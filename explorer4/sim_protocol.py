"""Freeze the exact policy, scene implementation, geometry and ordered evaluation seeds."""
import hashlib
import json
import subprocess
from pathlib import Path

from .paths import ROOT, offline_environment
from .profiles import profile
from .training_drafts import checkpoint_hash


def sha256_file(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def bundle_identity(checkpoint):
    root = Path(checkpoint)
    processors = {}
    for role in ('pre', 'post'):
        path = root / f'policy_{role}processor.json'
        config = json.loads(path.read_text())
        files = [path]
        for step in config['steps']:
            if step.get('state_file'):
                asset = root / step['state_file']
                if asset.resolve().parent != root.resolve():
                    raise ValueError('Processor state must be part of the checked checkpoint bundle')
                files.append(asset)
        processors.update({f.name: sha256_file(f) for f in files})
    return {'checkpoint_bundle_sha256': checkpoint_hash(root),
            'checkpoint_sha256': sha256_file(root / 'model.safetensors'), 'processors': processors}


def scene_revision(name):
    cfg = profile(name)
    sources = ['sim/factory.py', 'sim/environment.py', 'sim/variation.py', 'sim/scene.py']
    if name.endswith('dock_sim'):
        sources.extend(['sim/mobile.py','sim/tank_model.py','sim/manufacturer.py'])
    else:
        sources.extend(['sim/models.py', 'sim/manufacturer.py', 'sim/rosmaster_arm.py', 'sim/aligned.py'])
    paths = [ROOT / 'explorer4' / s for s in sources]
    paths.extend(ROOT / 'configs' / s for s in ('sim-alignment.json', 'tank-hardware-evidence.json'))
    digest = hashlib.sha256(json.dumps(cfg, sort_keys=True).encode())
    for path in paths:
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(bytes.fromhex(sha256_file(path)))
    return digest.hexdigest()


def model_identity(manifest):
    encoded = json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()
    return {'xml_sha256':manifest['xml_sha256'], 'model_manifest_sha256':hashlib.sha256(encoded).hexdigest()}


def probe_geometry(name):
    """The web process does not import MuJoCo. Build the exact scene without a renderer."""
    result = subprocess.run([str(ROOT / '.venv-sim/bin/python'), '-m', 'explorer4.sim_protocol', '--geometry', name],
                            cwd=ROOT, env=offline_environment(), capture_output=True, text=True, timeout=45)
    if result.returncode:
        raise ValueError('Unable to freeze current MuJoCo geometry: ' + result.stderr[-400:])
    return json.loads(result.stdout.splitlines()[-1])


def protocol(name, seeds, geometry, checkpoint):
    values = list(seeds)
    if not values or any(type(s) is not int or s < 0 for s in values) or len(set(values)) != len(values):
        raise ValueError('Expected distinct nonnegative integer scene seeds in evaluation order')
    return {'version': 2, 'scene': name, 'scene_revision': scene_revision(name),
            'task': profile(name)['task'], 'scene_seeds': values, **geometry,
            'n_action_steps':json.loads((Path(checkpoint)/'config.json').read_text()).get('n_action_steps'),
            **bundle_identity(checkpoint)}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--geometry', required=True)
    from .sim.factory import make
    env = make(parser.parse_args().geometry, images=False)
    try:
        print(json.dumps(model_identity(env.manifest)))
    finally:
        env.close()
