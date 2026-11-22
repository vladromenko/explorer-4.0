import json
from pathlib import Path
import pytest
from explorer4 import training_drafts as drafts


def episode(ident,session=None,scene=None):
    return {'id':ident,'session':session or ident,'scene':scene or ident,'sha256':ident*64,'frames':100}


def plan(train,validation,test):
    return {'domain':'sim','profile':'tank_dock_sim','sim_model_hash':'a'*64,
        'splits':{'train':train,'validation':validation,'test':test},'smoke':False,'seed':1000}


def test_finetune_preserves_old_roles_and_counts_new_frames():
    old=plan([episode('a')],[episode('b')],[episode('c')])
    new=plan([episode('d')],[episode('e',scene='a')],[episode('f')])
    merged=drafts.merge_plans(old,new)
    assert {x['id'] for x in merged['splits']['train']}=={'a','d','e'}
    assert {x['id'] for x in merged['splits']['validation']}=={'b'}
    assert {x['id'] for x in merged['splits']['test']}=={'c','f'}
    # A new segment bridges old train and validation: reject rather than reassign.
    new=plan([episode('d',session='a',scene='b')],[episode('e')],[episode('f')])
    with pytest.raises(ValueError,match='связывают'):drafts.merge_plans(old,new)


def test_preparation_creates_only_draft_and_frozen_plan(tmp_path,monkeypatch):
    monkeypatch.setattr(drafts,'DATA',tmp_path)
    selected=plan([episode('a')],[episode('b')],[episode('c')])
    monkeypatch.setattr(drafts.datasets,'freeze',lambda *a,**kw:('p'*64,selected))
    monkeypatch.setattr(drafts.datasets,'load_plan',lambda ident:selected)
    ident,prepared=drafts.prepare('tank_dock_sim','act',['a','b','c'],steps=1234,batch=2,seed=1000,device='cpu')
    assert prepared['preparation_only'] and not prepared['training_started']
    assert prepared['steps']==1234 and prepared['mixture']=={'old_train_frames':0,'new_train_frames':100}
    assert drafts.load(ident)==prepared
    assert not (tmp_path/'jobs').exists() and not (tmp_path/'catalog.sqlite3').exists()
    (tmp_path/'training-drafts'/(ident+'.json')).write_text('{}')
    with pytest.raises(ValueError,match='изменился'):drafts.load(ident)


def test_finetune_checkpoint_is_pinned_and_changed_weights_rejected(tmp_path,monkeypatch):
    monkeypatch.setattr(drafts,'DATA',tmp_path)
    old=plan([episode('a')],[episode('b')],[episode('c')]);new=plan([episode('d')],[episode('e')],[episode('f')])
    checkpoint=tmp_path/'checkpoint';checkpoint.mkdir()
    (checkpoint/'config.json').write_text(json.dumps({'type':'act'}));(checkpoint/'model.safetensors').write_bytes(b'weights')
    monkeypatch.setattr(drafts.datasets,'freeze',lambda *a,**kw:('n'*64,new))
    monkeypatch.setattr(drafts.datasets,'load_plan',lambda ident:old if ident=='o'*64 else new)
    source={'id':'source','status':'completed','profile':'tank_dock_sim','policy':'act','checkpoint':str(checkpoint),
            'config':json.dumps({'kind':'train','plan_id':'o'*64})}
    ident,value=drafts.prepare('tank_dock_sim','act',['d','e','f'],steps=100,batch=1,seed=1000,device='cpu',source=source)
    assert value['mode']=='fine_tune_new_optimizer' and value['mixture']=={'old_train_frames':100,'new_train_frames':100}
    drafts.load(ident)
    (checkpoint/'model.safetensors').write_bytes(b'changed')
    with pytest.raises(ValueError,match='веса изменились'):drafts.load(ident)


@pytest.mark.parametrize('args',[(49,1,0,'cpu'),(100,0,0,'cpu'),(100,1,-1,'cpu'),(100,1,0,'auto')])
def test_invalid_budgets(args):
    with pytest.raises(ValueError):drafts.validate_budget(*args)


def test_finetune_accepts_documentation_changes_but_not_channel_units():
    import copy
    old=plan([episode('a')],[episode('b')],[episode('c')]);new=plan([episode('d')],[episode('e')],[episode('f')])
    old['profile_contract']={'fps':20,'channels':['vx'],'units':['m/s'],'model_status':'old wording'}
    new['profile_contract']={**old['profile_contract'],'model_status':'corrected description'}
    drafts.merge_plans(old,new)
    new['profile_contract']['units']=['cm/s']
    with pytest.raises(ValueError,match='версию модели'):drafts.merge_plans(old,new)


def test_real_preparation_preserves_full_dataset_minimum_and_does_not_queue(tmp_path,monkeypatch):
    monkeypatch.setattr(drafts,'DATA',tmp_path)
    selected=plan([episode('a')],[episode('b')],[episode('c')])
    selected.update(domain='real',profile='rosmaster_dock',sim_model_hash=None)
    def freeze(name,smoke,**kw):
        assert name=='rosmaster_dock' and smoke is False
        assert kw['min_sim_episodes'] is None
        assert kw.get('min_real_episodes') is None  # retain standard 50, not a 3-demo pilot
        return 'p'*64,selected
    monkeypatch.setattr(drafts.datasets,'freeze',freeze)
    monkeypatch.setattr(drafts.datasets,'load_plan',lambda ident:selected)
    ident,prepared=drafts.prepare('rosmaster_dock','act',['a','b','c'],steps=2000,batch=1,seed=1000,device='cpu')
    assert prepared['domain']=='real' and prepared['preparation_only']
    assert prepared['training_started'] is False
    assert drafts.load(ident)==prepared
    assert not (tmp_path/'jobs').exists()


