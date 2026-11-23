"""Validate an independently instrumented C920 exposure measurement against a donor capture."""

import argparse
import hashlib
import json
import math
import os
import re
import statistics
import tempfile
from pathlib import Path
from uuid import UUID

from explorer4.paths import DATA
from explorer4.so101_packet_builder import camera_fingerprint

OPTICAL = "optical_midpoint_interval"
CLOCK = "CLOCK_MONOTONIC"
READ = "immediately_after_opencv_capture_read"
LIMIT = 20_000_000
MAX_LAG = 250_000_000


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def number(row, field, minimum=0):
    value = row[field]
    if type(value) is not int or value < minimum:
        raise ValueError(f"Expected integer {field} >= {minimum}")
    return value


def bounds(row, low, high, minimum=0):
    a, b = number(row, low, minimum), number(row, high, minimum)
    if a > b:
        raise ValueError(f"Reversed interval for {low}, {high}")
    return a, b


def optical_events(raw, capture):
    """Instrumented light-time intervals, independent of USB/camera timestamps."""
    trace = json.loads(raw)
    if (
        trace["schema"] != "measured-optical-timecode-v1"
        or trace["clock"] != CLOCK
        or trace["boot_id"] != capture["boot_id"]
        or trace["capture_id"] != capture["capture_id"]
    ):
        raise ValueError("Independent optical clock trace does not match this capture")
    events = {}
    last = 0
    for event in trace["events"]:
        code = str(event["code"])
        lo, hi = bounds(event, "earliest_ns", "latest_ns", 1)
        if not code or code in events or lo < last or hi <= lo:
            raise ValueError(
                "Optical codes must have distinct chronological measured intervals"
            )
        events[code] = lo, hi
        last = lo
    return events


def midpoint_interval(row, events):
    lo, hi = bounds(row, "midpoint_low_ns", "midpoint_high_ns", 1)
    first, last = events.get(str(row["first_code"])), events.get(str(row["last_code"]))
    if (
        first is None
        or last is None
        or first[0] > last[0]
        or hi < first[0]
        or lo > last[1]
    ):
        raise ValueError(
            "Exposure midpoint does not correspond to the measured optical code interval"
        )
    return min(lo, first[0]), max(hi, last[1])


def measured_sequence(capture, reference, events, meta, method):
    if UUID(capture["boot_id"]).int == 0 or not capture["capture_id"].strip():
        raise ValueError("Missing recorded boot and capture identity")
    if (reference["boot_id"], reference["capture_id"]) != (
        capture["boot_id"],
        capture["capture_id"],
    ):
        raise ValueError("Reference and camera capture identity differ")
    if (
        capture["clock"] != CLOCK
        or reference["clock"] != CLOCK
        or capture["receipt"] != READ
    ):
        raise ValueError(
            "Both sources must refer to the host monotonic clock and the production read endpoint"
        )
    if (
        camera_fingerprint(capture["camera"]) != camera_fingerprint(meta["camera"])
        or capture["source_calibration_sha256"] != meta["calibration_sha256"]
    ):
        raise ValueError(
            "Camera identity, controls or calibration differ from the donor recording"
        )
    if reference["method"] != method or reference["image_rows"] != [
        0,
        meta["camera"]["height"] - 1,
    ]:
        raise ValueError(
            "Reference must cover the full camera image using the declared timing method"
        )
    reads, independent = capture["rows"], reference["rows"]
    if len(reads) < max(3, math.ceil(meta["camera"]["fps_reported"])) or len(
        reads
    ) != len(independent):
        raise ValueError(
            "Need a contiguous nominal second of distinct read/reference pairs per sequence"
        )
    last_seq = None
    last_read = 0
    last_midpoint = 0
    records = []
    for read, ref in zip(reads, independent, strict=True):
        seq = number(read, "sequence")
        if number(ref, "sequence") != seq or (
            last_seq is not None and seq != last_seq + 1
        ):
            raise ValueError("Missing, duplicated or unpaired camera frame")
        stamp = number(read, "read_end_ns", 1)
        lo, hi = midpoint_interval(ref, events)
        if stamp <= last_read or lo + hi <= last_midpoint:
            raise ValueError("Read or exposure timestamp did not advance")
        error = number(ref, "reference_error_ns") + number(read, "read_clock_error_ns")
        lower, upper = stamp - hi - error, stamp - lo + error
        if lower < 0 or upper > MAX_LAG:
            raise ValueError(
                "A measured exposure could follow read end or exceed the 250 ms range"
            )
        records.append(
            {
                "sequence": seq,
                "read_end_ns": stamp,
                "lag_low_ns": lower,
                "lag_high_ns": upper,
            }
        )
        last_seq, last_read, last_midpoint = seq, stamp, lo + hi
    if last_read - records[0]["read_end_ns"] < 1_000_000_000:
        raise ValueError("Each capture must span at least one actual second")
    return {
        "capture_id": capture["capture_id"],
        "boot_id": str(UUID(capture["boot_id"])),
        "rows": records,
    }


def validate(manifest_path, meta):
    manifest_path = Path(manifest_path).resolve()

    def sibling(info):
        path = (manifest_path.parent / info["file"]).resolve()
        if not path.is_relative_to(manifest_path.parent):
            raise ValueError("Source file is outside the measurement bundle")
        return path.read_bytes()

    return evaluate(manifest_path.read_bytes(), sibling, meta)


