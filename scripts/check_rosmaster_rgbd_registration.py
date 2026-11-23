"""Compare image-derived relative camera motion with the native arm model on archives."""

import argparse
import hashlib
import itertools
import json
from pathlib import Path

import cv2
import numpy as np
from scipy.spatial.transform import Rotation

from explorer4.peer_dock_real import write_json
from explorer4.peer_dock_shelf import normalized_rays
from explorer4.sensors import decode_packet
from explorer4.sim.vendor_rosmaster.arm_model import ArmModel


def load_group(folder, detector):
    receipt = folder / 'result.json'
    native = json.loads(receipt.read_text())['rows'] if receipt.is_file() else None
    result = []
    for index in (0, 4, 8):
        raw = (folder / f'{index:02}.npz').read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        packet = decode_packet(raw)
        streams, arrays = packet['meta']['streams'], packet['arrays']
        if (packet['meta']['robot'] != 'rosmaster' or packet['meta']['read_only'] is not True
                or packet['meta']['motion_commands_sent'] != 0
                or streams['depth']['unit'] != 'mm' or streams['depth']['frame_id'] != streams['rgb']['frame_id']
                or arrays['depth'].shape != arrays['rgb'].shape[:2]):
            raise ValueError('Expected passive ROSMASTER depth registered to RGB')
        if native is not None and native[index]['input_sha256'] != digest:
            raise ValueError('Native joint receipt has a different camera packet')
        arm = native[index]['arm_native_degrees'] if native is not None else arrays['arm']
        gray = cv2.cvtColor(arrays['rgb'], cv2.COLOR_RGB2GRAY)
        points, vectors = detector.detectAndCompute(gray, None)
        result.append({'camera': streams['rgb_info'], 'depth': arrays['depth'] * .001,
                       'pixels': np.asarray([point.pt for point in points]), 'descriptors': vectors,
                       'arm': arm, 'sha256': digest})
    return result


def registered_motion(first, second, matcher, model):
    a, b = first['descriptors'], second['descriptors']
    if a is None or b is None or len(b) < 2:
        return {'valid': False, 'matches': 0}
    matches = [pair[0] for pair in matcher.knnMatch(a, b, k=2)
               if len(pair) == 2 and pair[0].distance < .74 * pair[1].distance]
    left = np.asarray([first['pixels'][m.queryIdx] for m in matches])
    right = np.asarray([second['pixels'][m.trainIdx] for m in matches])
    if len(matches) < 6:
        return {'valid': False, 'matches': len(matches)}

    def metric(pixels, view):
        height, width = view['depth'].shape
        x, y = np.clip(np.rint(pixels).astype(int), [0, 0], [width - 1, height - 1]).T
        values = view['depth'][y, x]
        return normalized_rays(view['camera'], pixels) * values[:, None]

    reference, measured = metric(left, first), metric(right, second)
    valid = (reference[:, 2] > .15) & (reference[:, 2] < 2) & (measured[:, 2] > .15) & (measured[:, 2] < 2)
    k = np.asarray(second['camera']['k']).reshape(3, 3)
    d = np.asarray(second['camera']['d'])
    if valid.sum() < 6:
        return {'valid': False, 'matches': len(matches), 'with_metric_depth': int(valid.sum())}
    _, rotation, translation, inliers = cv2.solvePnPRansac(
        reference[valid], right[valid], k, d, iterationsCount=2000, reprojectionError=2.3,
        confidence=.999, flags=cv2.SOLVEPNP_EPNP,
    )
    if inliers is None:
        return {'valid': False, 'matches': len(matches), 'with_metric_depth': int(valid.sum())}
    angle = Rotation.from_rotvec(rotation.ravel())
    shift = translation.ravel()
    index = inliers.ravel()
    residual = np.linalg.norm(angle.apply(reference[valid][index]) + shift - measured[valid][index], axis=1)
    nominal = np.linalg.inv(model.camera_pose(second['arm'])) @ model.camera_pose(first['arm'])
    delta = Rotation.from_matrix(nominal[:3, :3]).inv() * angle
    return {'valid': len(index) >= 30 and float(np.median(residual)) <= .006,
            'sources_sha256': [first['sha256'], second['sha256']], 'matches': len(matches),
            'inliers': len(index), 'depth_residual_m_p50_p90': np.percentile(residual, [50, 90]).tolist(),
            'measured_translation_m': shift.tolist(), 'measured_rotation_deg': float(np.degrees(angle.magnitude())),
            'nominal_translation_m': nominal[:3, 3].tolist(),
            'translation_difference_m': float(np.linalg.norm(shift - nominal[:3, 3])),
            'rotation_difference_deg': float(np.degrees(delta.magnitude()))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('before', 'after', 'repeat', 'output'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    detector = cv2.SIFT_create(nfeatures=6000, contrastThreshold=.015)
    before, after, repeat = [load_group(folder, detector) for folder in (args.before, args.after, args.repeat)]
    matcher, model = cv2.BFMatcher(), ArmModel()
    rows = {'different_arm_pose': [registered_motion(a, b, matcher, model) for a, b in itertools.product(before, after)],
            'same_arm_pose_after_wait': [registered_motion(a, b, matcher, model) for a, b in zip(after, repeat, strict=True)]}
    summary = {name: {'valid': sum(r['valid'] for r in results), 'attempts': len(results),
                      'median_translation_difference_m': float(np.median([r['translation_difference_m']
                                                                           for r in results if r['valid']]))}
               for name, results in rows.items() if any(r['valid'] for r in results)}
    args.output.parent.mkdir(exist_ok=True, parents=True)
    write_json(args.output, {'scope': 'Same stationary environment. Image-derived relative motion and the native model share depth intrinsics. No absolute chassis calibration or motion commands.',
                             'summary': summary, 'pairs': rows})
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
