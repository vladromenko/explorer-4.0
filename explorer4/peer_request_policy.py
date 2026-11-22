"""Inference and file provenance for the simulation-only peer-request selector."""
import hashlib
import json
from pathlib import Path

import numpy as np

from .paths import DATA


FEATURES = ('marker_visible', 'relative_area', 'off_centre', 'reprojection_error_px', 'central_screen_fraction')


def checksum(value):
    raw = json.dumps(value, sort_keys=True, allow_nan=False, separators=(',', ':')).encode()
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def local_features(packet, measurement):
    """Read only the initial recipient RGB detection and central coating occupancy."""
    screen = float(measurement['screen_fraction'])
    if not 0 <= screen <= 1:
        raise ValueError('Invalid screen pixel fraction')
    if packet is None:
        return [0., 0., 0., 0., screen]
    corners = np.asarray(packet['corners_px'], dtype=float)
    if corners.shape != (4, 2) or not np.isfinite(corners).all():
        raise ValueError('Four finite image corners required')
    normalized = corners / [640, 400]
    x, y = normalized.T
    area = .5 * abs(x @ np.roll(y, -1) - y @ np.roll(x, -1))
    features = [1., float(area), float(np.linalg.norm(normalized.mean(axis=0)-.5)),
                float(packet['reprojection_error_px']), screen]
    if not np.isfinite(features).all():
        raise ValueError('Non-finite image feature')
    return features


def score(model, features):
    normalized = (np.asarray(features) - model['mean']) / model['scale']
    return float(normalized @ model['coef'] + model['intercept'])


def verified_model(folder):
    model = read(folder/'model.json')
    fit = read(folder/'fit.json')
    plan = read(folder/'plan.json')
    report = read(folder/'evaluation.json')
    sha = checksum(model)
    if (model['schema'] != 'peer_request_ridge_v2' or model['features'] != list(FEATURES)
            or checksum(plan) != model['plan_sha256'] or sha != fit['model_sha256']
            or report['status'] != 'completed' or sha != report['model_sha256']):
        raise ValueError('Peer selector provenance failed')
    for name in ('mean', 'scale', 'coef'):
        vector = np.asarray(model[name])
        if vector.shape != (len(FEATURES),) or not np.isfinite(vector).all():
            raise ValueError('Invalid coefficient vector')
    if min(model['scale']) <= 0 or not np.isfinite([model['intercept'], model['threshold']]).all():
        raise ValueError('Invalid scaling or decision threshold')
    return sha, model


def available_models():
    base = DATA/'simlab/reports/workspace'
    result = {}
    for path in sorted(base.glob('*/peer_learning/evaluation.json')):
        try:
            sha, model = verified_model(path.parent)
        except (OSError, KeyError, ValueError, TypeError):
            continue
        result[sha] = {'folder':path.parent, 'plan_sha256':model['plan_sha256']}
    return result


def load_model(sha):
    entry = available_models().get(sha)
    if entry is None:
        raise ValueError('Обученный выбор помощи ожидает обучения и проверки в симуляции.')
    actual, model = verified_model(entry['folder'])
    if actual != sha:
        raise ValueError('Изменилась сохранённая версия модели помощи.')
    return model
