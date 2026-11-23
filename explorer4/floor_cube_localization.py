"""Find the measured top surface of a known floor cube in a registered depth frame."""

import numpy as np


def top_surface(depth, intrinsics, base_from_camera, size, bounds):
    """Return base-frame top candidates from metric depth and an OpenCV camera frame."""
    depth = np.asarray(depth)
    fx, fy, cx, cy = intrinsics
    r, c = np.indices(depth.shape)
    points = np.stack(((c - cx) * depth / fx, (r - cy) * depth / fy, depth), axis=-1)
    points = points @ base_from_camera[:3, :3].T + base_from_camera[:3, 3]
    x, y = bounds
    valid = (
        np.isfinite(depth) & (depth > 0) & (depth < 2)
        & (np.abs(points[:, :, 2] - size) < .003)
        & (points[:, :, 0] > x[0] - size) & (points[:, :, 0] < x[1] + size)
        & (points[:, :, 1] > y[0] - size) & (points[:, :, 1] < y[1] + size)
    )
    return points[valid, :2]


def cube_center(points, size, bounds):
    """Reject partial, oversized or out-of-workspace faces before moving the arm."""
    if len(points) < 100:
        return None
    low, high = np.percentile(points, [2, 98], axis=0)
    width = high - low
    if np.any(width < .84 * size) or np.any(width > 1.10 * size):
        return None
    center = (low + high) / 2
    if any(not low <= value <= high for value, (low, high) in zip(center, bounds, strict=True)):
        return None
    return center
