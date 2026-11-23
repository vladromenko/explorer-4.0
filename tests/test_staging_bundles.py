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
              'software': {'motion_permission.py': deploy.PREVIOUS_PERMISSION_SHA, 'limits.py':deploy.source_hash('limits.py'),
                           'agent.py':next(iter(deploy.REVIEWED_V2_AGENTS))}}
    actual = {**status, 'software': {k: deploy.source_hash(k) for k in deploy.HEALTH_FILES}}
    verified = deploy.preflight(status, raw)
    with pytest.raises(ValueError, match='guard implementation is unrecognized'):
        deploy.preflight({**status, 'software': {**status['software'], 'agent.py':'custom_guard'}}, raw)
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
        return {'limits_hex': config.read_bytes().hex(), 'software_on_disk':actual['software'], 'permission_sha256':{
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


def test_live_inspection_reads_running_agent_and_unchanged_installed_files(tmp_path, monkeypatch):
    import json
    import subprocess
    import sys
    from scripts import deploy_tank_recording as deploy

    robot = tmp_path / 'robot'
    robot.mkdir()
    monkeypatch.setattr(deploy, 'REMOTE', str(robot))
    for name in deploy.HEALTH_FILES:
        (robot/name).write_bytes((deploy.ROOT/'agents/tank'/name).read_bytes())
    (robot/'incident-block.json').write_bytes(b'keep this operator marker')
    before = {p.name: p.read_bytes() for p in robot.iterdir()}
    state = {'armed':False, 'hardware_open':False, 'limits':deploy.DEFAULTS,
             'software':{n:deploy.source_hash(n) for n in deploy.HEALTH_FILES}, 'monotonic_ns':1}
    events = []
    def get_health():
        events.append('GET /health')
        return {**state, 'monotonic_ns':len(events)}
    def read_files(*cmd):
        assert cmd[:3] == ('python3','-B','-c') and cmd[4] == str(robot)
        events.append('read hashes')
        return subprocess.check_output([sys.executable,*cmd[1:]],text=True)
    monkeypatch.setattr(deploy,'health',get_health)
    monkeypatch.setattr(deploy,'docker',read_files)
    receipt = deploy.inspect_live()
    assert events == ['GET /health','read hashes','GET /health']
    assert receipt['compatible'] and receipt['physical_commands'] == 0
    assert receipt['permission_sha256']['incident-block.json']
    assert receipt['live_software'] == receipt['disk_software']
    assert {p.name:p.read_bytes() for p in robot.iterdir()} == before
    (robot/'agent.py').write_bytes(b'updated on disk, old process')
    rejected = deploy.inspect_live()
    assert not rejected['compatible'] and 'inventories differ' in rejected['reason']
