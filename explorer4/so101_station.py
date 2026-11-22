"""Return object dimensions from the SO-101 station without commanding its arm.

The station checks its current camera against encoder feedback using the installed station
library. For a registered object it recognizes the fiducial and retrieves the operator's
dimensions. For an unlabelled object it fits the validated station geometry to a SAM 3
silhouette. A recipient records its own grasp outcome separately.
"""
import hashlib
import json
from pathlib import Path
import time

from . import knowledge


def read_registered_object(control, prompt, instance_id):
    """Use only the image checked against live jaw feedback. This lookup opens no devices."""
    import cv2
    import numpy as np
    from . import so101_geometry as geometry

    if not control.get('ok'):
        return {'ok': False, 'reason': 'Нет текущей проверки верхней камеры SO-101'}
    image = Path(control['image']).read_bytes()
    calibration = geometry.CALIBRATION.read_bytes()
    if (hashlib.sha256(image).hexdigest() != control['image_sha256']
            or hashlib.sha256(calibration).hexdigest() != control['calibration_sha256']):
        return {'ok': False, 'reason': 'Снимок или калибровка SO-101 изменились после проверки'}
    bgr = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
    if bgr is None:
        return {'ok': False, 'reason': 'Не удалось открыть проверенный снимок SO-101'}
    return geometry.registered_dimensions(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), json.loads(calibration),
                                          geometry.configuration(), prompt, instance_id)


class SO101Station:
    def __init__(self, log=None, device='cuda'):
        self.log = log or (lambda m: None)
        self.device = device

    def available(self):
        from .so101_vendor import measure
        return measure.CALIBRATION.is_file() and __import__('os').path.exists(measure.CAMERA)

    def practice(self, prompt, *, object_instance=None):
        """Measure `prompt` on the table. Returns {'ok': True, 'knowledge': item} or {'ok': False, 'reason'}."""
        from .so101_vendor import measure
        if not self.available():
            return {'ok': False, 'reason': 'верхняя камера SO-101 не подключена'}
        self.log(f'SO-101: проверяю верхней камерой предмет «{object_instance or prompt}»')
        try:
            from .station_check import capture
            control = capture()
            if not control['ok']:
                return {'ok': False, 'reason': 'Не подтверждена текущая геометрия камеры SO-101: '+control['reason']}
            if object_instance:
                m = read_registered_object(control, prompt, object_instance)
            else:
                m = measure.measure(prompt, image=control['image'], device=self.device)
        except Exception as exc:
            return {'ok': False, 'reason': f'стенд SO-101: {type(exc).__name__}: {exc}'}
        if not m['ok']:
            return m
        if m['model'] == 'registered_dimensions':
            observed_instance = m['object_instance']
            evidence = {'dimension_source': m['dimension_source'], 'marker': m['marker']}
        else:
            if not m.get('height_measured'):
                return {'ok': False, 'reason': 'Высота объекта по этому ракурсу не измерена', 'dir': m['dir']}
            observed_instance = (m['selection']['marker'] or {}).get('instance_id')
            evidence = {k: m[k] for k in ('silhouette_rmse_px', 'score', 'overlay', 'dir', 'height_sigma_m', 'selection')}
            evidence['dimension_source'] = 'calibrated_silhouette'
        params = {'width_m': m['width_m'], 'length_m': m['length_m'], 'height_m': m['height_m'],
                  'grasp_height_m': round(max(.012, min(m['height_m'], .06) / 2), 3)}
        self.log(f'SO-101: «{prompt}» {m["width_m"] * 100:.1f}×{m["length_m"] * 100:.1f} см, высота {m["height_m"] * 100:.1f} см ({m["model"]})')
        item = knowledge.add(prompt, 'so101_station', params, success=None, object_instance=observed_instance,
                             evidence={'camera_control': control, 'model': m['model'], **evidence})
        return {'ok': True, 'knowledge': item}


class SimSO101Station:
    """Virtual station for the swarm simulation: measures the true object size with small noise."""
    def __init__(self, world, log=None):
        self.world, self.log = world, log or (lambda m: None)

    def available(self):
        return True

    def practice(self, prompt, grasp=True, *, object_instance=None):
        if object_instance:
            return {'ok': False, 'reason': 'В этой двумерной сцене есть только имена классов предметов'}
        size = self.world.sizes.get(prompt)
        if size is None:
            return {'ok': False, 'reason': f'«{prompt}» нет на столе SO-101'}
        self.log(f'SO-101: пробую взять «{prompt}» и измеряю')
        time.sleep(2.)
        s = size * (1 + self.world.measure_rng.uniform(-.05, .05))
        item = knowledge.add(prompt, 'so101_station', {'width_m': round(s, 3), 'height_m': round(s, 3),
                                                       'grasp_height_m': round(max(.012, s / 2), 3)},
                             evidence={'sim': True}, success=True, domain='sim')
        return {'ok': True, 'knowledge': item}
