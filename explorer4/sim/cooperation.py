"""S1 uses an OpenCV waypoint measured in FleetWorld and independent physics scoring.

The fixed observation pose is the existing ArmModel.look_at_ik solution for the
known simulated dock marker. It is NOT a generalized target-seeking policy.
"""
import hashlib
import json
import math
import sys
from pathlib import Path
import cv2
import mujoco
import numpy as np
from .fleet import FleetWorld
from .peer_dock import DockSensors, MAX_AGE_S, MARKER_ID

OBSERVE_POSE=[46.76362916,104.44152446,23.57243078,44.75276349,90.,30.]


def marker(rgb):
    # Conservative, declared color/shape baseline in the fixed nominal scene.
    # Only image pixels: no segmentation IDs, object coordinates or task state.
    data=rgb.astype(float);r,g,b=data[:,:,0],data[:,:,1],data[:,:,2]
    mask=((r>45)&(r>1.7*g)&(r>2*b)).astype(np.uint8)
    count,labels,stats,_=cv2.connectedComponentsWithStats(mask,8)
    matches=[]
    for index in range(1,count):
        x,y,w,h,area=stats[index].tolist()
        if area>=500 and h>w*1.1 and w>12 and 1<x<rgb.shape[1]-w-1:
            patch=data[y:y+h,x:x+w]
            beige=(patch[:,:,0]>60)&(patch[:,:,1]>.65*patch[:,:,0])&(patch[:,:,1]<.95*patch[:,:,0])&(patch[:,:,2]<.8*patch[:,:,1])
            if int(beige.sum())>=30:matches.append({'box_xywh':[x,y,w,h],'pixels':area,'inner_patch_pixels':int(beige.sum())})
    return {'target_visible':len(matches)==1,'detections':matches,'source':'opencv_fixed_marker_rgb_v1',
            'scope':'single nominal simulated orange dock marker; not real object identity','world_xyz':None}


