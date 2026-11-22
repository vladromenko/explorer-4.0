"""Queue and lease regressions. No training, evaluation or subprocess is started."""
import hashlib
import json

import numpy as np
import pytest

from explorer4 import catalog, paths, resources, training
from explorer4.jobs import Jobs
from explorer4.simlab import contract
from scripts import simlab_pipeline


@pytest.fixture
def queue(tmp_path, monkeypatch):
    for module in (paths,catalog,resources,training,simlab_pipeline):
        monkeypatch.setattr(module,'DATA',tmp_path)
    catalog.initialize()
    return Jobs(None)


def saved_policy(root):
    path=root/'simlab/policies/tank_test'
    path.mkdir(parents=True)
    np.savez(path/'policy.npz',norm_mean=np.zeros(1),norm_var=np.ones(1),w0=np.ones((1,1)),b0=np.zeros(1))
    info={'robot':'tank','contract_version':contract.version('tank'),'contract_hash':contract.contract_hash('tank'),
          'weights_sha256':hashlib.sha256((path/'policy.npz').read_bytes()).hexdigest(),'history':1,'layers':1}
    (path/'policy.json').write_text(json.dumps(info))
    return path


def test_multiple_recipes_queue_without_start_and_cancel_independently(queue):
    first=queue.enqueue_simlab_pipeline('tank','check')
    second=queue.enqueue_simlab_pipeline('tank','full')
    third=queue.enqueue_simlab_pipeline('so101','clone')
    assert all(queue.get(k)['status']=='queued' for k in (first,second,third))
    queue.cancel(second)
    assert queue.get(second)['status']=='cancelled' and queue.get(first)['status']=='queued'
    with pytest.raises(ValueError):queue.enqueue_simlab_pipeline('tank','clone')


def test_managed_evaluation_uses_existing_lease_and_frozen_policy(queue,tmp_path,monkeypatch):
    policy=saved_policy(tmp_path)
    for robot,path in [('so101',policy),('tank',tmp_path)]:
        with pytest.raises(ValueError):queue.enqueue_simlab_pipeline(robot,'eval',path)
    ident=queue.enqueue_simlab_pipeline('tank','eval',policy)
    job=queue.get(ident)
    request=tmp_path/'jobs'/f'{ident}.json'
    request.write_text(job['config'])
    with catalog.connect() as db:db.execute("UPDATE jobs SET status='running' WHERE id=?",(ident,))
    calls=[]
    def record(title,args,python):
        calls.append(args[0])
        if args[0].endswith('simlab_video.py'):
            (policy/'videos').mkdir()
            (policy/'videos/index.json').write_text('[]')
    monkeypatch.setattr(simlab_pipeline,'step',record)
    with resources.ResourceLease('compute'):
        training.run_job(request)
        assert calls==['scripts/simlab_eval.py','scripts/simlab_eval.py','scripts/simlab_video.py']
        assert json.loads((tmp_path/'jobs'/ident/'result.json').read_text())['weights_sha256']
        with (policy/'policy.json').open('a') as stream:stream.write(' ')
        with pytest.raises(ValueError,match='изменилась'):training.run_job(request)
    assert not (tmp_path/'simlab/active.json').exists()


def test_standalone_entry_point_still_honours_lease(queue,monkeypatch):
    monkeypatch.setattr(simlab_pipeline.sys,'argv',['simlab_pipeline.py','tank','check'])
    monkeypatch.setattr(simlab_pipeline,'step',lambda *a:pytest.fail('unexpected launch'))
    with resources.ResourceLease('compute'),pytest.raises(resources.ResourceBusy):
        simlab_pipeline.main()
