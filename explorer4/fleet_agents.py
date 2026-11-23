"""The six agent roles of docs/AGENTIC_ADDENDUM.md, working inside the swarm.

Roles are bounded program parts with their own state and decision log, not separate LLM processes
(addendum §2). They share the research memory of explorer4/cognitive (evidence, assistance cases,
independent verification, retrieval with recipient compatibility — the article's hypothesis):

  MissionCoordinator   command -> plan of REGISTERED fleet skills with executor, preconditions and
                       how each step is verified; unknown skills/robots or missing preconditions are
                       rejected with the concrete reason (the plan is checked by code, not trusted).
  SceneObserver        every sighting becomes ObservationEvidence (robot, time, map frame,
                       uncertainty, expiry); the same object seen in two places is a conflict.
  AssistanceBroker     when a step fails it chooses among at most three admissible options —
                       retry, another robot looks again (observation help), human — using memory
                       cases that are compatible with the recipient's current skill version, with a
                       fixed baseline when memory has nothing; at most 2 helps per mission.
  MemoryCurator        stores each help as an AssistanceCase candidate; status changes only through
                       the verifier's measured outcomes (supported_in_scope / contradicted).
  OutcomeVerifier      separate helper / recipient / task outcomes from measurements (a new
                       sighting, the arm's holding check, «Забрал»), never from the planner's text.
  LearningAndExperimentCurator  what data the next training needs: recorded blocks vs targets,
                       MuJoCo scene alignment, training jobs and their «Допуск к роботу».

Motion stays with the deterministic executors (Explore/GoTo/DriveTo/ArmSkills/Handoff, STOP,
limits); no role sends a motor command.
"""
import collections
import hashlib
import json
import threading
import time
import uuid

from .cognitive import store
from .cognitive.schemas import SkillCard

ROLES = ['MissionCoordinator', 'SceneObserver', 'AssistanceBroker', 'MemoryCurator', 'OutcomeVerifier',
         'LearningAndExperimentCurator']
TITLES = {'MissionCoordinator': 'Координатор задачи', 'SceneObserver': 'Наблюдатель сцены',
          'AssistanceBroker': 'Выбор помощи', 'MemoryCurator': 'Память помощи', 'OutcomeVerifier': 'Проверка результата',
          'LearningAndExperimentCurator': 'Данные и обучение'}
MAX_HELPS = 2
EVIDENCE_TTL_S = 3600.


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def _file_hash(relative):
    from .paths import ROOT
    return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


# ---------------------------------------------------------------------- fleet skill registry
def fleet_skills():
    """Cards of the skills the swarm can execute; the version changes with the code/config."""
    specs = [
        ('rosmaster', 'explore', 'explorer4/explore.py', 'observation', ['map_explored', 'objects_recorded']),
        ('tank', 'explore', 'explorer4/explore.py', 'observation', ['map_explored', 'objects_recorded']),
        ('rosmaster', 'search', 'explorer4/explore.py', 'observation', ['object_sighted_after_start']),
        ('tank', 'search', 'explorer4/explore.py', 'observation', ['object_sighted_after_start']),
        ('rosmaster', 'approach', 'explorer4/goto.py', 'geometric', ['within_arm_reach']),
        ('tank', 'approach', 'explorer4/goto.py', 'geometric', ['near_object']),
        ('rosmaster', 'pick_floor', 'explorer4/rosmaster_arm.py', 'geometric', ['holding_object']),
        ('rosmaster', 'deliver', 'explorer4/drive.py', 'geometric', ['at_handover_spot']),
        ('rosmaster', 'place', 'explorer4/rosmaster_arm.py', 'geometric', ['object_on_pad']),
        ('so101', 'handover', 'explorer4/so101_handoff.py', 'manual', ['person_took_object']),
    ]
    cards = {}
    from .rosmaster_arm import learned_pick_job
    learned = learned_pick_job()
    for robot, name, source, kind, post in specs:
        ident = f'{robot}.fleet_{name}.v1'
        policy = None
        if (robot, name) == ('rosmaster', 'pick_floor') and learned is not None:
            # a learned grasp is a different recipient: its memory scope is bound to these weights
            from .deploy_gate import latest
            policy, kind = latest(learned)['checkpoint_bundle_sha256'], 'learned'
        version = _hash({'code': _file_hash(source), 'skill': name, 'policy': policy})
        cards[ident] = SkillCard(
            skill_id=ident, robot=robot, version=version, kind=kind, source_ref=source, profile='fleet',
            policy_sha256=policy or version, camera_sha256=camera_fingerprint(robot),
            calibration_sha256=calibration_fingerprint(robot),
            state_schema={'frame': 'fleet_map'}, action_schema={'executor': source},
            goals=['named_object'], cameras=['front' if robot != 'so101' else 'wrist'],
            verified_scope=['fleet swarm executor; scripted/geometric, not a learned policy'],
            preconditions=['robot_connected', 'localized_on_shared_map'] if robot != 'so101' else ['handover_poses_taught'],
            postconditions=post, resources=[robot], timeout_s=120., cancel_method='swarm STOP / goal cancel',
            verifier='explorer4.fleet_agents.OutcomeVerifier', sim_admission='available', real_admission='available',
            limitation='Program skill of the fleet; its success on the real robot is measured, not assumed')
    return cards


