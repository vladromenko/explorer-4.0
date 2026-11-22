"""Audit donor instance selection on archived SO-101 observations without robot or training access."""

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

import cv2
import numpy as np

from explorer4 import catalog, so101_geometry
from explorer4.paths import DATA
from explorer4.resources import ResourceLease
from explorer4.so101_vendor import measure
from explorer4.so101_vendor.instances import select_silhouette

EPISODE = "d891e94d13014e3abcda7f1a3dce517e"
FIRST_IMAGE = "234631e258f60c2fdb7d9310b2851e02a60b4ee2c84c2083a80b01b619e2e8ca"
OUTPUT = DATA / "simlab/reports/so101-instance-replay-v3"
BENCH = (
    Path.home()
    / "Projects/so101_autonomous_pick_place/logs/overhead_acceptance/20261103T054910.416568Z"
)
SCANS = (
    "measured-cube-scan",
    "exact-silhouette-scan",
    "final-blocked-scan",
    "after-observation-scan",
)


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recheck_station_masks(folder):
    trials = []
    for name in SCANS:
        path = folder / (name + ".json")
        scan = read(path)
        cubes = [r for r in scan["detections"] if r["label"] == "cube"]
        masks = np.zeros((len(cubes), 720, 1280), np.uint8)
        for mask, proposal in zip(masks, cubes, strict=True):
            contours = [
                np.asarray(p, np.int32) for p in proposal["silhouette_polygons_px"]
            ]
            cv2.fillPoly(mask, contours, 1)
        scores = [r["score"] for r in cubes]
        try:
            chosen = select_silhouette(masks, scores)
            measurement = {"chosen_index": chosen}
        except ValueError as exc:
            measurement = {"chosen_index": None, "reason": str(exc)}
        trials.append(
            {
                "file": path.name,
                "sha256": digest(path),
                "frame": scan["frame"]["sequence"],
                "proposals": len(cubes),
                "scores": scores,
                "old_index": int(np.argmax(scores)),
                "new_measurement": measurement,
            }
        )
    return trials


def replay_registered_frames(root, records, calibration, settings):
    # Use evenly spaced observations selected before evaluating the archived JPEGs.
    distinct = {}
    for r in records:
        distinct.setdefault(r["camera_sequence"], r)
    rows = list(distinct.values())
    result = []
    for i in np.linspace(0, len(rows) - 1, 12, dtype=int):
        row = rows[i]
        path = root / row["image"]
        bgr = cv2.imread(str(path))
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        missing = {**settings, "marker_id": settings["marker_id"] + 1}
        registered = so101_geometry.registered_dimensions(
            rgb, calibration, settings, "cube", settings["instance_id"]
        )
        wrong = so101_geometry.registered_dimensions(
            rgb, calibration, missing, "cube", settings["instance_id"]
        )
        result.append(
            {
                "camera_sequence": row["camera_sequence"],
                "image": path.name,
                "sha256": digest(path),
                "archived_detection": row["visual"]["valid"],
                "registered": registered,
                "wrong_id": wrong,
            }
        )
    return result


