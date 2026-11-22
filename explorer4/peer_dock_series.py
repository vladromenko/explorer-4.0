"""Counterbalanced physical pilot; independent endpoint measurements, existing leased Tank execution."""
import concurrent.futures
import hashlib
import json
import math
import time
import threading
import uuid

import numpy as np

from . import fleet_config, peer_field_outcomes
from .paths import DATA,ROOT
from . import peer_dock_real as field
from .peer_dock_config import MAX_AGE_S
from .navigation import RADIUS, guard, wrap

SERIES = DATA/'peer-dock-field/series.json'
CONFIG = ROOT/'configs/peer-dock-field.json'


SUPPLEMENT = ROOT/'configs/peer-dock-field-sequential-v1.json'
SUPPLEMENT_SHA256 = 'f9dbf5f476baff5f04bfa6e17bd922db7d0121925d4efe7411312e290ab9b7bf'


def _supplement_for(series):
    raw = SUPPLEMENT.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SUPPLEMENT_SHA256:
        raise ValueError('Контрольная сумма дополнения к полевой серии не совпадает')
    spec = json.loads(raw)
    original = CONFIG.read_bytes()
    if (hashlib.sha256(original).hexdigest() != spec['original_protocol_sha256']
            or series['protocol_sha256'] != spec['original_protocol_sha256']
            or series['protocol'] != json.loads(original)
            or [slot for slot in spec['order'] if slot[1] != 'sequential'] != series['protocol']['order']):
        raise ValueError('Дополнение не соответствует исходному физическому протоколу')
    return spec


def checked_order(series):
    registered = series.get('sequential_supplement')
    if registered is not None:
        if (registered.get('sha256') != SUPPLEMENT_SHA256 or registered.get('protocol') != _supplement_for(series)):
            raise ValueError('Сохранённое дополнение отличается от зарегистрированного порядка серии')
    return peer_field_outcomes.effective_order(series)


def prepare():
    with fleet_config.locked():
        if SERIES.is_file():
            series = json.loads(SERIES.read_text())
            if 'sequential_supplement' in series or series['fixtures'] or series['attempts']:
                checked_order(series)
                return series
        else:
            raw = CONFIG.read_bytes()
            series = {'protocol':json.loads(raw), 'protocol_sha256':hashlib.sha256(raw).hexdigest(),
                      'created':time.time(), 'fixtures':{}, 'attempts':[]}
        series['sequential_supplement'] = {'protocol':_supplement_for(series),
                                          'sha256':SUPPLEMENT_SHA256, 'registered_at':time.time()}
        field.write_json(SERIES,series)
        return series


def state():
    if SERIES.is_file():
        series = json.loads(SERIES.read_text())
        if 'sequential_supplement' in series or series['fixtures'] or series['attempts']:
            checked_order(series)
            return series
    return prepare()


def next_slot(s):
    rows = s['attempts']
    if rows and 'endpoint' not in rows[-1]:
        raise ValueError('Нужна остановка и независимый замер предыдущей попытки')
    order = checked_order(s)
    if 'sequential_supplement' in s and any(
            i >= len(order) or r.get('slot') != i or [r.get('layout'),r.get('condition')] != order[i]
            for i,r in enumerate(rows)):
        raise ValueError('Журнал попыток не совпадает с утверждённым порядком серии')
    if len(rows) >= len(order):
        raise ValueError(f'Все попытки учтены ({len(order)} из {len(order)})')
    return order[len(rows)]


def calibration_entry(robot,frame):
    entries=json.loads(field.CALIBRATION.read_text()) if field.CALIBRATION.exists() else {}
    e=entries.get(robot,{})
    if (e.get('robot')!=robot or not e.get('verified') or e.get('map_frame_id')!=frame or
        time.time()>=e.get('valid_until',0)):
        raise ValueError('Нужна действующая проверенная калибровка '+robot+' в общей карте')
    return e


