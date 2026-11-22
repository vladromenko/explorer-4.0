"""Read-only cooperative docking perception; an operator can hand a fresh measured goal to DriveTo."""
import concurrent.futures
import hashlib
import json
import math
import time
import uuid

import cv2
import numpy as np

from .paths import DATA
from .peer_dock_config import (DICTIONARY, MARKER_ID, MARKER_SIDE_M, MAX_AGE_S, STANDOFF_M,
                               WITNESS_ID, WITNESS_SIDE_M, WITNESS_OFFSET_DOWN_M)
from .sensors import SensorClient, stream_age

RUNS = DATA/'peer-dock'
CALIBRATION = DATA/'configs/peer-dock-cameras.json'
REQUEST = ['rgb','rgb_info','arm','odometry']
ROBOTS = ('tank','rosmaster')


def write_json(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp = path.with_suffix('.'+uuid.uuid4().hex+'.tmp')
    temp.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False))
    temp.replace(path)


def matrix(rotation,offset):
    result = np.eye(4)
    result[:3,:3],result[:3,3] = rotation,offset
    return result


def map_from_base(pose):
    x,y,yaw = pose
    c,s = math.cos(yaw),math.sin(yaw)
    return matrix([[c,-s,0],[s,c,0],[0,0,1]],[x,y,0])


def board_in_map(x,y,z,outward_deg):
    a = math.radians(outward_deg)
    normal = np.array([math.cos(a),math.sin(a),0.])
    up = np.array([0.,0.,1.])
    return matrix(np.column_stack([np.cross(up,normal),up,normal]),[x,y,z])


def board_pose(rgb,info):
    if rgb.shape!=(info['height'],info['width'],3) or info.get('distortion_model') not in ('rational_polynomial','plumb_bob'):
        raise ValueError('RGB resolution or distortion model differs from CameraInfo')
    K = np.asarray(info['k'],float).reshape(3,3)
    distortion = np.asarray(info['d'],float)
    if not np.isfinite(K).all() or min(K[0,0],K[1,1])<=0 or len(distortion) not in (4,5,8,12,14) or not np.isfinite(distortion).all():
        raise ValueError('Invalid measured camera intrinsics')
    params = cv2.aruco.DetectorParameters()
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco,DICTIONARY)),params)
    corners,ids,_ = detector.detectMarkers(cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY))
    ids = [] if ids is None else ids.flatten().tolist()
    result = {'detected_ids':ids,'board_valid':False}
    if any(ids.count(i)!=1 for i in (MARKER_ID,WITNESS_ID)):
        return {**result,'reason':'Both unique IDs 7 and 43 must appear on the same survey board'}
    world, pixels = [],[]
    for ident,side,offset in ((MARKER_ID,MARKER_SIDE_M,0),(WITNESS_ID,WITNESS_SIDE_M,-WITNESS_OFFSET_DOWN_M)):
        h = side/2
        world.extend([[x,y+offset,0.] for x,y in [(-h,h),(h,h),(h,-h),(-h,-h)]])
        pixels.extend(corners[ids.index(ident)].reshape(4,2).tolist())
    obj,img = np.array(world,float),np.array(pixels,float)
    ok,rvec,tvec = cv2.solvePnP(obj,img,K,distortion,flags=cv2.SOLVEPNP_ITERATIVE)
    if not ok:
        return {**result,'reason':'PnP failed'}
    projected,_ = cv2.projectPoints(obj,rvec,tvec,K,distortion)
    px = float(np.linalg.norm(projected.reshape(-1,2)-img,axis=1).max())
    R = cv2.Rodrigues(rvec)[0]
    T = matrix(R,tvec.ravel())
    if not np.isfinite(T).all() or T[2,3]<=0 or R[:,2]@tvec.ravel()>=0 or px>2.5:
        return {**result,'reason':'Pose is inconsistent with the printed board or exceeds 2.5 px reprojection'}
    return {**result,'board_valid':True,'optical_from_board':T.tolist(),'corners_px':pixels,'max_reprojection_px':px}