def draw_first_frame(source, target, report):
    """Show the actual tag and the text-prompt detection on the same source pixels."""
    if (
        digest(source) != report["frame_sha256"]
        or digest(source) != report["segmentation"]["input_sha256"]
    ):
        raise ValueError("Source image differs from the audited detection")
    image = cv2.imread(str(source))
    corners = np.rint(report["first_marker"]["marker_corners_px"]).astype(np.int32)
    box = np.rint(report["segmentation"]["boxes_xyxy"][0]).astype(int).reshape(2, 2)
    points = np.vstack([corners, box])
    x0, y0 = np.maximum(points.min(axis=0) - 72, 0)
    x1, y1 = np.minimum(points.max(axis=0) + 73, image.shape[1::-1])
    crop = image[y0:y1, x0:x1].copy()
    offset = np.array([x0, y0])
    p, q = box - offset
    amber, green = (0, 190, 255), (110, 240, 75)
    cv2.rectangle(crop, tuple(p), tuple(q), amber, 2)
    cv2.polylines(crop, [(corners - offset).astype(np.int32)], True, green, 2)
    canvas = cv2.copyMakeBorder(
        crop, 0, 58, 0, 0, cv2.BORDER_CONSTANT, value=(22, 27, 29)
    )
    for y, color, title in [
        (23, amber, "SAM 3 text prompt: cube"),
        (47, green, f"Operator-registered cube, tag {report['marker_id']}"),
    ]:
        cv2.line(canvas, (14, len(crop) + y - 5), (35, len(crop) + y - 5), color, 3)
        cv2.putText(
            canvas,
            title,
            (44, len(crop) + y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.54,
            (244, 244, 244),
            1,
            cv2.LINE_AA,
        )
    if not cv2.imwrite(str(target), canvas):
        raise OSError(f"Cannot write {target}")


def replay(out, bench):
    from explorer4 import perception

    out.mkdir(parents=True, exist_ok=True)
    with catalog.connect() as db:
        row = db.execute("SELECT * FROM episodes WHERE id=?", (EPISODE,)).fetchone()
    if (
        not row
        or row["profile"] != "so101_pick_place"
        or row["category"] != "demonstration"
        or row["excluded"]
    ):
        raise ValueError("Expected the included physical SO-101 demonstration")
    root = Path(row["dataset"]) / "donor_geometry"
    meta = read(root / "provenance.json")
    settings = meta["settings"]
    first = root / "000000.jpg"
    if (
        digest(first) != FIRST_IMAGE
        or digest(measure.CALIBRATION) != meta["calibration_sha256"]
    ):
        raise ValueError("Image or calibration differs from the archived recording")
    identity = settings["instance_id"]
    calibration = meta["calibration_snapshot"]
    rgb = cv2.cvtColor(cv2.imread(str(first)), cv2.COLOR_BGR2RGB)
    positive = so101_geometry.marker_object_pose(rgb, calibration, settings)
    wrong = so101_geometry.marker_object_pose(
        rgb, calibration, {**settings, "marker_id": settings["marker_id"] + 1}
    )
    # Replay the same recorded camera encodings and track how many are distinct.
    records = [
        json.loads(line)
        for line in (root / "measurements.jsonl").read_text().splitlines()
    ]
    visible_records = [r for r in records if r.get("visual", {}).get("valid") is True]
    report = {
        "scope": "Retrospective, passive observation of one existing physical demonstration and four earlier bench scans. "
        "No new recorded performance, robot action, fitting, or claim about current camera calibration.",
        "episode": EPISODE,
        "frame_sha256": FIRST_IMAGE,
        "calibration_sha256": meta["calibration_sha256"],
        "first_frame": first.name,
        "marker_dictionary": settings["marker_dictionary"],
        "marker_id": settings["marker_id"],
        "archived_object_dimensions_mm": [1000 * x for x in settings["size_m"]],
        "archived_rows": len(records),
        "archived_camera_sequences": len({r["camera_sequence"] for r in records}),
        "archived_marker_positive_rows": len(visible_records),
        "archived_marker_positive_sequences": len(
            {r["camera_sequence"] for r in visible_records}
        ),
        "first_marker": positive,
        "wrong_id_same_pixels": wrong,
        "archived_bench_scans": recheck_station_masks(bench),
    }
    with tempfile.TemporaryDirectory(dir=out) as tmp:
        with ResourceLease("compute"):
            evidence = measure.measure(
                "cube",
                image=first,
                object_instance=identity,
                device="cuda",
                settings=settings,
                output_root=tmp,
            )
        evidence = {
            k: v
            for k, v in evidence.items()
            if k not in {"image", "overlay", "dir", "calibration"}
        }
        report["first_frame_measurement"] = evidence
        calls = list(Path(tmp).rglob("result.json"))
        if calls:
            segment = read(calls[0])
            report["segmentation"] = {
                k: segment[k]
                for k in ["input_sha256", "prompt", "scores", "boxes_xyxy", "assets"]
            }
        report["sam_revision"] = perception.SAM_REV
        corners = np.asarray(positive["marker_corners_px"], dtype=float)
        box = np.r_[corners.min(axis=0), corners.max(axis=0)].tolist()
        with ResourceLease("compute"):
            guided = perception.analyze(
                first,
                Path(tmp) / "tag-prompt",
                "sam3",
                "cube",
                device="cuda",
                positive_box=box,
            )
        with np.load(guided["masks"], allow_pickle=False) as stored:
            x, y = np.rint(corners).astype(int).T
            coverage = [
                {
                    "mask_sha256_uint8": hashlib.sha256(
                        mask.astype(np.uint8).tobytes()
                    ).hexdigest(),
                    "shape_hw": list(mask.shape),
                    "marker_corners_inside": int(np.count_nonzero(mask[y, x])),
                }
                for mask in stored["masks"]
            ]
            try:
                selected = select_silhouette(stored["masks"], guided["scores"], corners)
            except ValueError:
                selected = None
        report["positive_marker_box_control"] = {
            "geometry_from": "Axis-aligned enclosing rectangle of the detected tag corners only.",
            "box_xyxy": box,
            "scores": guided["scores"],
            "proposals_xyxy": guided["boxes_xyxy"],
            "mask_containing_all_corners": selected,
            "mask_corner_coverage": coverage,
        }
    report["registered_dimension_retrieval"] = replay_registered_frames(
        root, records, calibration, settings
    )
    report["interpretation"] = (
        "Registered dimensions were supplied by the operator. Successful retrieval verifies recognition "
        "from a newly decoded archive image. It does not independently estimate object size or verify a physical grasp. "
        "The marker-box control supplies a localized visual prompt to upstream SAM 3. The four multi-cube scans "
        "are archived views of one laboratory setup and their proposals are model outputs."
    )
    target = out / "result.json"
    raw = json.dumps(report, indent=2, allow_nan=False, ensure_ascii=False) + "\n"
    if target.exists() and read(target) != report:
        raise ValueError("Existing evidence differs; use a different output directory")
    target.write_text(raw)
    draw_first_frame(first, out / "first-frame.png", report)
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--bench", type=Path, default=BENCH)
    args = parser.parse_args()
    print(replay(args.output, args.bench))