def camera_fingerprint(robot):
    """What the recipient's camera is: lidar/camera mounts used by the fleet + the robot's camera
    contract (resolution, rate). A changed mount or camera gives another scope for the help memory."""
    from .fleet_map import CAMERA, MOUNTS
    from .profiles import PROFILES
    contract = {n: {k: p.get(k) for k in ('camera', 'image_shape', 'fps')} for n, p in PROFILES.items() if p.get('robot') == robot}
    return _hash({'robot': robot, 'camera_mount': CAMERA.get(robot), 'lidar_mounts': MOUNTS.get(robot), 'contract': contract})


def calibration_fingerprint(robot):
    """Hash of the robot's calibration files on Homebrain, or None when there are none."""
    from .paths import DATA
    files = {'so101': ['calibration/follower.json', 'calibration/leader.json'],
             'rosmaster': ['provenance/rosmaster-bridge-current/explorer3/config/controller-calibration.json']}.get(robot, [])
    present = [DATA / f for f in files if (DATA / f).is_file()]
    return hashlib.sha256(b''.join(p.read_bytes() for p in present)).hexdigest() if present else None


class Role:
    def __init__(self, name):
        self.name, self.title = name, TITLES[name]
        self.state = 'ждёт'
        self.log = collections.deque(maxlen=12)

    def note(self, state, message, **data):
        self.state = state
        self.log.append({'at': time.time(), 'state': state, 'message': message, **data})

    def status(self):
        last = self.log[-1] if self.log else None
        return {'role': self.name, 'title': self.title, 'state': self.state,
                'last': None if last is None else last['message'], 'log': list(self.log)}