def observe(robot, directory, fleet):
    client = SensorClient(robot=robot,isolated=robot=='tank')
    try:
        packet = client.snapshot(only=REQUEST)
    finally:
        client.close()
    raw = packet['payload']
    (directory/(robot+'.npz')).write_bytes(raw)
    streams = packet['meta']['streams']
    image,info = packet['arrays'].get('rgb'),streams.get('rgb_info')
    result = {'source_robot':robot,'payload_sha256':hashlib.sha256(raw).hexdigest(),
              'payload_file':robot+'.npz','read_only':packet['meta'].get('read_only'),
              'received_monotonic_ns':packet['received_ns'],'received_at':time.time(),
              'rgb_age_s':stream_age(packet,'rgb',now_ns=packet['received_ns']) if 'rgb' in streams else None,
              'source_rgb_stamp_ns':streams.get('rgb',{}).get('source_timestamp_ns'),'board_valid':False}
    if image is None or info is None:
        return {**result,'reason':'Missing RGB or RGB CameraInfo'}
    preview = directory/(robot+'.jpg')
    bgr=cv2.cvtColor(image,cv2.COLOR_RGB2BGR)
    if cv2.imwrite(str(preview),bgr,[cv2.IMWRITE_JPEG_QUALITY,85]):
        result['preview_file']=preview.name
    cfg = {k:info.get(k) for k in ('width','height','k','d','frame_id','distortion_model')}
    result['camera'] = cfg
    result['camera_sha256'] = hashlib.sha256(json.dumps(cfg,sort_keys=True).encode()).hexdigest()
    if (result['rgb_age_s'] is None or result['rgb_age_s']>MAX_AGE_S or
        info.get('frame_id')!=streams['rgb'].get('frame_id')):
        return {**result,'reason':'Camera frame IDs differ or RGB is stale'}
    result.update(board_pose(image,info))
    if result['board_valid']:
        pairs = np.rint(result['corners_px']).astype(np.int32).reshape(2,4,2)
        cv2.polylines(bgr,list(pairs),True,(52,210,113),2,cv2.LINE_AA)
        cv2.imwrite(str(preview),bgr,[cv2.IMWRITE_JPEG_QUALITY,85])
    pose,stamp,frame = fleet.pose_frame(robot,MAX_AGE_S)
    result['map_frame_id'] = frame
    if pose is not None and abs(time.time()-stamp-result['rgb_age_s'])<=MAX_AGE_S:
        result['base_pose_map'] = [float(x) for x in pose]
        result['pose_at'] = stamp
    odom = streams.get('odometry') or {}
    if robot=='rosmaster' and stream_age(packet,'odometry',now_ns=packet['received_ns'])<=MAX_AGE_S:
        result['odometry_frames'] = [odom.get('frame_id'),odom.get('child_frame')]
    arm = packet['arrays'].get('arm')
    if (robot=='rosmaster' and arm is not None and streams['arm'].get('names')==[f'servo{i}' for i in range(1,7)]
        and streams['arm'].get('unit')=='servo_degrees_from_CubeBot_bridge' and stream_age(packet,'arm',now_ns=packet['received_ns'])<=MAX_AGE_S):
        result['arm_deg'] = arm.tolist()
    return result