def test_real_finetune_preserves_holdouts_and_rejects_sim_mixing():
    old=plan([episode('a')],[episode('b')],[episode('c')])
    new=plan([episode('d')],[episode('e',scene='a')],[episode('f')])
    for value in (old,new):value.update(domain='real',profile='rosmaster_dock',sim_model_hash=None)
    merged=drafts.merge_plans(old,new)
    assert {x['id'] for x in merged['splits']['train']}=={'a','d','e'}
    assert {x['id'] for x in merged['splits']['validation']}=={'b'}
    new['domain']='sim'
    with pytest.raises(ValueError):drafts.merge_plans(old,new)


def test_dataset_fingerprint_includes_raw_sensor_packets(tmp_path,monkeypatch):
    from explorer4 import datasets
    monkeypatch.setattr(datasets,'DATA',tmp_path)
    root=tmp_path/'datasets'/'episode';(root/'sensors').mkdir(parents=True)
    (root/'provenance.json').write_text('{}')
    raw=root/'sensors'/'000000.npz';raw.write_bytes(b'fixture-sensor-before')
    before=datasets.fingerprint(root)
    raw.write_bytes(b'fixture-sensor-after')
    assert datasets.fingerprint(root)!=before
    outside=tmp_path/'outside.npz';outside.write_bytes(b'external')
    (root/'sensors'/'linked.npz').symlink_to(outside)
    with pytest.raises(ValueError,match='outside'):datasets.fingerprint(root)


def test_double_submission_of_prepared_plan_queues_one_job(tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from explorer4 import catalog
    from explorer4.jobs import Jobs
    monkeypatch.setattr(catalog,'DATA',tmp_path)
    monkeypatch.setattr(catalog,'prepare',lambda:None)
    catalog.initialize()
    monkeypatch.setattr(drafts,'load',lambda ident:{'profile':'rosmaster_dock','policy':'act',
        'preparation_only':True,'training_started':False,'kind':'train'})
    jobs=Jobs(None)
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids=list(pool.map(jobs.start_prepared_training,['d'*64,'d'*64]))
    assert ids[0]==ids[1]
    assert len(catalog.rows('jobs'))==1
    assert catalog.rows('jobs')[0]['status']=='queued'
    assert jobs.process is None and jobs.thread is None
    with catalog.connect() as db:db.execute("UPDATE jobs SET status='completed' WHERE id=?",(ids[0],))
    assert jobs.start_prepared_training('d'*64)!=ids[0]


def test_comparison_reuses_one_partition_for_two_optimizer_seeds_and_legacy_drafts(tmp_path, monkeypatch):
    monkeypatch.setattr(drafts,'DATA',tmp_path)
    fixture=plan([episode('a')],[episode('b')],[episode('c')])
    fixture.update(domain='real',profile='so101_pick_place',sim_model_hash=None,seed=17)
    plan_id=drafts.save_content(tmp_path/'plans',fixture)
    original=(tmp_path/'plans'/(plan_id+'.json')).read_bytes()
    monkeypatch.setattr(drafts.datasets,'load_plan',lambda ident:fixture if ident==plan_id else None)
    frozen=[]
    def freeze(*args,**kwargs):
        frozen.append(kwargs['seed'])
        return plan_id,fixture
    monkeypatch.setattr(drafts.datasets,'freeze',freeze)
    params={'steps':100,'batch':1,'device':'cpu'}
    first_id,first=drafts.prepare('so101_pick_place','act',['a','b','c'],**params,split_seed=17,train_seed=818)
    second_id,second=drafts.prepare('so101_pick_place','diffusion',None,**params,train_seed=819,plan_id=plan_id)
    assert first_id!=second_id and frozen==[17]
    assert first['plan_id']==second['plan_id']==plan_id and first['split_seed']==second['split_seed']==17
    assert second['train_seed']==second['seed']==819
    with pytest.raises(ValueError,match='Frozen plan'):
        drafts.prepare('so101_pick_place','act',None,**params,plan_id=plan_id,split_seed=818)
    legacy={k:v for k,v in first.items() if k not in ('split_seed','train_seed')}
    legacy['version']=1
    old_id=drafts.save_content(tmp_path/'training-drafts',legacy)
    assert drafts.load(old_id)==legacy and (tmp_path/'plans'/(plan_id+'.json')).read_bytes()==original


def test_confirmation_seals_processor_identity_and_reads_old_seal_without_rewriting(tmp_path,monkeypatch):
    from contextlib import nullcontext
    from explorer4 import fleet_config,sim_protocol,training
    monkeypatch.setattr(fleet_config,'locked',nullcontext)
    identity={'checkpoint_sha256':'a'*64,'checkpoint_bundle_sha256':'b'*64}
    monkeypatch.setattr(sim_protocol,'bundle_identity',lambda _:identity.copy())
    cp=tmp_path/'weights'; cp.mkdir()
    assert training.bind_test_checkpoint(tmp_path,cp)=='bundle'
    identity['checkpoint_bundle_sha256']='c'*64
    with pytest.raises(ValueError,match='processors'):
        training.bind_test_checkpoint(tmp_path,cp)
    legacy=json.dumps({'checkpoint':str(cp),'sha256':identity['checkpoint_sha256']})
    seal=tmp_path/'frozen-test-checkpoint.json'
    seal.write_text(legacy)
    assert training.bind_test_checkpoint(tmp_path,cp)=='legacy_weights_only' and seal.read_text()==legacy
