"""Physical observation, calibration and map-frame transfer use the same metric printed board."""
import json
import time
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from explorer4 import peer_dock_real as dock


def test_board_requires_geometric_witness():
    frame=np.full((600,500,3),255,np.uint8)
    dictionary=cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    # 2 pixels per millimetre at the board plane.
    frame[40:400,70:430]=cv2.aruco.generateImageMarker(dictionary,7,360)[:,:,None]
    info={'width':500,'height':600,'distortion_model':'plumb_bob','k':[600,0,250,0,600,300,0,0,1],'d':[0]*5}
    assert not dock.board_pose(frame,info)['board_valid']
    frame[442:514,214:286]=cv2.aruco.generateImageMarker(dictionary,43,72)[:,:,None]
    r=dock.board_pose(frame,info)
    assert r['board_valid'] and r['max_reprojection_px']<1 and r['optical_from_board'][2][3]==pytest.approx(.30,abs=.003)
    frame[442:514,214:286]=255
    frame[490:562,214:286]=cv2.aruco.generateImageMarker(dictionary,43,72)[:,:,None]
    assert not dock.board_pose(frame,info)['board_valid']


def test_calibrated_donor_is_a_map_goal_and_wrong_pose_or_stale_frame_is_blocked(tmp_path,monkeypatch):
    monkeypatch.setattr(dock,'CALIBRATION',tmp_path/'cameras.json')
    from contextlib import nullcontext
    from explorer4 import fleet_config
    monkeypatch.setattr(fleet_config,'locked',nullcontext)
    monkeypatch.setattr(dock,'RUNS',tmp_path)
    pose=[0.,0.,0.]
    reference=dock.board_in_map(.85,0.,.40,180.)
    # Camera at base origin, optical Z forward, optical Y down.
    transform=dock.matrix([[0,0,1],[-1,0,0],[0,-1,0]],[0.,0.,0.2])
    def observation(board):
        return {'source_robot':'rosmaster','map_frame_id':'frame-one','odometry_frames':['odom_raw','base_footprint'],'board_valid':True,'camera_sha256':'camera','base_pose_map':pose,
                'optical_from_board':(np.linalg.inv(transform)@board).tolist(),'arm_deg':[90.]*6,
                'received_monotonic_ns':time.monotonic_ns(),'rgb_age_s':.02}
    for i,x in enumerate([.85,1.05]):
        board=reference.copy();board[0,3]=x
        ident=str(i)*32
        dock.write_json(tmp_path/ident/'result.json',{'created':time.time(),'observations':{'rosmaster':observation(board)}})
        entry=dock.calibrate(ident,'rosmaster',[x,0.,.4],180.,validate=bool(i))
    assert entry['verified'] and entry['position_residual_m']<1e-6
    fleet=SimpleNamespace(pose_frame=lambda *a:([0.,0.,0.],time.time(),'frame-one'),scan=lambda _:np.ones((3,2)))
    obs=observation(reference)
    report={'id':'field','selected':'rosmaster','observations':{'rosmaster':obs}}
    goal=dock.measured_goal(report,fleet)
    assert goal['pose']==pytest.approx([.85-.277,0.,0.],abs=1e-7) and goal['source_robot']=='rosmaster'
    obs['arm_deg'][1]+=8
    with pytest.raises(ValueError,match='arm'):
        dock.measured_goal(report,fleet)
    obs['received_monotonic_ns']-=10**9
    with pytest.raises(ValueError,match='устарело'):
        dock.measured_goal(report,fleet)


