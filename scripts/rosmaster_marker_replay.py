"""Look for the registered SO-101 tag in the frozen training videos from the ROSMASTER floor-cube pilot."""

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

import av
import cv2

from explorer4.datasets import fingerprint, load_plan
from explorer4.paths import DATA, ROOT

PLAN = "22a6506624dc67b0ff460e0e9d4a45b078fb0ad91a6a764c766026606e7f5978"
AUDIT = ROOT / "docs/results/research-audit-20261122"
REFERENCE = AUDIT / "so101-instance-replay.json"
PUBLIC = DATA / "simlab/reports/rosmaster-marker-replay-v1"
FAMILY = "DICT_APRILTAG_36h11"
TARGET, WRONG, SAMPLES = 1, 2, 12


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(path.read_text())


def evidence(detector, rgb, folder, name):
    corners, detected, _ = detector.detectMarkers(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY))
    markers = (
        []
        if detected is None
        else [
            {"id": int(i), "corners_px": q[0].tolist()}
            for i, q in zip(detected.ravel(), corners, strict=True)
        ]
    )
    ok, png = cv2.imencode(".png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    if not ok:
        raise ValueError("Unable to preserve the decoded frame")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (name + ".png")
    encoded = png.tobytes()
    if path.exists() and digest(path.read_bytes()) != digest(encoded):
        raise ValueError("Published frame has changed: " + str(path))
    if not path.exists():
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(encoded)
        temporary.replace(path)
    return {
        "markers": markers,
        "target": any(m["id"] == TARGET for m in markers),
        "wrong_id": any(m["id"] == WRONG for m in markers),
        "shape_hwc": list(rgb.shape),
        "rgb_sha256": digest(rgb.tobytes()),
        "png_sha256": digest(encoded),
        "frame_url": "/simlab-media/" + str(path.relative_to(DATA / "simlab")),
    }


def training_rows(plan):
    parent = load_plan(plan["parent_plan_id"], verify=False)
    eligible = {r["id"] for r in parent["splits"]["train"]}
    sealed = {
        r["id"] for split in ("validation", "test") for r in plan["splits"][split]
    }
    accepted = []
    with sqlite3.connect(f"file:{DATA}/catalog.sqlite3?mode=ro", uri=True) as db:
        for row in plan["splits"]["train"]:
            ident = row["id"]
            source = row.get("source_episode", ident)
            root = Path(row["dataset"])
            prefix = ident != source
            status = db.execute(
                "SELECT profile,category,excluded FROM episodes WHERE id=?", (source,)
            ).fetchone()
            if (
                ident in sealed
                or source in sealed
                or row["profile"] != "rosmaster_pick_place"
                or status != ("rosmaster_pick_place", "demonstration", int(prefix))
            ):
                raise ValueError("Unexpected source, split or current catalogue status")
            expected = (
                DATA
                / "datasets"
                / ("article-human-prefix-v1" if prefix else "rosmaster_pick_place")
                / ident
            )
            if root.resolve() != expected or fingerprint(root) != row["sha256"]:
                raise ValueError("Training source differs from its frozen bytes")
            raw = read(root / "provenance.json")
            if prefix:
                if (
                    raw["role"] != "train"
                    or raw["source_episode"] != source
                    or raw["span"] != [0, row["frames"]]
                    or row["span"] != raw["span"]
                    or raw["source_sha256"] != row["source_sha256"]
                ):
                    raise ValueError("Unregistered training prefix")
            elif (
                ident not in eligible
                or raw["domain"] != "real"
                or raw["command_source"] != "human"
                or raw["category"] != "demonstration"
                or raw["profile"]["camera"] != "front"
            ):
                raise ValueError("Unregistered human demonstration or camera")
            accepted.append(
                (
                    row,
                    root,
                    "approved_training_prefix"
                    if prefix
                    else "included_full_training_take",
                )
            )
    return accepted


def replay():
    cv2.setNumThreads(1)
    # Reading the signed plan file alone must never fingerprint the validation or test datasets.
    plan = load_plan(PLAN, verify=False)
    accepted = training_rows(plan)
    if (
        len(accepted) != 11
        or len({row.get("source_episode", row["id"]) for row, _, _ in accepted}) != 11
    ):
        raise ValueError("Expected 11 separately sourced training inputs")
    reference = read(REFERENCE)
    if (
        reference["marker_dictionary"],
        reference["marker_id"],
        reference["archived_object_dimensions_mm"],
    ) != (FAMILY, TARGET, [29.0] * 3):
        raise ValueError("Unexpected donor marker registration")
    positive = (
        DATA
        / "datasets/so101_pick_place"
        / reference["episode"]
        / "donor_geometry"
        / reference["first_frame"]
    )
    if digest(positive.read_bytes()) != reference["frame_sha256"]:
        raise ValueError("Positive control changed")
    detector = cv2.aruco.ArucoDetector(
        cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, FAMILY))
    )
    rgb = cv2.cvtColor(cv2.imread(str(positive)), cv2.COLOR_BGR2RGB)
    control = evidence(detector, rgb, PUBLIC / "frames", "registered-so101")
    if not control["target"] or control["wrong_id"]:
        raise ValueError("Detector failed the archived SO-101 control")
    episodes = []
    for row, root, role in accepted:
        n = row["frames"]
        indices = [j * (n - 1) // (SAMPLES - 1) for j in range(SAMPLES)]
        meta = read(root / "meta/info.json")
        feature = meta["features"]["observation.images.front"]
        if (
            n != meta["total_frames"]
            or meta["total_episodes"] != 1
            or meta["fps"] != 20
            or feature["shape"] != [480, 640, 3]
            or len(set(indices)) != SAMPLES
        ):
            raise ValueError("Unexpected video contract")
        (video,) = (root / "videos/observation.images.front").glob("*/*.mp4")
        frames = []
        with av.open(str(video)) as container:
            (stream,) = container.streams.video
            stream.thread_count = 1
            for index, frame in enumerate(container.decode(stream)):
                if index in indices:
                    image = frame.to_ndarray(format="rgb24")
                    if image.shape != (480, 640, 3):
                        raise ValueError("Decoded ROSMASTER frame shape differs")
                    detail = evidence(
                        detector, image, PUBLIC / "frames" / row["id"], f"{index:06d}"
                    )
                    frames.append(
                        {
                            "frame_index": index,
                            "video_pts": frame.pts,
                            "time_s": float(frame.time),
                            **detail,
                        }
                    )
        if (
            index + 1 != n
            or [f["frame_index"] for f in frames] != indices
            or len({f["rgb_sha256"] for f in frames}) != SAMPLES
        ):
            raise ValueError("Incomplete selection or repeated decoded pixels")
        episodes.append(
            {
                "id": row["id"],
                "source_episode": row.get("source_episode", row["id"]),
                "role": role,
                "series": row["session"],
                "source_range_half_open": [0, n],
                "training_dataset_sha256": row["sha256"],
                "video_sha256": digest(video.read_bytes()),
                "frames": frames,
            }
        )
    rows = [f for e in episodes for f in e["frames"]]
    parameters = detector.getDetectorParameters()
    return {
        "domain": "archived physical human training recordings; retrospective perception only",
        "script_sha256": digest(Path(__file__).read_bytes()),
        "training_plan_sha256": PLAN,
        "donor_registration": "so101-instance-replay.json",
        "donor_registration_sha256": digest(REFERENCE.read_bytes()),
        "donor_encoded_jpeg_sha256": reference["frame_sha256"],
        "positive_control": control,
        "dictionary": FAMILY,
        "target_id": TARGET,
        "negative_id": WRONG,
        "opencv": cv2.__version__,
        "pyav": av.__version__,
        "detector_parameters": {
            k: getattr(parameters, k)
            for k in dir(parameters)
            if not k.startswith("_")
            and isinstance(getattr(parameters, k), (bool, float, int))
        },
        "sampling": "Decode approved training video only. Before detection fix index floor(j*(N-1)/11), j=0..11. Require distinct raw RGB hashes per episode. Native 640x480 to grayscale, original dictionary defaults, no crops, rescaling, tuning or pose estimates.",
        "camera": "ROSMASTER arm-mounted RGB stored as observation.images.front. Source cube/marker identity across sessions is unverified.",
        "counts": {
            "full_takes": 5,
            "approved_prefixes": 6,
            "sampled_frames": len(rows),
            "target_frames": sum(f["target"] for f in rows),
            "wrong_id_frames": sum(f["wrong_id"] for f in rows),
            "episodes_with_target": sum(
                any(f["target"] for f in e["frames"]) for e in episodes
            ),
        },
        "limitations": "Visibility and identity apply only to the sampled pixels; frame-level detections are correlated. The checked donor image is a positive control from a different camera. No new robot trial or training.",
        "episodes": episodes,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=AUDIT / "rosmaster-marker-replay.json"
    )
    path = parser.parse_args().output
    result = replay()
    path.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(result["counts"])
