"""Replay a SimLab base policy against real LeRobot observations without opening a robot connection."""
import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np

from explorer4.paths import ROOT
from explorer4.sensors import decode_packet, feature_schema
from explorer4.simlab import contract
from explorer4.simlab.artifact import Policy
from explorer4.simlab.perception import MarkerDetector, TargetTracker
from explorer4.simlab.scenario import load_measurements


def recording_camera(robot, dataset, packet=None):
    source = Path(packet) if packet else next(iter(sorted((dataset/'sensors').glob('*.npz'))),None)
    if source:
        snapshot = decode_packet(source.read_bytes())
        if snapshot['meta']['robot']!=robot:
            raise ValueError('Camera calibration comes from a different robot')
        info = snapshot['meta']['streams'].get('rgb_info')
        if not info:
            raise ValueError('RGB CameraInfo missing from sensor packet')
    elif robot=='tank':
        source = ROOT/'configs/tank-hardware-evidence.json'
        info = json.loads(source.read_text())['installed_camera']['intrinsics']
    else:
        raise ValueError('Supply a ROSMASTER RGB CameraInfo packet from this camera with --camera-packet')
    if info.get('distortion_model') not in ('plumb_bob','rational_polynomial') or len(info.get('k',[]))!=9 or len(info.get('d',[])) not in (4,5,8,12,14):
        raise ValueError('Unsupported or incomplete RGB calibration')
    return info,str(source)


def labeled_samples(dataset, robot):
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    info = json.loads((dataset/'meta/info.json').read_text())
    _,channels = feature_schema(robot)
    features = info['features']
    if features.get('observation.environment_state',{}).get('names')!=channels:
        raise ValueError('Recording lacks the complete named environment_state for '+robot)
    if features.get('action',{}).get('names')!=contract.ROBOTS[robot]['action'] or 'observation.images.front' not in features:
        raise ValueError('Recording action order or camera differs from the base policy')
    from explorer4.profiles import profile
    cfg=profile(robot+'_dock_rgbd_lidar')
    if features.get('observation.state',{}).get('names')!=cfg['state_channels']:
        raise ValueError('Recording lacks the measured previous command contract for '+robot)
    # The official dataset resolves video shards, episode offsets and presentation timestamps.
    data = LeRobotDataset('local/'+dataset.name,root=dataset,video_backend='pyav')
    for f in data:
        rgb = (f['observation.images.front'].permute(1,2,0).numpy()*255).round().astype(np.uint8)
        yield (int(f['episode_index']),float(f['timestamp']),rgb,f['observation.environment_state'],f['action'],
               f['observation.state'][-len(cfg['channels']):])


def sensor_samples(archive,robot):
    info = json.loads((archive/'manifest.json').read_text())
    if info.get('robot')!=robot or info.get('category')!='sensor_diagnostic':
        raise ValueError('Expected the selected robot sensor diagnostic archive')
    for line in (archive/'index.jsonl').read_text().splitlines():
        row = json.loads(line)
        packet = decode_packet((archive/row['file']).read_bytes())
        if packet['meta']['robot']!=robot:
            raise ValueError('Robot identity changed within the sensor archive')
        rgb = packet['arrays'].get('rgb')
        if rgb is None:
            raise ValueError('No RGB camera in archived packet')
        yield 0,row['homebrain_received_ns']/1e9,rgb,row['observation.environment_state'],None,None


