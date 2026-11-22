"""Passive lab evidence. Read USB links, enabled sensor GET endpoints, archive metadata and hub status."""
import argparse
import concurrent.futures
import json
import time
from pathlib import Path

from explorer4 import fleet_config
from explorer4.paths import DATA
from explorer4.sensors import SensorClient, decode_packet


def stream_summary(packet):
    result = {}
    for key,s in packet['meta']['streams'].items():
        result[key] = {k:s[k] for k in ('frame_id','topic','width','height','age_s','source_timestamp_ns') if k in s}
        if key == 'tf_static':
            result[key]['pairs'] = [[v.get('parent',v.get('frame_id')),v.get('child',v.get('child_frame_id'))]
                                    for v in s.get('transforms',[])]
    return result


def sensor_readiness(robot):
    permitted,reason = fleet_config.robot_allowed(robot)
    live = {}
    if permitted:
        for mode in (False,True):
            client = None
            try:
                client = SensorClient(robot=robot,isolated=mode)
                packet = client.snapshot(only=['rgb_info','depth_info','scan','scan_rear','imu','odometry','arm','tf_static'])
                live[str(mode)] = {'available':True,'streams':stream_summary(packet)}
            except Exception as exc:
                live[str(mode)] = {'available':False,'reason':type(exc).__name__}
            finally:
                if client is not None:
                    client.close()
    archived = {}
    candidates = sorted((DATA/'sensor-recordings').glob(robot+'-*/000000.npz'),key=lambda f:f.stat().st_mtime)
    if candidates:
        archived = {'path':str(candidates[-1]),'streams':stream_summary(decode_packet(candidates[-1].read_bytes()))}
    return {'enabled_in_panel':permitted,'panel_reason':reason,'live_sensor_endpoints':live,'archive':archived}


def snapshot():
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        readings = dict(zip(('tank','rosmaster'),pool.map(sensor_readiness,('tank','rosmaster'))))
    files = sorted((DATA/'fleet-captures').glob('*/manifest.json'),key=lambda p:p.stat().st_mtime,reverse=True)
    previous = {}
    for file in files:
        record = json.loads(file.read_text())
        if record.get('phase')=='complete' and record.get('readback',{}).get('passed'):
            previous = {'id':file.parent.name,'robots':record.get('observed_robots'),'streams':record.get('streams'),
                        'matched_clock_samples':record.get('matched_clock_samples'),'finished_at':record.get('finished_at')}
            break
    hubfile = DATA/'ros2-hub/status.json'
    hub = json.loads(hubfile.read_text()) if hubfile.is_file() else {}
    return {'checked_unix_s':time.time(),'commands_sent':0,'so101':{
            'serial_links':[p.name for p in sorted(Path('/dev/serial/by-id').glob('*'))],
            'camera_links':[p.name for p in sorted(Path('/dev/v4l/by-id').glob('*'))],
            'calibration_files':[p.name for p in sorted((DATA/'calibration').glob('*.json'))],
            'active_motor_or_image_test':False},'mobile':readings,'latest_verified_mcap':previous,
            'hub_status_file':{k:hub.get(k) for k in ('updated_at','domain_id','shared_map_ready','read_only')},
            'hardware_setup_needed':[
                'Survey a common floor marker and base frame for each mobile robot before cross-robot map goals.',
                'Measure camera-to-base at the selected ROSMASTER arm pose; verify base-frame marker residuals at multiple ranges.',
                'Measure stopping distance and odometry scale on the actual floor before physical closed-loop docking.',
                'For the installed gripper and actual cube, verify contact, supported lift height, and release with an independent view.']}


if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    args.out.write_text(json.dumps(snapshot(),indent=2))
    print(args.out)
