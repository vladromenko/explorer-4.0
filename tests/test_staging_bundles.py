import io
import tarfile

import pytest

from scripts.build_staging_bundles import archive, verify


def test_archive_is_repeatable_and_content_checked(tmp_path):
    first, second = tmp_path / 'first.tar', tmp_path / 'second.tar'
    archive(first, {'payload/incident-block.json': b'{}'}, 'tank')
    archive(second, {'payload/incident-block.json': b'{}'}, 'tank')
    assert first.read_bytes() == second.read_bytes()
    assert not verify(first)['physical_acceptance']
    # A byte change without changing the manifest must fail verification.
    first.write_bytes(first.read_bytes().replace(b'{}', b'[]'))
    with pytest.raises(ValueError, match='manifest'):
        verify(first)


def test_verifier_rejects_paths_and_links_without_extraction(tmp_path):
    path = tmp_path / 'bad.tar'
    for name, kind in [('../outside', tarfile.REGTYPE), ('linked', tarfile.SYMTYPE)]:
        with tarfile.open(path, 'w') as output:
            entry = tarfile.TarInfo(name)
            entry.type = kind
            entry.linkname = '/etc/passwd' if kind == tarfile.SYMTYPE else ''
            output.addfile(entry, io.BytesIO(b''))
        with pytest.raises(ValueError):
            verify(path)


def test_install_backup_and_rollback_preserve_secrets_and_legacy_history(tmp_path):
    import hashlib,json
    from scripts.install_tank_bundle import install,rollback
    root=tmp_path/'robot';root.mkdir();stage=tmp_path/'stage';(stage/'payload').mkdir(parents=True)
    (root/'agent.py').write_text('old agent');(root/'config.json').write_text('secret remains')
    (root/'incident-block.json').write_text('old incident')
    files={'agent.py':b'new agent','limits.py':b'new limits'}
    for name,data in files.items():(stage/'payload'/name).write_bytes(data)
    manifest={'platform':'tank','files':{'payload/'+name:hashlib.sha256(data).hexdigest() for name,data in files.items()}}
    (stage/'MANIFEST.json').write_text(json.dumps(manifest))
    result=install(stage,root)
    assert (root/'incident-block.json').read_text()=='old incident'
    assert (root/'config.json').read_text()=='secret remains'
    (root/'incident-block.json').write_text('new operator decision')
    assert (root/'agent.py').read_text()=='new agent'
    rollback(result['archive'])
    assert (root/'agent.py').read_text()=='old agent' and not (root/'limits.py').exists()
    assert (root/'incident-block.json').read_text()=='new operator decision'
    (stage/'payload/agent.py').write_text('tampered')
    with pytest.raises(ValueError,match='hash'):install(stage,root)


def test_tank_preflight_uses_exact_active_limits_and_preserves_operators_files(tmp_path):
    import hashlib
    import json
    from agents.tank import limits
    from scripts import deploy_tank_recording as deploy
    from scripts.install_tank_bundle import install, rollback

    onboard = tmp_path / 'robot'
    config = onboard / 'configs/tank-limits.json'
    config.parent.mkdir(parents=True)
    raw = b'{"version":2,"manual":{"v":0.08,"w":0.2},"policy":{"v":0.06,"w":0.1}, "command_ttl_s":0.25, "battery_stop_v":7.1}'
    config.write_bytes(raw)
    permissions = onboard / 'bench-authorized.json'
    permissions.write_bytes(b'operator decision')
    status = {'armed': False, 'hardware_open': False, 'limits': limits.load(onboard),
              'software': {'motion_permission.py': deploy.PREVIOUS_PERMISSION_SHA}}
    actual = {**status, 'software': {k: deploy.source_hash(k) for k in deploy.HEALTH_FILES}}
    verified = deploy.preflight(status, raw)
    assert verified['effective_limits']['manual']['v'] == .08
    assert verified['effective_limits']['command_ttl_s'] == .25
    assert verified['effective_limits']['battery_stop_v'] == 7.1
    assert verified['operator_config_sha256'] == hashlib.sha256(raw).hexdigest()
    stage = tmp_path / 'stage'
    (stage / 'payload').mkdir(parents=True)
    (stage / 'payload/agent.py').write_bytes(b'updated')
    manifest = {'platform': 'tank', 'files': {'payload/agent.py': hashlib.sha256(b'updated').hexdigest()}}
    (stage / 'MANIFEST.json').write_text(json.dumps(manifest))
    def snapshot():
        return {'limits_hex': config.read_bytes().hex(), 'permission_sha256':{
            permissions.name: hashlib.sha256(permissions.read_bytes()).hexdigest()}}
    before = snapshot()
    changed = install(stage, onboard)
    deploy.verify_installation(actual, verified, before, snapshot())
    assert config.read_bytes() == raw and permissions.read_bytes() == b'operator decision'
    with pytest.raises(ValueError, match='Published limits'):
        deploy.verify_installation({**actual, 'limits': limits.DEFAULTS}, verified, before, snapshot())
    incomplete = dict(actual['software'])
    incomplete.pop('agent.py')
    with pytest.raises(ValueError, match='inventory'):
        deploy.verify_installation({**actual, 'software': incomplete}, verified, before, snapshot())
    config.write_bytes(raw + b'\n')
    with pytest.raises(ValueError, match='markers changed'):
        deploy.verify_installation(actual, verified, before, snapshot())
    rollback(changed['archive'])
    assert config.read_bytes() == raw + b'\n' and permissions.read_bytes() == b'operator decision'


def test_decline_legacy_and_active_deploy_before_staging_or_restarting(monkeypatch):
    import json
    from scripts import deploy_tank_recording as deploy

    historical = (deploy.ROOT/'configs/tank-limits.json').read_bytes()
    status = {'armed':False, 'hardware_open':False, 'limits':json.loads(historical)}
    monkeypatch.setattr(deploy, 'health', lambda: status)
    monkeypatch.setattr(deploy, 'read_policy', lambda:{'limits_hex':historical.hex(), 'permission_sha256':{}})
    monkeypatch.setattr(deploy, 'build', lambda *a:pytest.fail('preflight must precede staging'))
    monkeypatch.setattr(deploy, 'ssh', lambda *a:pytest.fail('preflight must precede remote mutation'))
    with pytest.raises(ValueError, match='Version 1'):
        deploy.deploy()
    with pytest.raises(ValueError, match='hardware closed'):
        deploy.preflight({**status,'hardware_open':True}, historical)
    with pytest.raises(ValueError, match='Candidate effective limits differ'):
        deploy.preflight(status, None)
    with pytest.raises(ValueError, match='unrecognized'):
        deploy.preflight({**status,'limits':deploy.DEFAULTS}, None)
    with pytest.raises(ValueError, match='Unknown onboard'):
        deploy.preflight(status, b'{"version":2,"extra_stop":null}')


@pytest.mark.parametrize('name', ['configs/tank-limits.json', 'incident-block.json', 'handoff-active.json'])
def test_tank_payload_cannot_write_operator_settings(tmp_path, name):
    import hashlib
    import json
    from scripts.install_tank_bundle import install

    stage = tmp_path / 'stage'
    payload = stage / 'payload' / name
    payload.parent.mkdir(parents=True)
    payload.write_bytes(b'{}')
    (stage / 'MANIFEST.json').write_text(json.dumps({'platform':'tank','files':{
        'payload/'+name:hashlib.sha256(b'{}').hexdigest()}}))
    with pytest.raises(ValueError, match='Protected onboard'):
        install(stage,tmp_path/'robot')
    assert not (tmp_path/'robot').exists()
