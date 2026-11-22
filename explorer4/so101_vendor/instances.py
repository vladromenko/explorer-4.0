"""Bind a station measurement to one object silhouette before sharing it with a recipient."""

import cv2
import numpy as np


def same_proposal(mask, other):
    # Same-label mask NMS from so101_pick_place.vision.sam3_detector.Sam3Detector._deduplicate.
    # It groups tight duplicates and nested SAM masks without merging disjoint objects.
    intersection = np.count_nonzero(mask & other)
    smaller = min(np.count_nonzero(mask), np.count_nonzero(other))
    union = np.count_nonzero(mask | other)
    return intersection >= 0.75 * union or intersection > 0.85 * smaller


def marker_in_mask(mask, corners):
    corners = np.asarray(corners, dtype=float)
    if corners.shape != (4, 2) or not np.isfinite(corners).all():
        raise ValueError("Неполное наблюдение метки предмета")
    x, y = np.rint(corners).astype(int).T
    inside = (x >= 0) & (x < mask.shape[1]) & (y >= 0) & (y < mask.shape[0])
    return bool(inside.all() and mask[y, x].all())


def select_silhouette(masks, scores, corners=None):
    """Return the unique eligible proposal. For a marked object require its four corners in the mask."""
    masks = np.asarray(masks, dtype=bool)
    scores = np.asarray(scores, dtype=float)
    if (
        masks.ndim != 3
        or scores.shape != (len(masks),)
        or not np.isfinite(scores).all()
    ):
        raise ValueError("Неполный результат сегментации камеры SO-101")
    candidates = []
    distant = []
    if corners is not None:
        # A large union can contain the tag and a second, independently
        # segmented object. Keep those other proposals as contrary evidence.
        points = np.asarray(corners, dtype=float)
        if points.shape != (4, 2) or not np.isfinite(points).all():
            raise ValueError("Неполное наблюдение метки предмета")
        tag_region = np.zeros(masks.shape[1:], dtype=np.uint8)
        cv2.fillConvexPoly(tag_region, np.rint(points).astype(np.int32), 1)
        tag_pixels = tag_region.astype(bool)
        distant = [
            mask for mask in masks if mask.sum() >= 150 and not mask[tag_pixels].any()
        ]
    for index in np.argsort(-scores, kind="stable"):
        mask = masks[index]
        if not mask.any() or (
            corners is not None and not marker_in_mask(mask, corners)
        ):
            continue
        component = metric_component(mask)
        if any(same_proposal(component, other) for other in distant):
            continue
        if corners is None or marker_in_mask(component, corners):
            candidates.append((int(index), component))
    if not candidates:
        raise ValueError("Нет силуэта, соответствующего выбранному предмету")
    # A high-score mask covering A and B can match both. Check each pair
    # so that this union cannot hide two separate hypotheses by suppression.
    for i, (_, mask) in enumerate(candidates):
        if any(not same_proposal(mask, other) for _, other in candidates[:i]):
            raise ValueError(
                "Камера видит несколько подходящих контуров. Уточните предмет для измерения."
            )
    return candidates[0][0]


def metric_component(mask):
    """Select the connected foreground used by the station's metric cuboid fit."""
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        np.uint8(mask), connectivity=8
    )
    if count == 1:
        raise ValueError("Пустой силуэт предмета")
    areas = stats[1:, cv2.CC_STAT_AREA]
    if np.count_nonzero(areas >= 150) > 1:
        raise ValueError(
            "Камера видит несколько подходящих контуров. Уточните предмет для измерения."
        )
    return labels == 1 + int(np.argmax(areas))