def record(fleet=None):
    if fleet is None:
        from .fleet_map import FLEET
        fleet = FLEET
    ident = uuid.uuid4().hex
    directory = RUNS/ident
    directory.mkdir(parents=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        tasks = {r:pool.submit(observe,r,directory,fleet) for r in ROBOTS}
        observations = {}
        for robot,future in tasks.items():
            try:
                observations[robot] = future.result()
            except Exception as exc:
                observations[robot] = {'source_robot':robot,'board_valid':False,'reason':str(exc)}
    result = {'id':ident,'created':time.time(),'observations':observations,'selected':None,
              'help_requested':True,'help_received':False,'motor_commands_sent':0,'status':'blocked'}
    reasons = []
    for robot in ROBOTS:
        obs = observations[robot]
        if not obs['board_valid']:
            reasons.append(f"{robot}: {obs.get('reason','board unavailable')}")
            continue
        try:
            goal = measured_goal({**result,'selected':robot},fleet)
        except (ValueError,OSError,KeyError) as exc:
            reasons.append(f'{robot}: {exc}')
            continue
        result.update(goal=goal,status='measured_goal',selected=robot,help_requested=robot=='rosmaster',
                      help_received=robot=='rosmaster')
        break
    if result['status']=='blocked':
        result['reason'] = ' · '.join(reasons)
    write_json(directory/'result.json',result)
    write_json(RUNS/'latest.json',result)
    return result


def recent_report(ident):
    if not isinstance(ident,str) or len(ident)!=32 or any(c not in '0123456789abcdef' for c in ident):
        raise ValueError('Invalid capture ID')
    return json.loads((RUNS/ident/'result.json').read_text())


def calibrated_sample(obs,entry):
    if obs.get('source_robot')!=entry.get('robot') or not obs.get('map_frame_id') or obs['map_frame_id']!=entry.get('map_frame_id'):
        raise ValueError('Robot or surveyed map frame changed since calibration')
    if not obs.get('camera_sha256') or obs['camera_sha256']!=entry.get('camera_sha256'):
        raise ValueError('CameraInfo changed since calibration')
    if obs['source_robot']=='rosmaster':
        if obs.get('odometry_frames')!=entry.get('odometry_frames') or not obs.get('odometry_frames'):
            raise ValueError('ROSMASTER odometry frame or base frame changed')
        now,ref = np.asarray(obs.get('arm_deg',[])),np.asarray(entry.get('arm_deg',[]))
        if now.shape!=(6,) or ref.shape!=(6,) or not np.isfinite(now).all() or np.max(np.abs(now-ref))>2.:
            raise ValueError('ROSMASTER arm must be at the measured camera pose (within 2 degrees)')
    if 'base_pose_map' not in obs:
        raise ValueError('No fresh base pose on the shared lidar map')
    return map_from_base(obs['base_pose_map'])@np.asarray(entry['base_from_optical'])@np.asarray(obs['optical_from_board'])


def calibrate(run_id,robot,xyz,outward_deg,*,validate=False,valid_hours=8.):
    if robot not in ROBOTS or np.shape(xyz)!=(3,) or not np.isfinite([*xyz,outward_deg]).all() or xyz[2]<=0:
        raise ValueError('Enter a measured board centre in map metres and outward heading in degrees')
    report = recent_report(run_id)
    if not np.isfinite(valid_hours) or valid_hours<=0:
        raise ValueError('Choose a positive validity window for the calibration session')
    valid_until = float(report['created'])+3600*valid_hours
    if valid_until <= time.time():
        raise ValueError('The measured capture has expired; acquire a fresh calibration observation')
    obs = report['observations'][robot]
    if not obs['board_valid'] or 'base_pose_map' not in obs:
        raise ValueError('Calibration needs both board IDs and a synchronized shared-map pose')
    if not obs.get('map_frame_id'):
        raise ValueError('Missing synchronized shared map frame')
    if robot=='rosmaster' and (obs.get('odometry_frames') not in (['odom_raw','base_footprint'],['odom','base_footprint'],['odom','base_link']) or len(obs.get('arm_deg',[]))!=6):
        raise ValueError('Missing synchronized ROSMASTER servo readback')
    known = board_in_map(*xyz,outward_deg)
    from . import fleet_config
    with fleet_config.locked():
        data = json.loads(CALIBRATION.read_text()) if CALIBRATION.exists() else {}
        if validate:
            entry = data.get(robot)
            if not entry or run_id==entry['fit_run'] or np.linalg.norm(np.array(xyz)-entry['fit_xyz'])<.1:
                raise ValueError('Take an independent capture with the board moved at least 10 cm and surveyed again')
            estimate = calibrated_sample(obs,entry)
            residual = float(np.linalg.norm(estimate[:3,3]-known[:3,3]))
            angle = math.degrees(math.acos(np.clip(estimate[:3,2]@known[:3,2],-1,1)))
            entry.update(validation_run=run_id,outward_deg=float(outward_deg),valid_until=valid_until,position_residual_m=residual,heading_residual_deg=angle,
                         verified=residual<=.035 and angle<=5)
        else:
            entry = {'robot':robot, 'map_frame_id':obs['map_frame_id'],'odometry_frames':obs.get('odometry_frames'),
                     'fit_run':run_id,'fit_xyz':list(xyz),'camera_sha256':obs['camera_sha256'],'arm_deg':obs.get('arm_deg'),
                     'base_from_optical':(np.linalg.inv(map_from_base(obs['base_pose_map']))@known@
                                          np.linalg.inv(obs['optical_from_board'])).tolist(),'verified':False}
            data[robot] = entry
        write_json(CALIBRATION,data)
    return entry


def measured_goal(report,fleet):
    robot = report.get('selected')
    if not robot:
        raise ValueError('Ни одна камера не подтвердила обе метки листа №7 + №43')
    obs = report['observations'][robot]
    age = (time.monotonic_ns()-obs['received_monotonic_ns'])/1e9+obs['rgb_age_s']
    if not 0<=age<=MAX_AGE_S:
        raise ValueError('Изображение устарело. Повторите наблюдение')
    data = json.loads(CALIBRATION.read_text()) if CALIBRATION.exists() else {}
    entry = data.get(robot,{})
    if entry.get('verified') and time.time()>=entry.get('valid_until',0):
        raise ValueError('Срок измеренной калибровки завершился. Проверьте камеру по новой точке')
    if not entry.get('verified'):
        raise ValueError(f'Сначала измерьте и проверьте положение камеры {robot} на двух положениях листа')
    transform = calibrated_sample(obs,entry)
    normal = transform[:3,2]
    if abs(normal[2])>math.sin(math.radians(8)):
        raise ValueError('Метка должна стоять вертикально')
    outward = normal[:2]/np.linalg.norm(normal[:2])
    centre = transform[:2,3]
    # A surveyed board normal is preferred to a single planar PnP yaw. The check independently
    # constrains the two-tag solution against the operator's measured wall orientation.
    if 'outward_deg' not in entry:
        raise ValueError('Нет измеренного направления стены')
    wall = math.radians(entry['outward_deg'])
    surveyed = np.array([math.cos(wall),math.sin(wall)])
    if outward@surveyed<math.cos(math.radians(8)):
        raise ValueError('Ориентация листа не соответствует измеренной стене')
    target = centre + STANDOFF_M*surveyed
    for participant in {'tank',robot}:
        pose,stamp,frame = fleet.pose_frame(participant,MAX_AGE_S)
        if pose is None or frame!=obs.get('map_frame_id'):
            raise ValueError('Нет подтверждённой общей системы координат камер и Tank')
    if fleet.scan('tank') is None:
        raise ValueError('Нет свежей локализации или лидара Tank')
    return {'frame':'fleet_map','map_frame_id':obs['map_frame_id'],'pose':[float(target[0]),float(target[1]),math.atan2(-surveyed[1],-surveyed[0])],
            'source_robot':robot,'calibration_run':entry['validation_run'],'evidence':report['id'],'max_age_s':MAX_AGE_S}



def operator_drive(goal, fleet):
    """Attach evidence to the existing leased controller and stop if its lidar or map pose expires."""
    from .drive import DriveTo

    class MeasuredDock(DriveTo):
        def _command(self):
            pose,_,frame=fleet.pose_frame('tank',MAX_AGE_S)
            if pose is None or frame!=goal['map_frame_id'] or fleet.scan('tank') is None:
                self.finish('lost_localization','Остановка: устарели поза или лидар Tank')
                return [0.,0.]
            return super()._command()

    runner = MeasuredDock('tank',goal['pose'],text='к совместной метке №7 + №43',record=True,
                          tol=.06,heading_tol=.15,v_max=.10)
    runner.episode.extra.update(dock_observation_id=goal['evidence'],source_robot=goal['source_robot'],
                                validation_run=goal['calibration_run'],surveyed_goal=goal['pose'])
    return runner



def operator_session(control,session,owner):
    if (control.robot!='tank' or control.owner!=owner or not control.authorized() or control.expired() or
        not session.thread or not session.thread.is_alive() or session.phase!='following' or
        session.record_requested or session.trial_plan or session.pilot or session.autonomous or
        control.base_keys or getattr(control.goal,'active',False)):
        raise PermissionError('Нужна готовая ручная сессия Tank на полу, без записи, испытания и удержания стрелок')
    return control.session,control.generation


def handoff(control,session,owner,expected,report,fleet):
    """Preparing a goal never writes to hardware. The existing manual loop owns motor output and STOP."""
    with control.lock:
        if operator_session(control,session,owner)!=expected:
            raise PermissionError('Сессия Tank изменилась после наблюдения')
        if report.get('status')!='measured_goal':
            raise ValueError(report.get('reason') or 'Измеренная цель отсутствует')
        goal=measured_goal(report,fleet)
        control.goal=operator_drive(goal,fleet)
        return goal