def shadow(policy, dataset, *, camera_packet=None, sensors_only=False):
    if policy.robot not in contract.ROBOTS:
        raise ValueError('The docking replay requires a mobile base policy')
    robot = policy.robot
    if sensors_only and not camera_packet:
        camera_packet = next(iter(sorted(dataset.glob('*.npz'))),None)
        if not camera_packet:
            raise ValueError('No archived sensor samples')
    calibration,source = recording_camera(robot,dataset,camera_packet)
    meas = load_measurements()
    marker = meas['dock_target']['marker']
    detector = MarkerDetector(calibration['k'],calibration['d'],side=marker['side'],marker_id=marker['id'])
    limits = np.asarray(contract.ROBOTS[robot]['policy_limits'])
    previous = np.zeros(len(limits))
    episode,last_time,rows,latencies = None,None,[],[]
    stream = sensor_samples(dataset,robot) if sensors_only else labeled_samples(dataset,robot)
    for current,t,rgb,environment,action,prior in stream:
        if tuple(rgb.shape)!=(calibration['height'],calibration['width'],3):
            raise ValueError('Decoded RGB resolution differs from CameraInfo')
        if np.shape(environment)!=(len(feature_schema(robot)[1]),) or not np.isfinite(environment).all():
            raise ValueError('Invalid environment_state shape or values')
        if current!=episode:
            tracker = TargetTracker()
            previous.fill(0)
            policy.reset()
            episode,last_time = current,t
        if t < last_time:
            raise ValueError('Recorded timestamps are out of order')
        target = tracker.update(detector.detect(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR)),t-last_time)
        last_time = t
        if prior is not None:
            native_prior=np.asarray(prior,dtype=float)
            if native_prior.shape!=limits.shape or not np.isfinite(native_prior).all():
                raise ValueError('Invalid recorded previous command')
            previous=np.clip(native_prior/limits,-1,1)
        obs = contract.from_real_features(robot,environment,target,previous,meas[robot]['lidar'])
        before = time.perf_counter()
        proposed = policy.act(obs)
        latencies.append(time.perf_counter()-before)
        normalized = (policy.buf.ravel()-policy.mean)/policy.std
        item = {'episode':current,'visible':target['visible'],'proposed':proposed.tolist(),
                'ood':bool(np.abs(normalized).max()>6)}
        if action is not None:
            native = np.asarray(action,dtype=float)
            if native.shape!=limits.shape or not np.isfinite(native).all():
                raise ValueError('Invalid recorded action')
            item['human'] = (native/limits).tolist()
        rows.append(item)
    if not rows:
        raise ValueError('No synchronized real observations')
    proposed = np.array([r['proposed'] for r in rows])
    report = {'robot':robot,'dataset':str(dataset),'frames':len(rows),'camera_info_source':source,
              'camera':{k:calibration[k] for k in ('width','height','frame_id','k','d','distortion_model')},
              'target_frame':'camera relative; camera-to-base extrinsics not established by this replay',
              'marker_visible_fraction':float(np.mean([r['visible'] for r in rows])),
              'out_of_distribution_fraction':float(np.mean([r['ood'] for r in rows])),
              'proposed_beyond_limits':int((np.abs(proposed)>1+1e-6).sum()),
              'latency_ms_p99':float(np.percentile(latencies,99)*1000),'commands_sent':0,
              'previous_action_source':'zero assumed; sensor archive contains no command labels' if sensors_only else 'previous command channels from synchronized observation.state',
              'physical_skill_verified':False}
    if not sensors_only:
        human = np.array([r['human'] for r in rows])
        moving = np.abs(human).max(1)>.05
        report.update(mae_normalized=np.abs(proposed-human).mean(0).tolist(),
                      sign_agreement_when_moving=(np.sign(proposed[moving])==np.sign(human[moving])).mean(0).tolist() if moving.any() else None)
    return {'summary':report,'frames':rows}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('policy',type=Path)
    parser.add_argument('dataset',type=Path)
    parser.add_argument('--camera-packet',type=Path,help='Sensor packet with matching robot RGB CameraInfo')
    parser.add_argument('--sensor-archive',action='store_true',help='Diagnostic observations only; no human action scores')
    parser.add_argument('--out',type=Path)
    args = parser.parse_args()
    policy = Policy(args.policy)
    result = shadow(policy,args.dataset,camera_packet=args.camera_packet,sensors_only=args.sensor_archive)
    result['summary']['policy'] = str(args.policy)
    result['summary']['weights_sha256'] = policy.info['weights_sha256']
    output = args.out or args.policy/f'shadow-{args.dataset.name}.json'
    output.write_text(json.dumps(result,indent=2))
    print(json.dumps(result['summary'],indent=2))


if __name__=='__main__':
    main()