def fixture_pose(fleet):
    robots={}
    for robot in field.ROBOTS:
        pose,_,frame=field.real_pose(fleet,robot)
        if pose is None:
            raise ValueError('Нет свежей позы '+robot+' на общей карте')
        e=calibration_entry(robot,frame)
        robots[robot]={'pose':list(map(float,pose)),'map_frame_id':frame,'calibration_run':e['validation_run'],
                       'outward_deg':e['outward_deg'],
                       'mount_sha256':hashlib.sha256(json.dumps([e['camera_sha256'],e['base_from_optical'],
                           e.get('arm_deg'),e.get('odometry_frames'),e['outward_deg']],sort_keys=True).encode()).hexdigest()}
    client=field.SensorClient(robot='rosmaster')
    try:
        packet=client.snapshot(only=['arm','odometry'])
    finally:
        client.close()
    stream=packet['meta']['streams'].get('arm',{})
    arm=np.asarray(packet['arrays'].get('arm',[]))
    odom=packet['meta']['streams'].get('odometry',{})
    donor=calibration_entry('rosmaster',robots['rosmaster']['map_frame_id'])
    if (field.stream_age(packet,'arm')>MAX_AGE_S or field.stream_age(packet,'odometry')>MAX_AGE_S or
        [odom.get('frame_id'),odom.get('child_frame')]!=donor.get('odometry_frames') or
        arm.shape!=(6,) or not np.isfinite(arm).all() or stream.get('names')!=[f'servo{i}' for i in range(1,7)] or
        stream.get('unit')!='servo_degrees_from_CubeBot_bridge' or np.max(np.abs(arm-donor['arm_deg']))>2.):
        raise ValueError('ROSMASTER должен стоять в проверенной позе руки с актуальной одометрией')
    robots['rosmaster']['arm_deg']=arm.tolist()
    if robots['tank']['map_frame_id']!=robots['rosmaster']['map_frame_id']:
        raise ValueError('Роботы находятся в разных картах')
    if abs(wrap(math.radians(robots['tank']['outward_deg']-robots['rosmaster']['outward_deg'])))>.15:
        raise ValueError('Калибровки описывают разные направления стены')
    return robots


def label_layout(layout,note,fleet,control,start_distance_m):
    if control.owner is not None or not control.stop_event.is_set():
        raise ValueError('Сначала нажмите STOP')
    if layout not in ('A','B') or not note.strip():
        raise ValueError('Выберите A/B и опишите метки пола для этой расстановки')
    p=state()['protocol']
    if start_distance_m is None or not math.isfinite(start_distance_m) or start_distance_m<=p['terminal_position_tolerance_m']+p['start_position_tolerance_m']:
        raise ValueError('Измерьте начальное расстояние до креста: Tank должен начинать за пределами допуска')
    poses=fixture_pose(fleet)
    with fleet_config.locked(),control.lock:
        if control.owner is not None or not control.stop_event.is_set():
            raise ValueError('Во время измерения расстановки нужен STOP')
        s=json.loads(SERIES.read_text())
        if layout in s['fixtures']:
            raise ValueError('Эта расстановка уже зафиксирована')
        s['fixtures'][layout]={'note':note.strip(),'start_distance_m':start_distance_m,'robots':poses,'created':time.time()}
        field.write_json(SERIES,s)


def check_position(s,layout,fleet):
    fixture=s['fixtures'].get(layout)
    if not fixture:
        raise ValueError('Зарегистрируйте маркированную исходную расстановку '+layout)
    actual=fixture_pose(fleet)
    spec=s['protocol']
    for r,p in actual.items():
        ref=fixture['robots'][r]
        if (ref['map_frame_id']!=p['map_frame_id'] or ref['mount_sha256']!=p['mount_sha256'] or
            math.dist(ref['pose'][:2],p['pose'][:2])>spec['start_position_tolerance_m'] or
            abs(wrap(ref['pose'][2]-p['pose'][2]))>spec['start_yaw_tolerance_rad']):
            raise ValueError('Восстановите исходную отметку, курс и калибровку '+r+' для '+layout)
    return actual


def terminal(run_id,evidence):
    with fleet_config.locked():
        s=json.loads(SERIES.read_text());row=s['attempts'][-1]
        if row['id']!=run_id or 'runtime' in row:
            return
        row['runtime']=evidence
        field.write_json(SERIES,s)


