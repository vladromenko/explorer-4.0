"""Homebrain client for the isolated Tank agent. Motor watchdog lives on the robot."""
import json
import math
import threading
import time
import cv2
import httpx
import numpy as np
from .paths import DATA


def config():return json.loads((DATA/'configs/tank-agent.json').read_text())

def client():
    from .local_work import require_hardware_mode
    require_hardware_mode('tank')
    cfg=config()
    return httpx.Client(base_url=f"http://{cfg['host']}:{cfg['port']}",headers={'X-Explorer-Token':cfg['token']},
                        trust_env=False,timeout=.25)


def require_response(response, operation):
    if response.status_code==409:
        raise RuntimeError('Tank · '+operation+': '+str(response.json().get('detail','Управление остановлено')))
    response.raise_for_status()

def autonomy_hold(observation, requested, now_ns):
    """Check the age of both robot observations at dispatch, including transport and inference."""
    if not observation or observation.get("camera_missing", True):
        return "Нет изображения камеры Tank"
    image = observation["images"]["front"]
    local_age = now_ns - image["homebrain_receive_timestamp_ns"]
    transport = image.get("request_duration_ns")
    sensors = observation.get("motion_sensors", {})
    for name, age in (("камеры", image.get("age_at_agent_response_ns")), ("лидара", sensors.get("scan_age_ns"))):
        if (type(age) is not int or type(transport) is not int or min(age, local_age, transport) < 0
                or age + local_age + transport > 500_000_000):
            return "Нет свежего наблюдения " + name + " Tank"
    v, w = requested
    needed = ("front", "rear") if w else (("front",) if v > 0 else ("rear",))
    for direction in needed:
        distance = sensors.get(direction)
        if not isinstance(distance, (int, float)) or not math.isfinite(distance) or distance <= 0:
            return "Лидар Tank не подтвердил сектор " + direction
    return None