def test_two_rgb_packets_to_operator_only_drive_without_hardware(tmp_path,monkeypatch):
    """No driver or motor mock is needed to prepare a real DriveTo. STOP cancels it before execution."""
    from contextlib import nullcontext
    from explorer4 import catalog, episodes, fleet_config
    from explorer4.control import Control
    from explorer4.drive import DriveTo
    from explorer4.tank import TankSource

    monkeypatch.setattr(dock,'RUNS',tmp_path/'runs')
    monkeypatch.setattr(dock,'CALIBRATION',tmp_path/'camera.json')
    monkeypatch.setattr(episodes,'ROOT',tmp_path/'episodes')
    monkeypatch.setattr(fleet_config,'locked',nullcontext)
    monkeypatch.setattr(catalog,'event',lambda *a:None)
    monkeypatch.setattr(TankSource,'send',lambda *a:pytest.fail('motor path reached'))
    dictionary=cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    scene={'y_m':0.,'map':'lab-one','donor_located':True}
    fleet=SimpleNamespace(pose_frame=lambda r,_:(
        [0.,0.,0.] if r=='tank' or scene['donor_located'] else None,time.time(),scene['map']),scan=lambda _:np.ones((5,2)))
    class Sensors:
        def __init__(self,*,robot,isolated):
            self.robot=robot
        def snapshot(self,only):
            image=np.full((480,640,3),255,np.uint8)
            if self.robot=='rosmaster':
                x=int(round(320-scene['y_m']*800))
                for ident,y,side in ((7,240,144),(43,343,28)):
                    image[y-side//2:y+side//2,x-side//2:x+side//2]=cv2.aruco.generateImageMarker(dictionary,ident,side)[:,:,None]
            info={'width':640,'height':480,'distortion_model':'plumb_bob','k':[600,0,320,0,600,240,0,0,1],'d':[0]*5,'frame_id':'camera','age_s':0.}
            streams={'rgb_info':info,'rgb':{'age_s':0.,'source_timestamp_ns':4,'frame_id':'camera'},
                     'arm':{'age_s':0.,'unit':'servo_degrees_from_CubeBot_bridge','names':[f'servo{i}' for i in range(1,7)]},
                     'odometry':{'age_s':0.,'frame_id':'odom_raw','child_frame':'base_footprint'}}
            return {'arrays':{'rgb':image,'arm':np.zeros(6)},'payload':b'synthetic test packet','received_ns':time.monotonic_ns(),
                    'request_elapsed_s':0.,'meta':{'streams':streams,'read_only':True}}
        def close(self):
            pass
    monkeypatch.setattr(dock,'SensorClient',Sensors)
    first=dock.record(fleet)
    assert first['status']=='blocked' and first['observations']['rosmaster']['board_valid']
    dock.calibrate(first['id'],'rosmaster',[.75,0.,.25],180.)
    assert dock.record(fleet)['status']=='blocked'
    scene['y_m']=.12
    validation=dock.record(fleet)
    assert dock.calibrate(validation['id'],'rosmaster',[.75,.12,.25],180.,validate=True)['verified']
    field=dock.record(fleet)
    assert field['help_requested'] and field['help_received'] and field['selected']=='rosmaster'
    assert field['motor_commands_sent']==0 and len(list((dock.RUNS/field['id']).glob('*.npz')))==2
    assert field['goal']['pose']==pytest.approx([.473,.12,0.],abs=.005)
    current=json.loads(dock.CALIBRATION.read_text())
    expired=json.loads(json.dumps(current))
    expired['rosmaster']['valid_until']=time.time()-1
    dock.write_json(dock.CALIBRATION,expired)
    with pytest.raises(ValueError,match='Срок'):
        dock.measured_goal(field,fleet)
    dock.write_json(dock.CALIBRATION,current)
    stale=json.loads(json.dumps(field))
    stale['observations']['rosmaster']['received_monotonic_ns']-=10**9
    with pytest.raises(ValueError,match='устарело'):
        dock.measured_goal(stale,fleet)
    swapped=json.loads(json.dumps(field))
    swapped['observations']['rosmaster']['camera_sha256']='Tank camera'
    with pytest.raises(ValueError,match='CameraInfo'):
        dock.measured_goal(swapped,fleet)
    swapped=json.loads(json.dumps(field))
    swapped['observations']['rosmaster']['odometry_frames']=['unconnected','base_link']
    with pytest.raises(ValueError,match='odometry'):
        dock.measured_goal(swapped,fleet)
    scene['donor_located']=False
    with pytest.raises(ValueError,match='общей'):
        dock.measured_goal(field,fleet)
    scene.update(donor_located=True,map='after-map-reset')
    with pytest.raises(ValueError,match='общей'):
        dock.measured_goal(field,fleet)
    scene['map']='lab-one'
    control=Control();control.robot='tank';control.owner='browser';control.session='my-session';control.stop_event.clear()
    control.heartbeat('browser')
    monkeypatch.setattr(control,'authorized',lambda:True)
    session=SimpleNamespace(thread=SimpleNamespace(is_alive=lambda:True),phase='following',record_requested=False,
                            trial_plan=None,pilot=None,autonomous=False)
    epoch=dock.operator_session(control,session,'browser')
    with pytest.raises(PermissionError):
        dock.handoff(control,session,'other browser',epoch,field,fleet)
    session.record_requested=True
    with pytest.raises(PermissionError):
        dock.handoff(control,session,'browser',epoch,field,fleet)
    session.record_requested=False
    control.expires=0
    with pytest.raises(PermissionError):
        dock.handoff(control,session,'browser',epoch,field,fleet)
    control.heartbeat('browser')
    with pytest.raises(PermissionError,match='изменилась'):
        dock.handoff(control,session,'browser',('previous-session',0),field,fleet)
    assert control.goal is None
    assert isinstance(dock.handoff(control,session,'browser',epoch,field,fleet),dict)
    assert isinstance(control.goal,DriveTo) and control.goal.active
    assert control.goal.episode.extra['dock_observation_id']==field['id']
    control.stop('STOP')
    assert control.goal is None and control.expired()
    with pytest.raises(PermissionError):
        dock.handoff(control,session,'browser',epoch,field,fleet)


def test_fleet_map_identity_survives_save_and_changes_with_origin(tmp_path,monkeypatch):
    from explorer4 import fleet_map
    monkeypatch.setattr(fleet_map,'MAP_DIR',tmp_path)
    monkeypatch.setattr(fleet_map.world_memory,'forget',lambda:None)
    one=fleet_map.FleetMap()
    saved=one.frame_id
    one.save()
    two=fleet_map.FleetMap()
    assert two.load() and two.frame_id==saved
    two.reset()
    assert two.frame_id!=saved