def observe_one(robot,run_dir,iteration,fleet):
    ident=f'{iteration:03d}-{robot}'
    folder=run_dir/ident
    folder.mkdir(parents=True)
    try:
        obs=field.observe(robot,folder,fleet)
    except Exception as exc:
        obs={'source_robot':robot,'board_valid':False,'reason':str(exc)}
    result={'id':run_dir.name+'/'+ident,'selected':robot,'observations':{robot:obs}}
    field.write_json(folder/'observation.json',result)
    if iteration==1 and robot=='tank':
        from .peer_field_shadow import capture_hook
        capture_hook(folder)
    base=f'/api/peer-dock/field-series/{run_dir.name}/{ident}/'
    info={'capture':ident,'source_robot':robot,'evidence':base+'observation.json'}
    for key,name in (('packet',robot+'.npz'),('preview',robot+'.jpg')):
        if (folder/name).is_file():
            info[key]=base+name
    if not obs['board_valid']:
        return None,{**info,'reason':obs['reason']}
    try:
        goal=field.measured_goal(result,fleet)
    except (ValueError,KeyError,OSError) as exc:
        return None,{**info,'reason':str(exc)}
    expires=obs['received_monotonic_ns']/1e9+MAX_AGE_S-obs['rgb_age_s']
    return goal,{**info,'valid':True,'expires_monotonic_s':expires}