class TankSource:
    def __init__(self,control,mode='manual',environment=False):
        self.control=control
        self.mode=mode
        self.http=client()
        self.lease=None
        self.previous_camera=None
        self.provenance={}
        self.sequence=0
        self.stop_requested=lambda:False
        self.environment=environment
        self.sensors=None
        from .tank_response import ScanResponse
        self.scan_response=ScanResponse()

    def start(self,explicit_user_start=False,stop=lambda:False):
        if not explicit_user_start or stop():raise InterruptedError('Explicit live operator required')
        self.stop_requested=stop
        observations=[]
        for _ in range(5):
            a=time.monotonic_ns();r=self.http.get('/health');r.raise_for_status();b=time.monotonic_ns()
            observations.append({'rtt_ns':b-a,'offset_ns':(a+b)//2-r.json()['monotonic_ns']})
        clock=min(observations,key=lambda v:v['rtt_ns'])
        self.provenance={'robot':'tank','profile':'MentorPi_Tank','clock_mapping':clock,
            'clock_mapping_kind':'midpoint_estimate_not_shared_clock','physical_skill_verified':False,
            'state_kind':'previous_transmitted_command_estimate','wheel_feedback':'unavailable',
            'motor_acknowledgement':False,'odometry_integral_excluded':True}
        request={'mode':self.mode,'profile':'tank_dock_rgbd_lidar' if self.environment else 'tank_dock'}
        if self.environment:request['environment']=True
        r=self.http.post('/session',json=request,timeout=20)
        if r.status_code==409 and 'Factory control' in str(r.json().get('detail','')):
            # The factory app still owns the board (e.g. after a reboot): hand it over automatically.
            from .tank_handoff import invoke
            invoke('enter')
            r=self.http.post('/session',json=request,timeout=20)
        require_response(r,'запуск');self.lease=r.json()['lease']
        if self.environment:
            from .sensors import SensorFeed,stream_age,SCHEMA
            self.sensors=SensorFeed(interval=.2,isolated=True);self.sensors.start()
            deadline=time.monotonic()+8
            while not stop() and time.monotonic()<deadline:
                self.send([0.,0.])
                packet=self.sensors.latest
                if packet and all(stream_age(packet,k)<1. for k in ('scan','depth','imu')):break
                time.sleep(.05)
            else:raise RuntimeError('Нет свежих depth/lidar/IMU для выбранного профиля')
            self.provenance['environment_schema']=SCHEMA
        if stop():raise InterruptedError('Operator stopped during preparation')
        return self.provenance

    def begin_episode(self):pass

    def observe(self):
        if self.stop_requested():raise InterruptedError('STOP before observation')
        # The camera is needed for recordings, not for driving: a missing frame is reported
        # (camera_missing) and the previous frame is reused instead of stopping the robot.
        started = time.monotonic_ns()
        rgb=None;info=None;status=None
        try:
            r=self.http.get('/frame.jpg',timeout=.4)
            if r.status_code==200:
                info=json.loads(r.headers['X-Explorer-Camera']);status=json.loads(r.headers['X-Explorer-Observation'])
                bgr=cv2.imdecode(np.frombuffer(r.content,dtype=np.uint8),cv2.IMREAD_COLOR)
                if bgr is not None:
                    rgb=cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB)
                    if (rgb.shape[1],rgb.shape[0])!=(640,400):rgb=cv2.resize(rgb,(640,400))
        except httpx.TimeoutException:pass
        received=time.monotonic_ns()
        if status is None:
            h=self.http.get('/health',timeout=.5);h.raise_for_status();status=h.json()
        camera_missing=rgb is None
        if camera_missing:
            rgb=getattr(self,'last_rgb',None)
            if rgb is None:rgb=np.zeros((400,640,3),np.uint8)
            info={'sequence':self.previous_camera if self.previous_camera is not None else -1,'source_timestamp_ns':0,
                  'source_clock':'missing','received_ns':status['monotonic_ns']}
        self.last_rgb=rgb
        sensor_packet=self.sensors.latest if self.sensors else None
        observation_time=time.monotonic_ns()
        reused=info['sequence']==self.previous_camera;self.previous_camera=info['sequence']
        image={'image':rgb,'sequence':info['sequence'],'timestamp_ns':received,'reused':reused,
               'source_timestamp_ns':info['source_timestamp_ns'],'source_clock':info['source_clock'],
               'agent_receive_timestamp_ns':info['received_ns'],'homebrain_receive_timestamp_ns':received,
               'request_duration_ns':received-started,'timestamp_kind':'available_at_homebrain','age_at_agent_response_ns':status['monotonic_ns']-info['received_ns']}
        for key in ('limits','motor_link','initial_battery_voltage','minimum_battery_voltage','minimum_battery_under_load','limit_events'):
            if key in status:self.provenance[key]=status[key]
        result={'observation_timestamp_ns':observation_time,'camera_missing':camera_missing,
                'observation.state':status['action'],'images':{'front':image},
                'motion_sensors':{'scan_age_ns':status['monotonic_ns']-status['scan_received_ns']
                                  if status.get('scan_received_ns') is not None else None,
                                  'front':status.get('front_distance_m'),'rear':status.get('rear_distance_m')},
                'state_kind':'previous_transmitted_command_estimate','state_valid':False,
                'measured_response_kind':'previous_command_estimate_no_wheel_feedback',
                'battery_voltage':status['battery_voltage'],'battery_source':'RRC packet voltage_mV/1000',
                'battery_agent_received_ns':status['battery_received_ns'],'imu_raw':status['imu'],
                'imu_agent_received_ns':status['imu_received_ns'],'robot_clock':'tank_monotonic_ns'}
        if self.environment:
            from .sensors import environment_features,stream_age
            packet=sensor_packet
            if packet is None or packet['received_ns']>observation_time:
                raise RuntimeError('Нет причинно допустимого пакета датчиков')
            if any(stream_age(packet,k,observation_time)>2. for k in ('scan','depth','imu')):
                raise RuntimeError('Depth/lidar/IMU устарели: профиль окружения остановлен')
            result.update(self.scan_response.observe(packet))
            result.update({'observation.environment_state':environment_features(packet,observation_time).tolist(),
                           '_sensor_packet':packet})
        return result

    def send(self,requested,observation=None, *, autonomous_goal=False, expected_goal=None):
        if self.stop_requested():raise InterruptedError('STOP before command')
        if len(requested)!=2 or not all(math.isfinite(v) for v in requested):
            raise ValueError('Tank requires two finite velocity channels')
        intent = list(requested)
        goal = getattr(self.control, "goal", None)
        bound_goal = expected_goal if expected_goal is not None else goal
        autonomous = self.mode != "manual" or autonomous_goal or bool(bound_goal and bound_goal.active)
        index=self.sequence;self.sequence+=1
        a=time.monotonic_ns()
        self.provenance['last_command_attempt']={'sequence':index,'requested':intent,'send_start_ns':a,'accepted':'unknown'}
        response=None
        hold = None
        for attempt in range(2):
            if self.stop_requested():
                raise InterruptedError("STOP before command")
            now = time.monotonic_ns()
            if any(intent) and autonomous:
                hold = autonomy_hold(observation, intent, now)
            elif observation is not None and now - observation['observation_timestamp_ns'] > 2_000_000_000:
                hold = "Наблюдение Tank устарело"
            owns_goal = bound_goal is not None and getattr(self.control, "goal", None) is bound_goal
            if autonomous_goal and (not owns_goal or not bound_goal.active):
                hold = "Задание Tank завершено или заменено"
            command = [0., 0.] if hold else intent
            if hold and owns_goal and bound_goal.active:
                bound_goal.cancel(hold)
            self.provenance['last_command_attempt'].update(sequence=index, dispatched=command, guard_reason=hold)
            try:
                payload={'lease':self.lease,'sequence':index,'v':command[0],'w':command[1]}
                if autonomous and self.mode == "manual":
                    payload["autonomous_goal"] = True
                response=self.http.post('/command',json=payload,timeout=.5)
                break
            except httpx.TimeoutException as exc:
                if attempt:raise RuntimeError('Tank: нет ответа по Wi-Fi дважды подряд') from exc
                index=self.sequence;self.sequence+=1
        b=time.monotonic_ns();require_response(response,'команда');sent=response.json()
        self.provenance['last_command_attempt']['accepted']=True
        return {'action':sent['action'],'requested_action':intent,
                'motion_paused':bool(hold) or sent.get('motion_paused',False),'pause_reason':hold or sent.get('pause_reason'),
                'action_send_start_ns':a,'action_send_end_ns':b,'action_acknowledged':False,
                'agent_accepted_command':True,'agent_autonomy_guard':sent.get('autonomous_guard'),
                'robot_serial_send_start_ns':sent['send_start_ns'],
                'robot_serial_send_end_ns':sent['send_end_ns'],'motor_targets_rps':sent['motor_targets_rps']}

    def sample(self,index,stop=lambda:False):
        if stop():raise InterruptedError('STOP before observation')
        observation=self.observe()
        if stop():raise InterruptedError('STOP before command')
        goal=getattr(self.control,'goal',None)
        if goal is not None and goal.active and self.control.base_keys:
            self.control.cancel_goal('Перехват стрелками')      # the operator always wins
            goal=None
        goal_control = goal is not None and goal.active
        if goal_control:
            image = observation['images']['front']
            if hasattr(goal, 'command_from_camera'):
                requested = goal.command_from_camera(image['image'], image, image.get('homebrain_receive_timestamp_ns'))
            else:
                requested = goal.command(image['image'])
        else:
            requested=self.control.base_action()
        action=self.send(requested,observation,autonomous_goal=goal_control,expected_goal=goal if goal_control else None)
        if goal is not None:action['_goto']=goal.status()   # not recorded
        if action['motion_paused']:self.control.clear_base_inputs()
        return {**observation,**action,'frame_id':index,'teleoperation_phase':'paused' if action['motion_paused'] else 'following'}

    def plan_action(self,provider,observation):
        if not provider.needs_inference():return provider.next(observation)
        # Never extend the previous moving command while waiting for GPU inference.
        self.send([0.,0.])
        done=threading.Event();errors=[];started=time.monotonic_ns()
        def hold():
            try:
                while not done.wait(.1):self.send([0.,0.])
            except Exception as exc:errors.append(exc)
        worker=threading.Thread(target=hold,daemon=True);worker.start()
        try:result=provider.next(observation)
        finally:
            done.set();worker.join(timeout=1)
            self.provenance.setdefault('planning_holds',[]).append({
                'start_ns':started,'end_ns':time.monotonic_ns(),'command':[0.,0.]})
        if worker.is_alive():raise RuntimeError('Tank neutral-command worker did not stop')
        if errors:raise errors[0]
        if self.stop_requested():raise InterruptedError('STOP during policy inference')
        return result

    def close(self):
        errors=[]
        try:
            r=self.http.post('/stop',timeout=8);require_response(r,'STOP')
        except Exception as exc:
            reason='STOP Tank не подтверждён. Выключите питание выключателем. '+str(exc)
            errors.append(reason)
            self.provenance['termination_reason']='motor_link_lost' if 'motor_link_lost' in str(exc) or 'serial' in str(exc).lower() else 'control_link_lost_unknown'
            marker=DATA/'validation/tank-link-events'/f'{time.time_ns()}.json'
            marker.parent.mkdir(parents=True,exist_ok=True)
            marker.write_text(json.dumps({'event':self.provenance['termination_reason'],'operator_ack_required':True,'reason':reason,'created_at':time.time(),
                                          'physical_stop_confirmed':False},ensure_ascii=False,indent=2))
        finally:
            try:
                health=self.http.get('/health',timeout=1);health.raise_for_status();status=health.json()
                for key in ('limits','motor_link','initial_battery_voltage','minimum_battery_voltage','minimum_battery_under_load','limit_events'):
                    if key in status:self.provenance[key]=status[key]
                if status.get('motor_link',{}).get('pending'):self.provenance['termination_reason']='motor_link_lost'
            except Exception:pass
            self.http.close()
            if self.sensors:self.sensors.close()
        return errors


def acknowledge_motor_link(stationary):
    if stationary is not True:raise PermissionError('Подтвердите, что Tank стоит')
    from .tank_handoff import invoke
    invoke('enter')  # Explicit user confirmation also handles a rebooted factory owner.
    with client() as http:
        response=http.post('/motor-link/continue',json={'stationary':True},timeout=20)
        require_response(response,'восстановление связи')
        return response.json()
