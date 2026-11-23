"""Static RGB-D registration to a natural shelf, with no actuator access."""

import cv2
import numpy as np
from scipy.spatial.transform import Rotation

from .peer_dock_config import STANDOFF_M
from .peer_dock_real import matrix


def normalized_rays(info, uv):
    K = np.asarray(info["k"], dtype=float).reshape(3, 3)
    distortion = np.asarray(info["d"], dtype=float)
    if min(K[0, 0], K[1, 1]) <= 0 or not np.isfinite(K).all() or not np.isfinite(distortion).all():
        raise ValueError("Invalid camera intrinsics")
    xy = cv2.undistortPoints(np.asarray(uv, float).reshape(-1, 1, 2), K, distortion)
    return np.column_stack((xy.reshape(-1, 2), np.ones(len(xy))))


def from_tf(parent, child, transforms):
    """Compose the published parent-from-child rigid transforms."""
    graph = {}
    for link in transforms:
        pose = matrix(Rotation.from_quat(link["quaternion_xyzw"]).as_matrix(), link["translation"])
        left, right = link["parent"], link["child"]
        graph.setdefault(left, []).append((right, pose))
        graph.setdefault(right, []).append((left, np.linalg.inv(pose)))
    pending, visited = [(parent, np.eye(4))], {parent}
    for node, transform in pending:
        if node == child:
            return transform
        for other, local in graph.get(node, []):
            if other not in visited:
                pending.append((other, transform @ local))
                visited.add(other)
    raise ValueError(f"No published transform from {child} to {parent}")


def front_plane(depth_m, info, rois):
    kept = np.zeros(depth_m.shape, dtype=bool)
    for x1, y1, x2, y2 in rois:
        kept[y1:y2, x1:x2] = True
    y, x = np.where(kept & np.isfinite(depth_m) & (depth_m > .15) & (depth_m < 1.))
    if len(x) < 400:
        raise ValueError("Too few returns from the marked image regions of the shelf front")
    points = normalized_rays(info, np.c_[x, y]) * depth_m[y, x, None]
    center = np.median(points, axis=0)
    _, _, vectors = np.linalg.svd(points - center, full_matrices=False)
    members = points[np.abs((points - center) @ vectors[-1]) < .007]
    if len(members) < max(400, .75 * len(points)):
        raise ValueError("Depth regions do not support one common front plane")
    center = members.mean(axis=0)
    _, sv, vectors = np.linalg.svd(members - center, full_matrices=False)
    normal = vectors[-1] * np.sign(vectors[-1, 2])
    error = float(np.quantile(np.abs((members - center) @ normal), .9))
    if sv[1] / np.sqrt(len(members)) < .015 or normal[2] < .6 or error > .005:
        raise ValueError("Shelf front plane is poorly constrained")
    return normal, float(normal @ center), error, len(members)


def image_line(points):
    v = np.cross(*np.c_[points, np.ones(2)])
    n = np.linalg.norm(v[:2])
    if n < 1e-6 or not np.isfinite(n):
        raise ValueError("Degenerate image segment")
    return v / n


def shelf_lines(rgb, references):
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    detected = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD).detect(gray)[0]
    if detected is None:
        raise ValueError("No line segments in the expected shelf image")
    lines = detected.reshape(-1, 2, 2)
    lengths = np.linalg.norm(lines[:, 1] - lines[:, 0], axis=1)
    homogeneous = np.c_[lines.reshape(-1, 2), np.ones(2 * len(lines))]
    result = {}
    for name, reference in references.items():
        distance = np.abs(homogeneous @ image_line(reference)).reshape(-1, 2).max(axis=1)
        close = lines[(distance < 2.8) & (lengths >= 30)]
        if len(close) == 0:
            raise ValueError(f"Missing shelf line {name}")
        dx, dy, x, y = cv2.fitLine(close.reshape(-1, 2), cv2.DIST_L2, 0, .01, .01).ravel()
        result[name] = image_line([[x, y], [x + dx, y + dy]])
    return result


def intersection(a, b):
    xyw = np.cross(a, b)
    if abs(xyw[2]) < .3:
        raise ValueError("Expected near-perpendicular shelf edges")
    return xyw[:2] / xyw[2]


def observe(packet, regions):
    streams = packet["meta"]["streams"]
    arrays = packet["arrays"]
    camera = streams["depth"]
    rgb = streams["rgb"]
    depth_info, rgb_info = (streams[f"{k}_info"] for k in ("depth", "rgb"))
    depth = arrays["depth"]
    if (camera["frame_id"] != depth_info["frame_id"] or rgb["frame_id"] != rgb_info["frame_id"]
            or depth.shape != (depth_info["height"], depth_info["width"])
            or arrays["rgb"].shape[:2] != (rgb_info["height"], rgb_info["width"])
            or camera.get("unit") not in {"mm", "m"}):
        raise ValueError("Depth and RGB stream metadata changed")
    normal, offset, error, count = front_plane(
        depth.astype(float) * (.001 if camera["unit"] == "mm" else 1.), depth_info, regions["plane"]
    )
    lines = shelf_lines(arrays["rgb"], regions["lines"])
    corner_uv = intersection(lines["right"], lines["bottom"])
    witness_uv = intersection(lines["left"], lines["bottom"])
    up_uv = corner_uv + 100 * np.array([lines["right"][1], -lines["right"][0]]) * np.sign(lines["right"][0])
    rays = normalized_rays(rgb_info, [corner_uv, up_uv, witness_uv])
    transforms = streams.get("tf_static", {}).get("transforms", [])
    depth_from_rgb = from_tf(camera["frame_id"], rgb["frame_id"], transforms)
    origin = depth_from_rgb[:3, 3]
    rays = rays @ depth_from_rgb[:3, :3].T
    scales = (offset - origin @ normal) / (rays @ normal)
    if not np.all(np.isfinite(scales) & (scales > .15) & (scales < 1.)):
        raise ValueError("Shelf corners do not intersect the observed front plane")
    corner, upper, witness = origin + rays * scales[:, None]
    up = upper - corner
    up /= np.linalg.norm(up)
    right = np.cross(up, -normal)
    right /= np.linalg.norm(right)
    depth_from_shelf = matrix(np.column_stack((right, up, -normal)), corner)
    check = np.linalg.inv(depth_from_shelf) @ np.r_[witness, 1.]
    if not -.65 < check[0] < -.25 or abs(check[1]) > .015:
        raise ValueError("The held-out divider does not agree with the shelf corner")
    return {
        "depth_from_shelf": depth_from_shelf.tolist(), "witness_in_shelf_m": check[:3].tolist(),
        "corner_px": corner_uv.tolist(), "witness_px": witness_uv.tolist(),
        "plane_p90_m": error, "plane_inlier_count": count,
    }


def tank_base_from_depth(packet):
    streams = packet["meta"]["streams"]
    return from_tf(
        "base_footprint", streams["depth"]["frame_id"], streams["tf_static"]["transforms"]
    )


def goal_from_shelf(base_from_shelf, width):
    outward = base_from_shelf[:2, 2].copy()
    outward /= np.linalg.norm(outward)
    center = (base_from_shelf @ [-width / 2, 0, 0, 1])[:2]
    return np.r_[center + STANDOFF_M * outward, np.arctan2(-outward[1], -outward[0])].tolist()