class PairedAttempt:
    """Return bounded requests to the Tank operator's leased command loop."""

    prompt = "paired_dock"

    def __init__(self, run_id, condition, spec, fixture, fleet):
        if condition not in {"selective", "local_scan", "sequential"}:
            raise ValueError(f"Unknown physical docking condition: {condition}")
        self.sensing_end_s = spec["sensing_budget_s"]
        if condition == "sequential":
            donor_s = spec["donor_budget_s"]
            if not math.isfinite(donor_s) or not 0 < donor_s <= spec["total_budget_s"] - self.sensing_end_s:
                raise ValueError("Invalid post-scan donor budget")
            self.sensing_end_s += donor_s

        self.id, self.condition, self.spec, self.fleet = run_id, condition, spec, fleet
        self.start = time.monotonic()
        self.run_dir = SERIES.parent / run_id
        self.run_dir.mkdir()
        # An already running local read may outlive its deadline. Its late result
        # has its own evidence folder and cannot hold up or replace the donor read.
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=2 if condition == "sequential" else 1)
        self.future = None
        self.driver = None
        self.attempts = 0
        self.pending_capture = None
        self.peer_requests = 0
        self.lock = threading.RLock()
        self.done = False
        self.active = True
        self.events = []
        self.samples = []
        self.phase = "initial"
        self.phase_events = [{"phase": "initial", "at_s": 0.0}]
        self.measured_goal = None
        self.heading = wrap(math.radians(fixture["tank"]["outward_deg"]) + math.pi)
        self.frame_id = fixture["tank"]["map_frame_id"]
        try:
            self.submit("tank")
        except Exception as exc:
            # start() still owns the ledger lock here. The first tick or STOP
            # persists the terminal record after the registration has returned.
            self.set_phase("capture_error", time.monotonic() - self.start, error=str(exc))

    def set_phase(self, phase, age, **evidence):
        self.phase = phase
        self.phase_events.append({"phase": phase, "at_s": age, **evidence})

    def submit(self, robot):
        sequence = self.attempts + 1
        capture = f"{sequence:03d}-{robot}"
        future = self.pool.submit(observe_one, robot, self.run_dir, sequence, self.fleet)
        self.attempts, self.pending_capture, self.future = sequence, capture, future
        if robot == "rosmaster" and not self.peer_requests:
            self.peer_requests = 1
            self.set_phase("peer", time.monotonic() - self.start, capture=capture)

    def finish(self, reason, **evidence):
        with self.lock:
            if self.done:
                return
            self.done = True
            self.active = False
            age = time.monotonic() - self.start
            self.set_phase("finished", age, reason=reason, **evidence)
            self.pool.shutdown(wait=False, cancel_futures=True)
            controller_endpoint = None
            if self.driver:
                try:
                    if self.driver.active:
                        self.driver.cancel(reason)
                    controller_endpoint = self.driver.status()
                except Exception as exc:
                    # Keep the request and STOP evidence even if the drive trace failed to close.
                    controller_endpoint = {"error": str(exc)}
            terminal(self.id, {
                "reason": reason, "finished": time.time(), "seconds": age,
                "observations": self.events, "command_requests": self.samples,
                "consumed_goal": self.measured_goal, "unconsumed_capture": self.pending_capture,
                "peer_requests": self.peer_requests, "phase_events": self.phase_events,
                "controller_endpoint": controller_endpoint,
                "drive_episode_id": self.driver.episode.id if self.driver and self.driver.episode else None,
                "scope": "Controller requests only. Physical endpoint requires an independent manual measurement.",
            })

    def cancel(self, reason="operator_stop"):
        self.finish(reason)

    def status(self):
        details = self.driver.status() if self.driver else {"message": "поиск", "state": "sensing"}
        return {**details, "active": self.active, "message": f"{self.condition}: " + details["message"], "prompt": self.prompt}

    def sense(self, age, frame):
        if age >= self.sensing_end_s:
            self.finish("no_measurement_before_deadline")
            return
        if (self.condition == "sequential" and self.phase in {"initial", "local_scan"}
                and age >= self.spec["sensing_budget_s"]):
            self.future.cancel()
            self.set_phase("hold_for_peer", age, discarded_capture=self.pending_capture)
            self.future = self.pending_capture = None
            # TankSource sends this tick's zero before the next tick can submit a donor read.
            return
        if self.phase == "hold_for_peer":
            self.submit("rosmaster")
            return
        if not self.future.done():
            return

        capture = self.pending_capture
        self.pending_capture = None
        try:
            goal, info = self.future.result()
        except Exception as exc:
            goal, info = None, {"reason": str(exc)}
        if goal and (time.monotonic() > info["expires_monotonic_s"] or goal["map_frame_id"] != frame):
            goal = None
            info.update(valid=False, reason="pose expired before operator controller consumed it")
        self.events.append({"at_s": age, "phase": self.phase, "capture": capture, **info})
        if goal:
            self.measured_goal = goal
            self.driver = field.operator_drive(goal, self.fleet)
            self.set_phase("docking", age, capture=capture)
        elif self.phase == "peer" or self.condition == "selective":
            self.submit("rosmaster")
        else:
            if self.phase == "initial":
                self.set_phase("local_scan", age)
            self.submit("tank")

    def command(self, rgb):
        with self.lock:
            if self.done:
                return [0., 0.]
            if self.phase == "capture_error":
                self.finish("controller_error")
                return [0., 0.]
            try:
                return self._command(rgb)
            except Exception as exc:
                self.finish("controller_error", error=str(exc))
                return [0., 0.]

    def _command(self, rgb):
        age = time.monotonic() - self.start
        pose, _, frame = field.real_pose(self.fleet, "tank")
        scan = self.fleet.scan("tank")
        if pose is None or frame != self.frame_id or scan is None:
            self.finish("localization_or_lidar_lost")
            return [0., 0.]
        if age >= self.spec["total_budget_s"]:
            self.finish("total_deadline")
            return [0., 0.]
        if self.driver is None:
            self.sense(age, frame)
        if self.driver:
            v, w = self.driver.command(rgb)
            if not self.driver.active:
                self.finish(self.driver.state)
        elif self.phase == "local_scan":
            # Rotate only on a cleared footprint. Translation stays zero throughout the scan.
            if len(scan) == 0 or np.linalg.norm(scan, axis=1).min() < RADIUS["tank"] + self.spec["scan_clearance_m"]:
                self.finish("unsafe_local_turn_clearance")
                return [0., 0.]
            limit = self.spec["scan_max_turn_rad_s"]
            turn = np.clip(2 * wrap(self.heading - pose[2]), -limit, limit)
            v, w, why = guard(scan, "tank", 0., float(turn))
            if why and abs(turn) > .05 and w == 0.:
                self.finish("local_turn_blocked_by_lidar")
                return [0., 0.]
        else:
            v, w = 0., 0.
        v = float(np.clip(v, -self.spec["max_drive_m_s"], self.spec["max_drive_m_s"]))
        w = float(np.clip(w, -self.spec["max_drive_turn_rad_s"], self.spec["max_drive_turn_rad_s"]))
        if self.active:
            self.samples.append([round(age, 3), v, w])
        return [v, w]


