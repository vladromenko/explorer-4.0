"""Failure fixtures complement, never substitute for, the real MuJoCo/browser run."""
import json
import time
import uuid
import pytest
from explorer4 import catalog,resources
from explorer4.cognitive import run,store,registry,broker


@pytest.fixture
def runtime(tmp_path,monkeypatch):
    for module in (catalog,resources,store,run):monkeypatch.setattr(module,'DATA',tmp_path)
    catalog.initialize();store.initialize()
    work=tmp_path/'jobs'/uuid.uuid4().hex;work.mkdir(parents=True)
    return work


class FakeSim:
    commands=[]
    outcome='success'
    local=False
    def __init__(self,work,seed,scene='workshop'):self.work=work;self.commands.clear()
    def request(self,command,**payload):
        self.commands.append(command)
        def camera(robot):
            image=self.work/(robot+'.png');image.write_bytes(b'explicit-nonimage-fixture')
            return {'robot':robot,'image':str(image),'simulation_time_s':0.,'measurement':{'target_visible':False,'detections':[],'screen_fraction':.12},
                    'packet':{'frame':'tank_start_map','target_xy_m':[.9,0.]} if self.local and robot=='tank' else None}
        if command=='snapshot':return {'scene':'fixture','seed':1,'model_sha256':'f'*64,
            'recipient':camera('tank'),'donor':camera('rosmaster'),
            'conditions':{'recipient_stationary':True,'fixed_scene':True}}
        if command in ('scan','observe'):
            return {**camera('rosmaster'),'helper_outcome':self.outcome,'recipient_held':True,
                'packet':{'frame':'tank_start_map','target_xy_m':[.9,0.]},
                'conditions':{'recipient_stationary':True,'fixed_scene':True,'target_observed_by_helper':self.outcome=='success'}}
        if command == 'local_scan':
            assert payload['packet'] is None
            return {'helper':'unknown','recipient':'failure','task':'failure','version':'fixture-v1'}
        if command in ('dock','local_dock'):
            assert payload['packet']['target_xy_m']==[.9,0.]
            return {'helper':'success','recipient':'success','task':'success','version':'fixture-v1'}
        raise ValueError('unexpected command')
    def close(self):pass


def test_cancel_during_model_never_dispatches_simulated_motion(runtime,monkeypatch):
    monkeypatch.setattr(run,'Sim',FakeSim)
    def late(work,request):
        mission_id=json.loads((work/'mission.json').read_text())['mission_id'];broker.cancel(mission_id)
        return {'proposal':{'choice':'scan_then_dock','reason':'late fixture'}}
    monkeypatch.setattr(run,'model_proposal',late)
    with pytest.raises(ValueError,match='Late model'):run.execute({'comparison':'M1','seed':1},runtime)
    assert FakeSim.commands==['snapshot']
    assert not store.cases()


def test_failed_observation_never_starts_recipient(runtime,monkeypatch):
    monkeypatch.setattr(run,'Sim',FakeSim);monkeypatch.setattr(FakeSim,'outcome','failure')
    with pytest.raises(ValueError,match='target visibility'):run.execute({'comparison':'M0','seed':1},runtime)
    assert FakeSim.commands==['snapshot','observe']
    assert store.cases()[0]['status']=='contradicted'
    assert store.cases()[0]['helper_outcome']=='failure'
    mission_id=json.loads((runtime/'mission.json').read_text())['mission_id']
    assert store.mission(mission_id)['outcome']=='unknown'
    assert store.events(mission_id)[-1]['kind']=='deterministic_stop'


def test_m0_is_nonmodel_nontraining_and_case_survives(runtime,monkeypatch):
    monkeypatch.setattr(run,'Sim',FakeSim)
    monkeypatch.setattr(run,'model_proposal',lambda *_:pytest.fail('M0 must not call model'))
    result=run.execute({'comparison':'M0','seed':1},runtime)
    assert result['training_started'] is False and result['physical_robot_access'] is False
    assert result['proposal']['backend']=='local_visibility_rule_v1'
    assert result['helper']==result['recipient']==result['task']=='success'
    assert store.cases()[0]['status']=='candidate'


def test_completed_mission_releases_claims_for_immediate_next_run(runtime,monkeypatch):
    monkeypatch.setattr(run,'Sim',FakeSim)
    run.execute({'comparison':'M0','seed':1},runtime)
    with catalog.connect() as db:assert db.execute('SELECT count(*) FROM cognitive_claims').fetchone()[0]==0
    second=runtime.parent/uuid.uuid4().hex;second.mkdir()
    result=run.execute({'comparison':'M0','seed':2},second)
    assert result['outcome']=='success'


def test_recipient_with_local_measurement_skips_donor(runtime,monkeypatch):
    monkeypatch.setattr(run,'Sim',FakeSim)
    monkeypatch.setattr(FakeSim,'local',True)
    result=run.execute({'comparison':'M0','seed':1},runtime)
    assert FakeSim.commands==['snapshot','local_dock']
    assert (result['helper'],result['outcome'])==('not_requested','success')

def test_selector_dispatches_active_onboard_scan_from_local_image(runtime,monkeypatch):
    from explorer4 import peer_request_policy
    monkeypatch.setattr(run, 'Sim', FakeSim)
    # An inert test double checks dispatch only. No fitting or model publication.
    model = {'schema':'test','plan_sha256':'d'*64,'mean':[0.]*5,'scale':[1.]*5,
             'coef':[0.]*5,'intercept':0.,'threshold':1.}
    monkeypatch.setattr(peer_request_policy,'load_model',lambda _:model)
    result=run.execute({'comparison':'peer_learned','seed':1,'peer_model_sha256':'e'*64},runtime)
    assert FakeSim.commands == ['snapshot','local_scan']
    assert result['outcome'] == 'failure'
    assert result['proposal']['features'] == [0.,0.,0.,0.,.12]
    assert result['proposal']['model_sha256'] == 'e'*64
    assert not store.cases()
