"""«Допуск к роботу»: the checks that decide whether a checkpoint may drive a real arm."""
import json
import types

import pytest

from explorer4 import deploy_gate


class _F:
    def __init__(self, *shape):
        self.shape = shape


def _core(state=6, action=6, cams=('observation.images.wrist',)):
    feats = {'observation.state': _F(state), **{c: _F(3, 480, 640) for c in cams}}
    return types.SimpleNamespace(cfg=types.SimpleNamespace(input_features=feats, output_features={'action': _F(action)}),
                                 image_keys=list(cams))


def test_contract_matches_robot_or_says_what_differs(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy_gate, 'DATA', tmp_path)
    from explorer4.profiles import profile
    cfg = profile('so101_pick_place')
    assert deploy_gate.check_contract(_core(),'so101_pick_place','j',cfg)['status']=='fail'
    out=tmp_path/'jobs/j/train/meta'
    out.mkdir(parents=True)
    (out/'info.json').write_text(json.dumps({'fps':cfg['fps'],'features':{
        'action':{'names':cfg['channels']},'observation.state':{'names':cfg['channels']},
        'observation.images.wrist':{'shape':[480,640,3]}}}))
    assert deploy_gate.check_contract(_core(),'so101_pick_place','j',cfg)['status']=='pass'
    bad=deploy_gate.check_contract(_core(state=5,cams=('observation.images.front',)), 'so101_pick_place','j',cfg)
    assert bad['status']=='fail' and 'observation.state' in bad['message'] and 'wrist' in bad['message']
    assert deploy_gate.check_contract(_core(),'so101_pick_place','j',{**cfg,'units':['m/s']*6})['status']=='fail'


def test_trial_needs_scoped_current_report_and_processors(tmp_path,monkeypatch):
    monkeypatch.setattr(deploy_gate,'GATES',tmp_path)
    plan={'source_id':'job1','checkpoint':'ck','profile':'rosmaster_pick_place','instruction':'pick up the cube'}
    with pytest.raises(PermissionError):
        deploy_gate.require(plan)
    out=tmp_path/'job1.json'
    out.write_text(json.dumps({'verdict':'ready','meaning':'legacy'}))
    with pytest.raises(PermissionError,match='stale'):
        deploy_gate.require(plan)
    monkeypatch.setattr(deploy_gate,'bundle_identity',lambda _: {'checkpoint_bundle_sha256':'bundle'})
    monkeypatch.setattr(deploy_gate,'scene_revision',lambda _: 'revision')
    monkeypatch.setattr(deploy_gate,'probe_geometry',lambda _: {'xml_sha256':'xml'})
    report={'version':2,'verdict':'ready','scope':{'real_profile':plan['profile'],'instruction':plan['instruction']},
            'checkpoint_bundle_sha256':'old','development':{'episodes':['v']},'thresholds':deploy_gate.thresholds(),
            'sim_protocol':{'scene':'rosmaster_floor_pick_sim','scene_revision':'revision','xml_sha256':'xml'}}
    out.write_text(json.dumps(report))
    with pytest.raises(PermissionError,match='процессоры'):
        deploy_gate.require(plan)
    out.write_text(json.dumps({**report,'checkpoint_bundle_sha256':'bundle'}))
    assert deploy_gate.require(plan)['verdict']=='ready'
    with pytest.raises(PermissionError,match='instruction'):
        deploy_gate.require({**plan,'instruction':'place in box'})


def test_development_excludes_train_test_and_derived_relatives(tmp_path,monkeypatch):
    real='rosmaster_pick_place'
    rows=[]
    for ident in ('train','test','v1','v2','v3'):
        root=tmp_path/ident
        root.mkdir()
        meta={'domain':'real','synthetic':False,'command_source':'human','profile':{'task':'pick up the cube'}}
        if ident=='v2':
            meta['source_episode']='test'
        (root/'provenance.json').write_text(json.dumps(meta))
        rows.append({'id':ident,'profile':real,'session':ident,'scene':ident if ident!='v3' else 'train',
                     'dataset':str(root),'sha256':ident,'outcome':'success','excluded':False,'category':'demonstration'})
    frozen={'domain':'real','profile':real,'splits':dict(train=rows[:1],test=rows[1:2],validation=rows[2:])}
    monkeypatch.setattr(deploy_gate.datasets,'load_plan',lambda ident,verify: frozen if not verify else pytest.fail('reserved data accessed'))
    monkeypatch.setattr(deploy_gate.catalog,'rows',lambda _:rows)
    monkeypatch.setattr(deploy_gate.datasets,'fingerprint',lambda path:'v1' if str(path).endswith('v1') else pytest.fail('reserved data read'))
    job={'id':'job','profile':real,'config':json.dumps({'plan_id':'plan'})}
    held,meta=deploy_gate.development_selection(job,deploy_gate.scope_for(job))
    assert [e['id'] for e in held]==['v1'] and set(meta['excluded'])=={'v2','v3'}
    with pytest.raises(ValueError,match='Select a frozen'):
        deploy_gate.development_selection({**job,'profile':'rosmaster_floor_pick_sim'},deploy_gate.scope_for(job))


