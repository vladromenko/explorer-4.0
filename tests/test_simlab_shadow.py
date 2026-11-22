"""M8.2: shadow mode on a recording never sends commands and reports agreement."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

av = pytest.importorskip('av')
pd = pytest.importorskip('pandas')
pytest.importorskip('httpx')

ROOT = Path(__file__).resolve().parents[1]


def fake_policy(path):
    from explorer4.simlab import contract
    dim = contract.size('tank') * 3
    np.savez(path / 'policy.npz', norm_mean=np.zeros(dim), norm_var=np.ones(dim), w0=np.zeros((2, dim)), b0=np.array([0.5, 0.0]))
    import hashlib
    info = {'format': 'explorer4.simlab.mlp_elu.v1', 'robot': 'tank', 'contract_version': contract.VERSION,
            'contract_hash': contract.contract_hash('tank'), 'history': 3, 'layers': 1, 'scenario': 'dock_v1',
            'scenario_fingerprint': 'x', 'weights_sha256': hashlib.sha256((path / 'policy.npz').read_bytes()).hexdigest()}
    (path / 'policy.json').write_text(json.dumps(info))


def test_shadow_uses_official_samples_and_real_history(tmp_path, monkeypatch):
    from scripts import simlab_shadow as shadow
    from explorer4.sensors import CHANNELS
    pol=tmp_path/'policy'
    pol.mkdir()
    fake_policy(pol)
    sample=np.zeros((400,640,3),np.uint8)
    env=np.zeros(len(CHANNELS),np.float32)
    samples=[(0,i/20,sample,env,np.array([.15,0.]),np.array([.1,0.])) for i in range(12)]
    monkeypatch.setattr(shadow,'labeled_samples',lambda *_:samples)
    result=shadow.shadow(shadow.Policy(pol),tmp_path)['summary']
    assert result['frames']==12 and result['commands_sent']==0
    assert result['marker_visible_fraction']==0 and result['sign_agreement_when_moving'][0]==1.
    assert result['camera']['height']==400


def test_shadow_rejects_missing_rosmaster_calibration_and_incomplete_environment(tmp_path):
    from scripts import simlab_shadow as shadow
    with pytest.raises(ValueError,match='ROSMASTER'):
        shadow.recording_camera('rosmaster',tmp_path)
    (tmp_path/'meta').mkdir()
    (tmp_path/'meta/info.json').write_text(json.dumps({'features':{},'fps':20}))
    with pytest.raises(ValueError,match='environment_state'):
        next(shadow.labeled_samples(tmp_path,'tank'))