class FleetAgents:
    COMPARISONS = ('M0', 'M2', 'M3')    # no memory / memory without recipient check / with it (RESEARCH_PROTOCOL AG2)

    def __init__(self, swarm, domain=lambda: 'real', comparison='M3'):
        self.swarm = swarm
        self.domain = domain
        if comparison not in self.COMPARISONS:
            raise ValueError('Unknown comparison')
        self.comparison = comparison
        self.frozen = False                # experiment test series: memory is read, never written
        self.roles = {name: Role(name) for name in ROLES}
        self.plan = []
        self.mission = None
        self.helps = 0
        self.lock = threading.Lock()
        self.skills = None

    # ------------------------------------------------------------------ helpers
    def role(self, name):
        return self.roles[name]

    def card(self, robot, skill):
        if self.skills is None:
            self.skills = fleet_skills()
        ident = f'{robot}.fleet_{skill}.v1'
        if ident not in self.skills:
            raise ValueError(f'Нет такого навыка: {ident}')
        return self.skills[ident]

    def status(self):
        return {'roles': [r.status() for r in self.roles.values()], 'plan': list(self.plan), 'comparison': self.comparison,
                'mission': self.mission, 'helps': self.helps, 'domain': self.domain()}

    # ------------------------------------------------------------------ MissionCoordinator
    def start(self, kind, prompt, robots):
        """Plan of registered skills for the command; raises with the reason when not executable."""
        c = self.role('MissionCoordinator')
        self.skills = None                       # re-read: code or an admitted learned policy may have changed
        self.mission = uuid.uuid4().hex
        self.helps = 0
        mobile = [r for r in robots]
        if not mobile:
            c.note('отказ', 'Нет доступного мобильного робота')
            raise RuntimeError('Ни один мобильный робот не доступен')
        steps = []
        if kind == 'explore':
            steps = [(r, 'explore', 'осмотр комнаты, предметы в общую память') for r in mobile]
        elif kind == 'find':
            steps = [(r, 'search', f'найти «{prompt}»') for r in mobile]
        elif kind == 'goto':
            steps = [(mobile[0], 'approach', f'подъехать к «{prompt}»')]
        elif kind == 'fetch':
            if 'rosmaster' not in mobile:
                c.note('отказ', 'Принести может только ROSMASTER: у Tank нет руки')
                raise RuntimeError('Принести может только ROSMASTER: он не подключён или не выбран')
            steps = [(r, 'search', f'найти «{prompt}», если места нет в памяти') for r in mobile]
            steps += [('rosmaster', 'approach', f'подъехать к «{prompt}»'), ('rosmaster', 'pick_floor', f'взять «{prompt}» с пола')]
            if getattr(self.swarm, 'task_context', {}).get('terminal_goal') is not None:
                steps += [('rosmaster', 'deliver', 'отвезти в отмеченную зону на полу'),
                          ('rosmaster', 'place', 'положить и независимо проверить предмет в зоне')]
            else:
                steps += [('rosmaster', 'deliver', 'отвезти к SO-101'), ('rosmaster', 'place', 'положить на площадку'),
                          ('so101', 'handover', 'взять с площадки и протянуть человеку')]
        else:
            c.note('отказ', f'Неизвестная команда: {kind}')
            raise ValueError('Неизвестная команда')
        self.plan = []
        for i, (robot, skill, text) in enumerate(steps):
            card = self.card(robot, skill)          # unknown robot/skill -> error, never invented
            if card.kind == 'learned':
                text += ' (обученная модель, допуск пройден)'
            postconditions = card.postconditions
            if getattr(self.swarm, 'task_context', {}).get('terminal_goal') is not None:
                postconditions = {'deliver': ['at_floor_zone_approach'], 'place': ['released_object_observed_inside_zone']}.get(skill, postconditions)
            self.plan.append({'id': f's{i + 1}', 'robot': robot, 'skill': card.skill_id, 'version': card.version[:12], 'kind': card.kind,
                              'text': text, 'verify': ', '.join(postconditions), 'status': 'ждёт'})
        c.note('план', f'{len(self.plan)} шагов из зарегистрированных навыков: ' +
               ' → '.join(f'{p["robot"]}:{p["skill"].split(".")[1].removeprefix("fleet_")}' for p in self.plan), mission=self.mission)
        return self.plan

    def step(self, skill, robot, status, note=''):
        for p in self.plan:
            if p['robot'] == robot and p['skill'].split('.')[1] == 'fleet_' + skill:
                p['status'] = status
                if note:
                    p['note'] = note
                return

    def finish(self, outcome, message):
        self.role('MissionCoordinator').note('готово' if outcome in ('done', 'explored') else outcome, message)
        self.role('LearningAndExperimentCurator').note('сводка', learning_summary())

    # ------------------------------------------------------------------ SceneObserver
    def sighting(self, item):
        """ObservationEvidence for a world-memory sighting; conflicts with an earlier place noted."""
        o = self.role("SceneObserver")
        if not item or not (item.get("room_xy") or item.get("identity")):
            return None
        observed = item.get("observation") or {}
        observed_at = item["at"]
        received = observed.get("received_timestamp_ns", int(observed_at * 1e9))
        payload = {
            "object": item["prompt"],
            "object_instance": item.get("object_instance"),
            "identity_evidence": item.get("identity"),
            "room_xy": item["room_xy"],
            "robot": item["robot"],
            "distance_m": item.get("distance"),
            "uncertainty_m": item.get("uncertainty_m"),
            "uncertainty_source": item.get("uncertainty_source", "legacy estimate"),
            "measured_error_bound_m": item.get("measured_error_bound_m"),
            "seen_at": observed_at,
            "map_frame_id": item.get("frame_id"),
            "source_pose": item.get("robot_pose"),
            "rgb": observed,
            "bbox_xyxy_px": item.get("bbox_xyxy_px"),
            "snapshot": item.get("snapshot"),
            "snapshot_sha256": item.get("snapshot_sha256"),
        }
        ident = "fleet:" + (
            item.get("sample_id")
            or store.digest([item["robot"], item["prompt"], observed_at, item["room_xy"]])
        )
        try:
            store.evidence([ident], fresh=False)  # already recorded (the same sighting)
            return ident
        except ValueError:
            pass
        artifact = {}
        if item.get("snapshot") and item.get("snapshot_sha256"):
            from . import world_memory

            path = (world_memory.SNAPSHOTS / item["snapshot"]).resolve()
            if path.is_relative_to(store.DATA.resolve()):
                artifact = {
                    "artifact_ref": str(path.relative_to(store.DATA.resolve())),
                    "artifact_sha256": item["snapshot_sha256"],
                }
        try:
            store.put_evidence(
                {
                    **artifact,
                    "id": ident,
                    "domain": self.domain(),
                    "robot": item["robot"],
                    "source": "fleet_scout_sam3" if self.domain() == "real" else "fleet_sim_camera",
                    "sample_id": ident,
                    "frame_id": item.get("frame_id") or "unversioned_room",
                    "camera_id": observed.get("optical_frame") or (item["robot"] + "/scout_rgb"),
                    "source_timestamp_ns": observed.get("source_timestamp_ns"),
                    "received_timestamp_ns": received,
                    "clock_domain": observed.get("receipt_clock", "homebrain_wall_receipt"),
                    "boot_id": observed.get("boot_id"),
                    "created_at": observed_at,
                    "expires_at": observed_at + EVIDENCE_TTL_S,
                    "units": {"room_xy": "m"} if item.get("room_xy") else {},
                    "status": "estimated" if item.get("room_xy") else "observed",
                    "quality": {
                        "score": item.get("score"),
                        "timing_basis": observed.get("timing_basis", "legacy_record_time"),
                        "sensor_acquisition_known": observed.get("source_timestamp_ns") is not None,
                    },
                    "content_sha256": store.digest(payload),
                    "payload": payload,
                }
            )
        except Exception as exc:
            o.note("ошибка", f"свидетельство не сохранено: {exc}")
            return None
        position = " · точка на карте " + str(item["room_xy"]) if item.get("room_xy") else ""
        o.note(
            "видит",
            f"{item['robot']} видит «{item.get('object_instance') or item['prompt']}»{position}",
            evidence=ident,
        )
        return ident

    def conflict(self, prompt, old_xy, new_xy):
        import math
        d = math.dist(old_xy, new_xy)
        if d > .5:
            self.role('SceneObserver').note('противоречие', f'«{prompt}» сместился на {d:.1f} м: прежнее место устарело')
        return d

    # ------------------------------------------------------------------ AssistanceBroker
    def assist(self, recipient, skill, prompt, reason, helpers, evidence_ids):
        """Choose help after a failed step. Returns {'option', 'donor', 'why', 'case'}."""
        b = self.role('AssistanceBroker')
        if self.helps >= MAX_HELPS:
            b.note('человек', f'Лимит помощи ({MAX_HELPS}) исчерпан: зову человека')
            return {'option': 'human', 'donor': None, 'why': 'лимит помощи', 'case': None}
        card = self.card(recipient, skill)
        found = {'accepted': [], 'rejected': []}
        if evidence_ids:
            try:
                found = store.retrieve('fleet_' + skill, reason, card, 'named_object', self.domain(), comparison=self.comparison)
            except Exception as exc:
                b.note('ошибка', f'память недоступна: {exc}')
        stats = collections.defaultdict(lambda: [0, 0])
        for a in found['accepted']:
            case = a['case']
            stats[case['assistance_type']][0] += case['status'] == 'supported_in_scope'
            stats[case['assistance_type']][1] += 1
        options = []
        donors = list(dict.fromkeys(h for h in helpers if h != recipient and h in ('tank', 'rosmaster')))
        options.extend(('observation', h) for h in donors)
        options.append(('recovery', recipient))
        options.append(('human', None))
        # a compatible case that the verifier contradicted is negative experience for that kind of help
        by_id = {c['id']: c for c in store.cases()} if found['rejected'] else {}
        contradicted = {by_id[r['id']]['assistance_type'] for r in found['rejected']
                        if r['id'] in by_id and r['reasons'] == ['Memory is contradicted']}

        def score(o):
            s, n = stats.get(o[0], (0, 0))
            base = {'observation': 2., 'recovery': 1., 'human': 0.}[o[0]]   # fixed baseline order
            return (s / n if n else 0.) * 3 + base - (2. if o[0] in contradicted else 0.)
        from .cognitive.action_value import observed_choice
        keys = {('ask:'+robot if kind=='observation' else kind): (kind, robot) for kind, robot in options}
        fallback_pair = max(options, key=score)
        fallback = next(k for k,pair in keys.items() if pair == fallback_pair)
        try:
            observed = store.evidence(evidence_ids, domain=self.domain()) if evidence_ids else []
        except ValueError:
            observed = []
        choice = observed_choice(observed, admissible=list(keys), fallback=fallback, domain=self.domain(),
                                 scope={"recipient":recipient,"skill":skill,"object":prompt,"reason":reason})
        option, donor = keys[choice["action"]]
        incompatible = len(found['rejected']) - sum(1 for r in found['rejected'] if r['reasons'] == ['Memory is contradicted'])
        why = (f'память: {len(found["accepted"])} совместимых случаев, {incompatible} отклонено как несовместимые с навыком получателя'
               + (f', опровергнуто: {", ".join(sorted(contradicted))}' if contradicted else '')
               if found['accepted'] or found['rejected'] else 'в памяти нет совместимых случаев — базовый порядок')
        if choice["source"] == "forecast":
            why = 'Выбрано по прогнозу исхода и цене доступных действий'
        self.helps += 1
        case = None
        if option != 'human' and evidence_ids:
            case = self._candidate(recipient, donor or recipient, skill, prompt, reason, option, evidence_ids)
        b.note(option, f'{recipient} не смог ({reason}): ' + {'observation': f'{donor} посмотрит ещё раз', 'recovery': f'{recipient} попробует снова',
                                                              'human': 'нужен человек'}[option] + f' · {why}', case=case)
        return {'option': {'observation': 'helper_observe', 'recovery': 'retry', 'human': 'human'}[option],
                'donor': donor, 'why': why, 'case': case, 'action_value':choice}

    def gaps(self, assessed, available):
        """MissionCoordinator: the recipient's knowledge gaps before acting and who can fill each."""
        from .knowledge import helpers_for
        c = self.role('MissionCoordinator')
        if not assessed['gaps']:
            c.note('знает', 'ROSMASTER знает и где предмет, и как его брать (' + assessed['skill'] + ')')
            return
        parts = [f'{g}: {assessed["reasons"][g]} → помощь: {", ".join(helpers_for(g, available + ["so101"]))}' for g in assessed['gaps']]
        c.note('пробелы', 'Чего не знает ROSMASTER — ' + '; '.join(parts))

    def knowledge_help(self, donor, recipient, prompt, item):
        """A knowledge transfer (donor measured/practised the object) as a help case; outcome later."""
        self.role('AssistanceBroker').note('knowledge', f'{donor} передаёт {recipient} знание о «{prompt}»: {item["params"]}')
        if self.frozen:
            return None
        payload = {'object': prompt, 'params': item['params'], 'source': item['source']}
        now = time.time()
        ident = f'fleet-knowledge:{item["id"]}'
        try:
            store.put_evidence({'id': ident, 'domain': self.domain(), 'robot': donor if donor in ('so101', 'rosmaster', 'tank') else 'so101',
                                'source': 'so101_station', 'sample_id': ident, 'frame_id': 'so101_table',
                                'received_timestamp_ns': int(now * 1e9), 'clock_domain': 'homebrain_wall', 'created_at': now,
                                'expires_at': now + EVIDENCE_TTL_S, 'status': 'observed', 'content_sha256': store.digest(payload),
                                'payload': payload})
        except Exception:
            return None
        return self._candidate(recipient, donor, 'pick_floor', prompt, 'grasp_knowledge_missing', 'knowledge', [ident])

    # ------------------------------------------------------------------ MemoryCurator / OutcomeVerifier
    def _candidate(self, recipient, donor, skill, prompt, reason, kind, evidence_ids):
        if self.frozen:
            return None
        card = self.card(recipient, skill)
        compat = {'recipient_skill_id': card.skill_id, 'recipient_version': card.version, 'policy_sha256': card.policy_sha256,
                  'camera_sha256': card.camera_sha256, 'calibration_sha256': card.calibration_sha256, 'domain': self.domain(),
                  'goal_id': 'named_object', 'checked_conditions': ['recipient_localized', 'object_named'],
                  'unknown_conditions': [], 'evidence_ids': evidence_ids[:4]}
        ident = f'fleet-case:{uuid.uuid4().hex[:24]}'
        value = {'id': ident, 'task': 'fleet_' + skill, 'effect': reason, 'domain': self.domain(), 'donor': donor, 'recipient': recipient,
                 'donor_episode': f'{self.mission}:{donor}', 'recipient_episode': f'{self.mission}:{recipient}', 'reason': reason,
                 'before_evidence_ids': evidence_ids[:4], 'compatibility': compat, 'assistance_type': kind,
                 'expected_effect': f'свежее положение «{prompt}», затем {recipient} выполняет {skill}',
                 'actions_provenance': 'observation' if kind in ('observation', 'knowledge') else 'scripted', 'actual_effect': {'object': prompt}}
        try:
            store.add_case(value)
        except Exception as exc:
            self.role('MemoryCurator').note('ошибка', f'случай не сохранён: {exc}')
            return None
        self.role('MemoryCurator').note('кандидат', f'новый случай помощи {donor}→{recipient} ({kind}) — кандидат до проверки', case=ident)
        return ident

    def verify(self, case_id, helper, recipient, task, measurement):
        """Independent outcome from measurements; updates the case status in the research memory."""
        v = self.role('OutcomeVerifier')
        if case_id is None:
            return None
        now = time.time()
        case = next((c for c in store.cases() if c['id'] == case_id), None)
        if case is None:
            return None
        episode = f'{self.mission}:verify'
        payload = {'helper': helper, 'recipient': recipient, 'task': task, 'episode': episode,
                   'compatibility_sha256': store.digest(case['compatibility']), 'measurement': measurement}
        ident = f'fleet-verify:{uuid.uuid4().hex[:24]}'
        try:
            store.put_evidence({'id': ident, 'domain': case['domain'], 'robot': case['recipient'], 'source': 'fixed_outcome_verifier',
                                'sample_id': ident, 'frame_id': 'fleet_map', 'received_timestamp_ns': int(now * 1e9),
                                'clock_domain': 'homebrain_wall', 'created_at': now, 'expires_at': now + EVIDENCE_TTL_S,
                                'status': 'observed', 'content_sha256': store.digest(payload), 'payload': payload})
            status = store.verify_case(case_id, episode, helper=helper, recipient=recipient, task=task, evidence_ids=[ident],
                                       verifier_version='fleet_agents.v1')
        except Exception as exc:
            v.note('ошибка', f'проверка не записана: {exc}')
            return None
        v.note('проверено', f'помощник: {helper}, получатель: {recipient}, задача: {task} · {measurement}', case=case_id)
        self.role('MemoryCurator').note(status, f'случай {case_id[-8:]}: {status}')
        return status


def learning_summary():
    """Recorded blocks vs targets, MuJoCo alignment source and gate verdicts (LearningAndExperimentCurator)."""
    try:
        from . import catalog
        from .paths import ROOT
        from .datasets import eligible
        real = {p: len(eligible(p)) for p in ('rosmaster_pick_place', 'so101_pick_place')}   # only this block's demos
        align = json.loads((ROOT / 'configs/sim-alignment.json').read_text())
        src = {k: v.get('source', '?') for k, v in align.items() if isinstance(v, dict)}
        from .deploy_gate import GATES, latest
        gates = [latest(p.stem) for p in sorted(GATES.glob('*.json'),key=lambda p:p.stat().st_mtime)[-3:]]
        ready = sum(g['verdict'] == 'ready' for g in gates)
        return (f'показы: ROSMASTER {real["rosmaster_pick_place"]}/50, SO-101 {real["so101_pick_place"]}/50 · '
                f'сцена MuJoCo: {", ".join(f"{k}={v}" for k, v in src.items())} · допущено моделей: {ready} из {len(gates)} проверенных')
    except Exception as exc:
        return f'нет данных: {exc}'