def test_semantics_of_native_velocity_and_gripper(monkeypatch):
    import numpy as np
    core=types.SimpleNamespace(cfg=types.SimpleNamespace(n_action_steps=100))
    monkeypatch.setattr(deploy_gate,'replay_real',lambda *args:(np.array([[0.0,0.2]]),np.array([[0.1,0.0]]),[0.001]))
    result=deploy_gate.replay_checks(core,[{}],'tank_dock',deploy_gate.thresholds())
    assert result['real_holdout']['status']=='fail' and result['first_step']['status']=='fail'
    assert result['real_holdout']['units']==['m/s','rad/s']


def test_cotraining_adds_sim_only_to_train_and_caps_frames(monkeypatch, tmp_path):
    from explorer4 import datasets
    from explorer4.alignment_lineage import configuration_record
    def episode(ident, real=False, parent=None, alignment=None):
        d=tmp_path/ident
        d.mkdir()
        model={'alignment':alignment or configuration_record({'source':'instructions'})}
        raw={'domain':'real' if real else 'sim','synthetic':not real,'hardware':{'model':model},'source_episode':parent}
        (d/'provenance.json').write_text(json.dumps(raw))
        (d/'research.jsonl').write_text(json.dumps({'command_source':'scripted_expert'})+'\n')
        return {'id':ident,'dataset':str(d),'frames':100,'created':int(ident[-1]),'session':ident+'-s','scene':ident+'-p',
                'profile':'so101_pick_place' if real else 'so101_handover_sim'}
    train = episode('d0',True)
    held = episode('held1',True)
    other = episode('other2', True)
    middle = episode('derived3',True,parent=held['id'])
    alignment=configuration_record({'source':'measured','object_x_m':[.17,.25],'alignment_provenance':{
        'mode':'frozen_train','plan_id':'other-plan','source_episodes':[{'id':middle['id'],'sha256':'m'}]}})
    plan={'domain':'real','profile':'so101_pick_place','splits':{'train':[{'id':middle['id'],'sha256':'m'}]}}
    monkeypatch.setattr(datasets,'load_plan',lambda *a,**kw:plan)
    sims=[episode('good1'),episode('also2'),episode('limit0'),episode('sim4',parent=middle['id']),
          episode('sim5',alignment=alignment),episode('old6',alignment={'mode':'unknown'})]
    monkeypatch.setattr(datasets,'eligible',lambda name:sims)
    monkeypatch.setattr(datasets.catalog,'rows',lambda _:[train,held,other,middle,*sims])
    monkeypatch.setattr(datasets,'simulation_model_hash',lambda e:'m')
    monkeypatch.setattr(datasets,'fingerprint',lambda p:'sha')
    chosen,info=datasets.cotraining_episodes('so101_pick_place',250,1.,holdouts=[held,other])
    assert [e['id'] for e in chosen]==['also2','good1'] and info['sim_frames']==200
    assert info['splits_with_sim']==['train'] and set(info['refused'])=={'sim4','sim5','old6'}
    for ident in ('sim4','sim5'):
        assert 'held-out' in info['refused'][ident]
    with pytest.raises(ValueError):
        datasets.cotraining_episodes('tank_dock',100,1.,holdouts=[held,other])


def test_only_predeclared_standard_simulation_with_matching_bundle_and_scenes_is_eligible(tmp_path,monkeypatch):
    from explorer4.sim_protocol import model_identity
    scene='rosmaster_floor_pick_sim'
    source={'id':'source','profile':'rosmaster_pick_place','checkpoint':'ck','config':'{}','status':'completed'}
    seeds=list(range(10000,10020))
    env={'xml_sha256':'geometry','mesh':'revision1'}
    bundle={'checkpoint_bundle_sha256':'bundle','checkpoint_sha256':'weights','processors':{'post':'frozen'}}
    p={'version':2,'scene':scene,'task':'pick up the cube','scene_revision':'rev','scene_seeds':seeds,
       **model_identity(env),**bundle,'n_action_steps':100}
    cfg={'kind':'sim_evaluate','source_job':'source','expected_model_hash':'geometry','scene_seeds':seeds,'profile':scene,'protocol':p}
    active={'id':'eval','status':'completed','created':4.,'config':json.dumps(cfg)}
    diagnostic={**active,'id':'diagnostic','created':5.,'config':json.dumps({**cfg,'diagnostic':'floor_probe'})}
    old={**active,'id':'legacy','created':6.,'config':json.dumps({k:v for k,v in cfg.items() if k!='protocol'})}
    monkeypatch.setattr(deploy_gate.catalog,'rows',lambda _:[source,active,diagnostic,old])
    monkeypatch.setattr(deploy_gate,'scene_revision',lambda _: 'rev')
    monkeypatch.setattr(deploy_gate,'DATA',tmp_path)
    result={'status':'completed','domain':'sim','model':env,'checkpoint_sha256':'weights','profile':scene,'protocol':p,
            'new_process_reload':True,'privileged_input':False,'success_fraction':1.,'n_action_steps':100,
            'trials':[{'seed':s,'initial_qpos_sha256':str(s),'outcome':'success'} for s in seeds]}
    out=tmp_path/'jobs/eval/result.json';out.parent.mkdir(parents=True);out.write_text(json.dumps(result))
    assert deploy_gate.mujoco_result('source',identity=bundle)['job']=='eval'
    assert deploy_gate.mujoco_result('source',identity={**bundle,'processors':{'post':'new'}}) is None
    for change in ({'trials':result['trials'][::-1]},{'model':{**env,'mesh':'different'}},{'n_action_steps':1}):
        out.write_text(json.dumps({**result,**change}))
        assert deploy_gate.mujoco_result('source',identity=bundle) is None
