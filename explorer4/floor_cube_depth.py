"""Localize a single known-size floor cube in metric depth with measured floor tilt."""

import cv2
import numpy as np

from .peer_dock_shelf import normalized_rays


def fit_floor(samples):
    points = samples
    for _ in range(3):
        if len(points) < 400 or np.min(np.ptp(points[:, :2], axis=0)) < .07:
            return None
        origin = np.median(points, axis=0)
        _, _, axes = np.linalg.svd(points - origin, full_matrices=False)
        normal = axes[-1] * np.sign(axes[-1, 2])
        if normal[2] < .97:
            return None
        points = samples[np.abs((samples - origin) @ normal) < .006]
    if len(points) < .7 * len(samples):
        return None
    return origin, normal, len(points)


def find_floor_cube(depth_m, camera_info, base_from_camera, bounds, size=.032):
    """Return a unique candidate. The floor must be visible and the camera mount is an input."""
    depth = np.asarray(depth_m)
    y, x = np.where(np.isfinite(depth) & (depth > .15) & (depth < .95))
    if len(x) < 1000:
        return None
    camera = normalized_rays(camera_info, np.c_[x, y]) * depth[y, x, None]
    points = camera @ base_from_camera[:3, :3].T + base_from_camera[:3, 3]
    xrange, yrange = bounds
    inside = ((points[:, 0] >= xrange[0]) & (points[:, 0] <= xrange[1])
              & (points[:, 1] >= yrange[0]) & (points[:, 1] <= yrange[1]))
    floor = fit_floor(points[inside & (np.abs(points[:, 2]) < .033)][::8])
    if floor is None:
        return None
    origin, normal, supporting = floor
    heights = (points - origin) @ normal
    top = inside & (np.abs(heights - size) <= .007)
    pixels = np.zeros(depth.shape, dtype=np.uint8)
    pixels[y[top], x[top]] = 1
    count, labels, stats, _ = cv2.connectedComponentsWithStats(pixels)
    objects = []
    membership = labels[y, x]
    for component in range(1, count):
        bx, by, w, h, area = stats[component]
        if (area < 120 or bx == 0 or by == 0 or bx + w == depth.shape[1] or by + h == depth.shape[0]):
            continue
        surface = points[membership == component, :2].astype(np.float32)
        center, sides, angle = cv2.minAreaRect(surface)
        if all(.78 * size <= width <= 1.25 * size for width in sides):
            objects.append((center, sides, angle, int(area)))
    if len(objects) != 1:
        return None
    center, sides, angle, count = objects[0]
    return {'base_xy_m': list(center), 'face_sides_m': list(sides), 'orientation_deg_mod_90': angle % 90,
            'depth_pixels': count, 'floor_points': supporting,
            'floor_tilt_from_nominal_deg': float(np.degrees(np.arccos(np.clip(normal[2], 0., 1.))))}
