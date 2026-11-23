"""Independent optical endpoint pose from a known unmarked shelf corner."""

import math

import numpy as np

from .fleet_map import Grid, inverse, scan_points, thin, wrap
from .peer_dock_real import matrix
from .peer_dock_shelf import front_plane, from_tf, intersection, normalized_rays, observe, shelf_lines
from .peer_shelf_run import tank_mount


def left_corner(packet, reference):
    """The left divider can still be visible when the right edge has left the frame."""
    streams = packet['meta']['streams']
    arrays = packet['arrays']
    camera, color = streams['depth'], streams['rgb']
    depth_info, rgb_info = streams['depth_info'], streams['rgb_info']
    depth = arrays['depth']
    if (camera['frame_id'] != depth_info['frame_id'] or color['frame_id'] != rgb_info['frame_id']
            or depth.shape != (depth_info['height'], depth_info['width'])
            or arrays['rgb'].shape[:2] != (rgb_info['height'], rgb_info['width'])
            or camera.get('unit') not in ('mm', 'm')):
        raise ValueError('Endpoint camera format changed')
    depth_m = depth * (.001 if camera['unit'] == 'mm' else 1.)
    plane, offset, residual, count = front_plane(depth_m, depth_info, reference['plane'])
    lines = shelf_lines(arrays['rgb'], reference['lines'])
    corner = intersection(lines['left'], lines['bottom'])
    if not (-.05 * rgb_info['width'] <= corner[0] <= 1.05 * rgb_info['width']
            and -.06 * rgb_info['height'] <= corner[1] <= 1.06 * rgb_info['height']):
        raise ValueError('The corner would require extrapolation beyond the registered image margin')
    up = corner + 100 * np.asarray([lines['left'][1], -lines['left'][0]]) * np.sign(lines['left'][0])
    rgb_to_depth = from_tf(camera['frame_id'], color['frame_id'], streams['tf_static']['transforms'])
    rays = normalized_rays(rgb_info, [corner, up]) @ rgb_to_depth[:3, :3].T
    origin = rgb_to_depth[:3, 3]
    distances = (offset - origin @ plane) / (rays @ plane)
    if not np.all(np.isfinite(distances) & (distances > .15) & (distances < 1.)):
        raise ValueError('The endpoint corner does not intersect the reconstructed shelf')
    lower, higher = origin + rays * distances[:, None]
    vertical = higher - lower
    vertical /= np.linalg.norm(vertical)
    horizontal = np.cross(vertical, -plane)
    horizontal /= np.linalg.norm(horizontal)
    return matrix(np.column_stack((horizontal, vertical, -plane)), lower), {
        'corner_px': corner.tolist(), 'front_plane_residual_m_p90': residual, 'plane_support': count,
    }


def estimate(anchor, endpoint, start_reference, end_reference):
    observed = observe(anchor, start_reference)
    start_right = np.asarray(observed['depth_from_shelf'])
    right_from_left = np.eye(4)
    right_from_left[0, 3] = observed['witness_in_shelf_m'][0]
    start_base_from_left = tank_mount(anchor) @ start_right @ right_from_left
    end_left, measurement = left_corner(endpoint, end_reference)
    end_base_from_left = tank_mount(endpoint) @ end_left
    pose = start_base_from_left @ np.linalg.inv(end_base_from_left)
    yaw = math.atan2(pose[1, 0], pose[0, 0])
    return {'pose_xy_yaw': [*pose[:2, 3].tolist(), yaw], 'height_offset_m': float(pose[2, 3]), **measurement}


def starting_alignment(anchor, current):
    """Estimate how to restore a start on natural geometry. It grants no motor permission."""
    left, right = (packet['meta'] for packet in (anchor, current))
    if (not left.get('source_sha256') or left['source_sha256'] != right.get('source_sha256')
            or left['streams']['scan']['frame_id'] != right['streams']['scan']['frame_id']):
        raise ValueError('The lidar publisher or frame changed')
    start_scan, current_scan = (scan_points('tank', packet) for packet in (anchor, current))
    start_points, current_points = (thin(scan, .04, 360) for scan in (start_scan, current_scan))
    if min(len(start_points), len(current_points)) < 70:
        raise ValueError('The two scans contain insufficient layout geometry')
    grids = (Grid(), Grid())
    for grid, scan in zip(grids, (start_scan, current_scan), strict=True):
        grid.add(scan, (0., 0.))
    refinement = ((.06, .015, math.radians(7), math.radians(1)),
                  (.025, .005, math.radians(1.5), math.radians(.25)))
    broad = (.32, .04, math.radians(42), math.radians(6))
    _, pose = grids[0].refine(current_points, (0., 0., 0.), (broad, *refinement))
    overlap = grids[0].inliers(current_points, pose)
    expected_inverse = inverse(pose)
    _, reverse = grids[1].refine(start_points, expected_inverse, refinement)
    position_residual = math.dist(expected_inverse[:2], reverse[:2])
    yaw_residual = abs(wrap(expected_inverse[2] - reverse[2]))
    if overlap < .72 or position_residual > .025 or yaw_residual > math.radians(3):
        raise ValueError('The start cannot be localized consistently to the recorded shelf area')
    return {'pose_in_start_frame': list(pose), 'lidar_overlap': overlap, 'reverse_error_m': position_residual,
            'reverse_error_deg': math.degrees(yaw_residual),
            'within_start_tolerance': math.hypot(*pose[:2]) <= .015 and abs(pose[2]) <= math.radians(3)}
