"""Compare the two installed open-vocabulary detectors on identical archived SO-101 frames."""

import argparse
import base64
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

from explorer4 import catalog
from explorer4.paths import DATA, ROOT, offline_environment
from explorer4.resources import ResourceLease
from explorer4.vision_assets import verify

SOURCE = ROOT / "docs/results/research-audit-20261122/so101-instance-replay.json"
WORKER = ROOT / "scripts/vision_worker.py"
PUBLIC = DATA / "simlab/reports/cube-detector-comparison-v1"
METHODS = ("sam3", "yoloe")
PROMPTS = ("cube", "cube with a black and white marker on top")
CONFIDENCE = 0.4


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preserve(path, value):
    encoded = json.dumps(value, indent=2, allow_nan=False, sort_keys=True) + "\n"
    if path.exists() and path.read_text() != encoded:
        raise ValueError(f"Saved evidence differs at {path}")
    if not path.exists():
        temp = path.with_suffix(".partial")
        temp.write_text(encoded)
        temp.replace(path)


def load_inputs():
    source = json.loads(SOURCE.read_bytes())
    rows = source["registered_dimension_retrieval"]
    with catalog.connect() as db:
        episode = db.execute(
            "SELECT * FROM episodes WHERE id=?", (source["episode"],)
        ).fetchone()
    if (
        episode is None
        or episode["excluded"]
        or episode["profile"] != "so101_pick_place"
        or episode["category"] != "demonstration"
    ):
        raise ValueError("Expected the same included SO-101 operator recording")
    root = Path(episode["dataset"]) / "donor_geometry"
    images = [root / row["image"] for row in rows]
    if len(rows) != 12 or len({row["camera_sequence"] for row in rows}) != 12:
        raise ValueError("Expected the original twelve distinct camera sequences")
    for row, image in zip(rows, images, strict=True):
        if checksum(image) != row["sha256"]:
            raise ValueError(f"Changed source JPEG {image.name}")
    return source, rows, images


def protocol(source, rows):
    return {
        "study": "Retrospective text-prompt comparison on one previously inspected physical SO-101 demonstration",
        "episode": source["episode"],
        "source_sha256": checksum(SOURCE),
        "implementation_sha256": {
            p.name: checksum(p)
            for p in (WORKER, Path(__file__), ROOT / "configs/vision-assets.json")
        },
        "methods": METHODS,
        "prompts": PROMPTS,
        "confidence": CONFIDENCE,
        "camera_sequences": [row["camera_sequence"] for row in rows],
        "endpoint": "Highest-scoring returned box contains all four corners of the independently read ID 1. Also count any qualifying box. Only frames with a readable tag have this label. All boxes remain in the report.",
        "input": "Identical original full-resolution JPEGs. No boxes, tag ID, coordinates, or reference image supplied to either detector. Prompts were fixed before cross-frame model calls.",
        "limits": "Bounding-box coverage of the marker is a positional proxy. It can include adjacent objects. Frames from this one recording are correlated. The deployment camera, physical grasp and tracking through occlusion are separate evaluations.",
        "optimizer_updates": 0,
        "physical_trials": 0,
    }


def infer(method, images):
    messages = [
        json.dumps(
            {
                "prompt": prompt,
                "conf": CONFIDENCE,
                "jpeg_b64": base64.b64encode(img.read_bytes()).decode("ascii"),
            }
        )
        for prompt in PROMPTS
        for img in images
    ]
    with ResourceLease("compute"):
        verify(DATA / "cache/vision", method)
        worker = subprocess.run(
            [sys.executable, str(WORKER), method],
            cwd=ROOT,
            env=offline_environment(),
            input="\n".join(messages) + "\n",
            text=True,
            stdout=subprocess.PIPE,
            check=True,
            timeout=300,
        )
    ready = False
    outputs = []
    for line in worker.stdout.splitlines():
        try:
            response = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(response, dict):
            continue
        if response.get("ready"):
            ready = (
                response.get("method") == method and response.get("device") == "cuda"
            )
        elif "error" in response:
            raise RuntimeError(response["error"])
        elif "boxes" in response:
            outputs.append(response["boxes"])
    if not ready or len(outputs) != len(messages):
        raise ValueError(f"Incomplete GPU worker results for {method}")
    return outputs


def score(boxes, row):
    if any(
        len(b) != 5 or not all(map(math.isfinite, b)) or b[2] < b[0] or b[3] < b[1]
        for b in boxes
    ):
        raise ValueError("Malformed detector output")
    observation = row["registered"]
    result = {
        "camera_sequence": row["camera_sequence"],
        "jpeg_sha256": row["sha256"],
        "boxes_xyxy_score": boxes,
        "top_covers_tag": None,
        "any_covers_tag": None,
    }
    if observation["ok"]:
        corners = observation["marker"]["corners_px"]
        ranked = sorted(boxes, key=lambda b: -b[4])
        hits = [
            all(x1 <= x <= x2 and y1 <= y <= y2 for x, y in corners)
            for x1, y1, x2, y2, _ in ranked
        ]
        result.update(top_covers_tag=bool(hits and hits[0]), any_covers_tag=any(hits))
    return result


def run(prepare_only):
    source, rows, images = load_inputs()
    PUBLIC.mkdir(parents=True, exist_ok=True)
    preserve(PUBLIC / "protocol.json", protocol(source, rows))
    if prepare_only:
        return
    trials, summaries = {}, {}
    for method in METHODS:
        results = iter(infer(method, images))
        trials[method], summaries[method] = {}, {}
        for prompt in PROMPTS:
            entries = [score(next(results), row) for row in rows]
            trials[method][prompt] = entries
            summaries[method][prompt] = {
                "readable_tag_frames": sum(
                    e["top_covers_tag"] is not None for e in entries
                ),
                "top_covers_tag": sum(e["top_covers_tag"] is True for e in entries),
                "any_covers_tag": sum(e["any_covers_tag"] is True for e in entries),
                "returned_any_of_all_12": sum(
                    bool(e["boxes_xyxy_score"]) for e in entries
                ),
            }
    preserve(
        PUBLIC / "result.json",
        {
            "protocol_sha256": checksum(PUBLIC / "protocol.json"),
            "summary": summaries,
            "trials": trials,
        },
    )
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    run(parser.parse_args().prepare)