def evaluate(raw, load, meta):
    manifest = json.loads(raw)
    method = manifest["method"]
    if manifest["schema"] != "so101-exposure-measurement-v1" or method != OPTICAL:
        raise ValueError(
            "C920 requires an independent optical timecode; UVC start-of-exposure flags are insufficient"
        )
    for field in ("operator", "instrument", "error_budget", "capture_conditions"):
        if not isinstance(manifest.get(field), str) or not manifest[field].strip():
            raise ValueError(f"Missing measurement provenance: {field}")
    evidence = {digest(raw): raw}
    sequences, sources = {}, {}
    for split in ("fit", "control"):
        refs = manifest[split]
        content = {}
        sources[split] = {}
        for role in ("capture", "reference", "source"):
            info = refs[role]
            data = load(info)
            sha = digest(data)
            if not data or sha != info["sha256"] or sha in evidence:
                raise ValueError(f"Missing, changed or reused {split} {role} file")
            evidence[sha], content[role], sources[split][role] = data, data, sha
        reference = json.loads(content["reference"])
        if reference["source_sha256"] != sources[split]["source"]:
            raise ValueError(
                "Decoded timings do not identify the independent raw trace"
            )
        capture = json.loads(content["capture"])
        events = optical_events(content["source"], capture)
        sequences[split] = measured_sequence(capture, reference, events, meta, method)
    fit, control = sequences["fit"], sequences["control"]
    if fit["capture_id"] == control["capture_id"] or (
        fit["boot_id"] == control["boot_id"]
        and control["rows"][0]["read_end_ns"] <= fit["rows"][-1]["read_end_ns"]
    ):
        raise ValueError(
            "Control capture must be independent and subsequent on the same boot"
        )
    lag = round(
        statistics.median((r["lag_low_ns"] + r["lag_high_ns"]) / 2 for r in fit["rows"])
    )
    for sequence in sequences.values():
        for row in sequence["rows"]:
            row["error_bound_ns"] = max(
                abs(row["lag_low_ns"] - lag), abs(row["lag_high_ns"] - lag)
            )
        sequence["max_error_bound_ns"] = max(
            r["error_bound_ns"] for r in sequence["rows"]
        )
    uncertainty = max(s["max_error_bound_ns"] for s in sequences.values())
    if not 0 < uncertainty <= LIMIT:
        raise ValueError(
            f"Worst measured error including instrument bounds is {uncertainty / 1e6:g} ms; required (0, 20] ms"
        )
    report = {
        "schema": "so101-camera-timing-measured-v1",
        "usable": True,
        "method": method,
        "lag_s": lag / 1e9,
        "uncertainty_s": uncertainty / 1e9,
        "camera_sha256": camera_fingerprint(meta["camera"]),
        "source_calibration_sha256": meta["calibration_sha256"],
        "manifest_sha256": digest(raw),
        "sources": sources,
        "sequences": sequences,
        "operator": manifest["operator"],
        "instrument": manifest["instrument"],
        "capture_conditions": manifest["capture_conditions"],
        "error_budget": manifest["error_budget"],
        "scope": "Median fit lag. Error bound is the worst individual fit or held-out residual including supplied exposure/clock bounds for these capture conditions. No population coverage guarantee.",
    }
    return report, evidence


def store_once(path, raw):
    """Publish completely written immutable bytes without replacing existing evidence."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent) as tmp:
        tmp.write(raw)
        tmp.flush()
        os.fsync(tmp.fileno())
        try:
            os.link(tmp.name, path)
        except FileExistsError:
            if path.read_bytes() != raw:
                raise ValueError(f"Existing measurement preserved: {path}") from None


def serialized(report):
    return (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()


def verified_installed(path: Path, meta: dict) -> dict:
    """Recompute an installed receipt from all seven immutable evidence blobs."""
    path = Path(path)
    if path.name != camera_fingerprint(meta["camera"]) + ".json":
        raise ValueError("Timing receipt filename does not identify this camera")
    evidence = (path.parent / "evidence").resolve()

    def blob(info):
        sha = info["sha256"]
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise ValueError("Invalid content address in timing evidence")
        target = evidence / sha
        if target.is_symlink():
            raise ValueError("Timing evidence cannot be redirected")
        raw = target.read_bytes()
        if digest(raw) != sha:
            raise ValueError("Stored timing evidence changed")
        return raw

    try:
        saved = path.read_bytes()
        header = json.loads(saved)
        manifest = blob({"sha256": header["manifest_sha256"]})
        report, _ = evaluate(manifest, blob, meta)
        if serialized(report) != saved:
            raise ValueError(
                "Installed receipt differs from independently recomputed timing"
            )
        return report
    except (OSError, KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"Timing receipt verification failed: {exc}") from exc


def install(report, evidence, directory):
    for sha, raw in evidence.items():
        store_once(directory / "evidence" / sha, raw)
    path = directory / (report["camera_sha256"] + ".json")
    store_once(path, serialized(report))
    return path


def main():
    from explorer4.so101_metric_calibration import load_capture

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--episode", required=True, help="Included physical donor episode ID"
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="Publish a passing receipt and its source evidence",
    )
    args = parser.parse_args()
    try:
        _, meta = load_capture(args.episode)
        report, evidence = validate(args.manifest, meta)
        path = (
            install(report, evidence, DATA / "validation/so101-timing/measured")
            if args.install
            else None
        )
        print(
            json.dumps(
                {k: v for k, v in report.items() if k not in ("sources", "sequences")}
                | {"installed_at": str(path) if path else None},
                indent=2,
            )
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        parser.exit(2, f"Timing measurement rejected: {exc}\n")


if __name__ == "__main__":
    main()