def start(control,session,owner,fleet,*,fixture_restored):
    if not fixture_restored:
        raise ValueError('Перед попыткой восстановите размеченные позиции цели, экрана и обеих машин')
    epoch=field.operator_session(control,session,owner)
    before=state()
    layout,condition=next_slot(before)
    if condition not in ('selective','local_scan','sequential'):
        raise ValueError('В назначении неизвестное условие полевой серии')
    poses=check_position(before,layout,fleet)
    with fleet_config.locked(),control.lock:
        s=json.loads(SERIES.read_text())
        if len(s['attempts'])!=len(before['attempts']) or next_slot(s)!=[layout,condition]:
            raise ValueError('Попытка уже была начата другим действием')
        if field.operator_session(control,session,owner)!=epoch:
            raise PermissionError('Сессия изменилась')
        if fleet.scan('tank') is None:
            raise ValueError('Нет свежего лидара Tank')
        ident=uuid.uuid4().hex
        s['attempts'].append({'id':ident,'layout':layout,'condition':condition,'slot':len(s['attempts']),
                              'start':time.time(),'start_poses':poses,'operator_confirmed_marked_fixture':True})
        field.write_json(SERIES,s)
        spec = s['protocol']
        if condition == 'sequential':
            spec = {**spec, 'donor_budget_s':s['sequential_supplement']['protocol']['donor_budget_s']}
        control.goal=PairedAttempt(ident,condition,spec,poses,fleet)
        return ident


def score(control,run_id,dx,dy,yaw_deg,stationary,intervention,note):
    if control.owner is not None or not control.stop_event.is_set():
        raise ValueError('Физический STOP обязателен до независимого замера')
    with fleet_config.locked(),control.lock:
        if control.owner is not None or not control.stop_event.is_set():
            raise ValueError('Для независимого замера требуется STOP')
        s=json.loads(SERIES.read_text())
        if not s['attempts'] or s['attempts'][-1]['id']!=run_id:
            raise ValueError('Выберите текущую попытку')
        row=s['attempts'][-1]
        if 'endpoint' in row:
            raise ValueError('Замер уже сохранён')
        from .peer_field_shadow import capture_hook
        capture_hook(SERIES.parent/run_id/'001-tank',before_endpoint=True)
        if not note.strip() or any(v is None or not math.isfinite(v) for v in (dx,dy,yaw_deg)):
            raise ValueError('Нужны независимые замеры и источник (линейка, угломер или видео)')
        spec=s['protocol'];runtime=row.get('runtime',{})
        # A controller arrival is insufficient. Intervention or an interrupted/lost run never
        # earns a task success. A successful goal requires actual admitted perception evidence.
        measured=math.hypot(dx,dy)<spec['terminal_position_tolerance_m'] and abs(wrap(math.radians(yaw_deg)))<spec['terminal_yaw_tolerance_rad']
        terminal_reason=runtime.get('reason')
        completed=terminal_reason in {'arrived','total_deadline','no_measurement_before_deadline','blocked','no_path',
                                      'unsafe_local_turn_clearance','local_turn_blocked_by_lidar','timeout'}
        admitted=any(e.get('valid') for e in runtime.get('observations',[]))
        valid=completed and admitted
        row['endpoint']={'x_error_m':dx,'y_error_m':dy,'heading_error_deg':yaw_deg,'stationary_half_second':stationary,
                         'operator_intervention':intervention,'stop_reason':control.last_stop_reason,'measurement_source':note.strip(),'at':time.time(),
                         'protocol_completed':completed,'perception_admitted':admitted,'independent_geometry_pass':measured,
                         'valid_run':valid,'success':bool(valid and measured and stationary and not intervention)}
        field.write_json(SERIES,s)
        return row['endpoint']



def report():
    s=state()
    outcomes={}
    for condition in dict.fromkeys(method for _,method in checked_order(s)):
        rows=[r for r in s['attempts'] if r['condition']==condition]
        measured=[r['endpoint'] for r in rows if 'endpoint' in r]
        outcomes[condition]={'started':len(rows),'measured':len(measured),'independent_successes':sum(e.get('success') is True for e in measured)}
    calibration=json.loads(field.CALIBRATION.read_text()) if field.CALIBRATION.is_file() else {}
    prerequisites={r:{'verified_current':bool(calibration.get(r,{}).get('verified') and
                    calibration[r].get('valid_until',0)>time.time())} for r in field.ROBOTS}
    return {**s,'outcomes':outcomes,'calibration':prerequisites,
            'effective_order':checked_order(s),'paired':peer_field_outcomes.paired_outcomes(s)}