class CooperationWorld:
    def __init__(self, output, seed, scene='workshop'):
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.screen = scene.endswith('_screen')
        preset = scene.removesuffix('_screen')
        self.world = FleetWorld(seed, preset, peer_dock='screen' if self.screen else True)
        self.scene = scene
        self.reset(seed)

    def reset(self, seed):
        self.world.reset(seed)
        self.seed = seed
        self.stage = 'waiting_for_observation'
        self.received = None
        rng = np.random.default_rng(seed)
        # Move the actual board along its surveyed wall. Do not expose its XY
        # to either camera estimator or the motion controller.
        goal = np.array([rng.uniform(.77, 1.02), rng.uniform(-.23, .23), 0.])
        view = self.world.views['tank']
        view.env.goal = goal.copy()
        self.world.model.body('tank/target').pos[:2] = view.origin[:2] + goal[:2] + [.30, 0.]
        self.world.model.geom('tank/dock_zone').pos[:2] = view.origin[:2] + goal[:2]
        # Surveyed start pad. Some views face the target, others face away.
        pad = np.array([0., 0., rng.uniform(-.14, .14) + rng.choice([0., .93])])
        self.world.data.qpos[view.q] = pad
        if self.screen:
            from .peer_screens import vary_screen
            vary_screen(self.world.model, seed)
        mujoco.mj_forward(self.world.model, self.world.data)
        for item in self.world.views.values():
            item.read(forward=True)
        self.sensors = DockSensors(self.world, pad)
        self.start_odometry = pad.copy()
        self.initial = self.world.snapshot()

    def rewind(self):
        self.world.restore(self.initial)
        self.sensors.odometry = self.start_odometry.copy()
        self.stage = 'waiting_for_observation'
        self.received = None

    def camera(self, robot, label):
        image = self.world.render(robot)
        path = self.output / (label + '.png') if label else None
        if path:
            cv2.imwrite(str(path), cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
        packet = self.sensors.packet(robot, image)
        measurement = {'target_visible': packet is not None, 'detections': [],
                       'source': 'OpenCV ArUco/IPPE RGB', 'marker_id': MARKER_ID}
        if packet:
            measurement['detections'].append({'corners_px': packet['corners_px']})
        from .peer_screens import screen_fraction
        if robot == 'tank':
            measurement['screen_fraction'] = screen_fraction(image)
        return {'robot': robot, 'frame_id': robot + '/camera', 'image': str(path) if path else None,
                'measurement': measurement, 'packet': packet, 'simulation_time_s': float(self.world.data.time)}

    def overview(self,label):
        path=self.output/(label+'.png')
        cv2.imwrite(str(path),cv2.cvtColor(self.world.render(),cv2.COLOR_RGB2BGR))
        return str(path)

    def snapshot(self):
        from .state_codec import dump
        state_sha=dump(self.output/'initial-state.json',self.initial)
        self.overview('world-before')
        return {'scene':'shared_dock_'+self.scene+'_v3','seed':self.seed,'stage':self.stage,'domain':'sim',
            'model_sha256':self.world.manifest['xml_sha256'],
            'initial_state_sha256':state_sha,
            'recipient':self.camera('tank','recipient-before'),
            'donor':self.camera('rosmaster','donor-before'),
            'conditions':{'recipient_stationary':bool(np.linalg.norm(self.world.views['tank'].env.data.qvel)<1e-6),'fixed_scene':True},
            'action_provenance':'camera-derived metric waypoint, surveyed start and integrated ideal twist sensors'}

    def observe(self,scan=False,save=True):
        if self.stage!='waiting_for_observation':raise ValueError('Observation is not repeatable within this episode')
        before=self.world.views['tank'].env.data.qpos.copy()
        if scan:
            for pose in ([90.,115.,20.,40.,90.,30.],[65.,110.,20.,42.,90.,30.]):
                for _ in range(20):self.world.step({'rosmaster':pose})
        for _ in range(60):self.world.step({'rosmaster':OBSERVE_POSE})
        self.world.hold_agent('rosmaster')
        result=self.camera('rosmaster','donor-observation' if save else None)
        self.received = result['packet']
        self.helper_visible = self.received is not None
        self.stage = 'observed'
        if save:
            self.overview('world-observation')
        return {**result,'helper_outcome':'success' if self.helper_visible else 'failure',
            'recipient_held':bool(np.allclose(before,self.world.views['tank'].env.data.qpos,atol=1e-6)),
            'conditions':{'target_observed_by_helper':self.helper_visible,'fixed_scene':True,'recipient_stationary':True}}

    def local_scan(self, packet, *, save=True):
        """Use at most three seconds of onboard rotation and the existing dock controller."""
        attempts = 0
        if packet is None:
            for step in range(60):
                yaw = self.sensors.odometry[2]
                turn = float(np.clip(-2 * math.atan2(math.sin(yaw), math.cos(yaw)), -.5, .5))
                self.world.step({'tank':[0., turn]})
                self.sensors.integrate(.05)
                if step % 4 == 3:
                    attempts += 1
                    packet = self.camera('tank', 'local-scan-last' if save else None)['packet']
                    if packet is not None:
                        break
        result = self.dock(packet, save=save)
        return {**result, 'local_scan_frames':attempts}

    def dock(self, packet, *, save=True, on_tick=None):
        """Consume one metric message. Only the independent verifier reads task state."""
        now = float(self.world.data.time)
        age = now - packet['stamp_s'] if packet else None
        valid = (packet is not None and packet['frame'] == 'tank_start_map'
                 and packet['marker_id'] == MARKER_ID and 0 <= age <= MAX_AGE_S
                 and np.isfinite([*packet['target_xy_m'], packet['target_yaw_rad']]).all())
        actions = []
        view = self.world.views['tank']
        if valid:
            self.stage = 'executing'
            while not view.done:
                action = self.sensors.action(packet)
                self.world.step({'tank': action})
                self.sensors.integrate(view.env.dt)
                actions.append([float(x) for x in action])
                if on_tick is not None:
                    on_tick(len(actions), self.world)
        self.world.stop()
        self.stage = 'completed'
        info = view.env.info()
        outcome = 'success' if valid and view.result and view.result[4]['outcome'] == 'success' else 'failure'
        result = {'source':'fixed_outcome_verifier', 'version':'shared-dock-rgb-pose-v3',
                  'oracle_used_only_for_evaluation':True,
                  'helper':'success' if self.received else 'unknown',
                  'recipient':outcome, 'task':outcome,
                  'raw_environment_outcome':view.result[4]['outcome'] if view.result else None,
                  'distance_m':info['distance_m'], 'yaw_error_rad':info['yaw_error_rad'],
                  'stationary':info['stationary'], 'stable_s':info['stable_s'],
                  'simulation_time_s':float(self.world.data.time), 'packet_age_s':age,
                  'reason':'goal_reached' if outcome=='success' else ('drive_failed' if valid else 'stale_or_missing_packet'),
                  'consumed_packet':packet if valid else None, 'actions_sent':len(actions),
                  'first_action':actions[0] if actions else None,
                  'commands_sha256':hashlib.sha256(np.asarray(actions,dtype='<f8').tobytes()).hexdigest()}
        if save:
            self.camera('tank','recipient-final')
            self.overview('world-final')
            (self.output/'verifier.json').write_text(json.dumps(result,indent=2))
        return result

    def close(self):self.world.stop();self.world.close()


def serve(output,seed,scene='workshop'):
    world=CooperationWorld(output,seed,scene)
    local_packet=None
    try:
        for line in sys.stdin:
            try:
                request=json.loads(line)
                if set(request) not in ({'command'}, {'command','packet'}):raise ValueError('Invalid cooperation request')
                command=request['command']
                if command=='snapshot':
                    result=world.snapshot()
                    local_packet=result['recipient']['packet']
                elif command=='local_scan':
                    if world.stage != 'waiting_for_observation' or request.get('packet') != local_packet:
                        raise ValueError('Local scan must start at the original recipient observation')
                    result=world.local_scan(local_packet)
                elif command=='local_dock':
                    if world.stage!='waiting_for_observation' or not request.get('packet') or request['packet']!=local_packet:
                        raise ValueError('Docking requires the active local camera packet')
                    result=world.dock(local_packet)
                elif command in ('observe','scan'):result=world.observe(scan=command=='scan')
                elif command=='dock':
                    if world.stage != 'observed' or request.get('packet') != world.received or world.received is None:
                        raise ValueError('Docking requires a fresh packet from the active observation')
                    result=world.dock(request['packet'])
                elif command=='close':break
                else:raise ValueError('Unknown cooperation command')
                print(json.dumps({'ok':True,'result':result}),flush=True)
            except Exception as exc:print(json.dumps({'ok':False,'error':str(exc)}),flush=True)
    finally:world.close()


if __name__=='__main__':serve(sys.argv[1],int(sys.argv[2]),sys.argv[3] if len(sys.argv)>3 else 'workshop')
