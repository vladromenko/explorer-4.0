import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts import so101_timing_import as timing


class TimingMeasurement(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.meta = {
            "camera": {
                "device": "test-camera",
                "height": 720,
                "fps_reported": 30,
                "controls_readback_before": {"AUTO_WB": 1, "WB_TEMPERATURE": 4100},
            },
            "calibration_sha256": "a" * 64,
        }
        self.boot = "fc5e43b9-d7c5-4384-940d-668f03ee44a2"

    def file(self, name, value):
        data = json.dumps(value).encode()
        (self.root / name).write_bytes(data)
        return {"file": name, "sha256": hashlib.sha256(data).hexdigest()}

    def bundle(self, method="optical_midpoint_interval", change=lambda *args: None):
        info = {
            "schema": "so101-exposure-measurement-v1",
            "method": method,
            "instrument": "test fixture",
            "operator": "test-only",
            "error_budget": "known fixture bounds",
            "capture_conditions": "isolated data without camera access",
        }
        for i, split in enumerate(("fit", "control")):
            base = (i + 1) * 10**10
            cap, ref = [
                {
                    "capture_id": split,
                    "boot_id": self.boot,
                    "clock": timing.CLOCK,
                    "rows": [],
                }
                for _ in range(2)
            ]
            cap.update(
                camera=json.loads(json.dumps(self.meta["camera"])),
                source_calibration_sha256=self.meta["calibration_sha256"],
                receipt=timing.READ,
            )
            trace = {
                "schema": "measured-optical-timecode-v1",
                "capture_id": split,
                "boot_id": self.boot,
                "clock": timing.CLOCK,
                "events": [],
            }
            ref.update(
                method=method,
                image_rows=[0, 719],
                buffer_type="V4L2_BUF_TYPE_VIDEO_CAPTURE",
            )
            for n in range(32):
                read = base + n * 33_333_333
                mid = read - (50_000_000 if split == "fit" else 54_000_000)
                cap["rows"].append(
                    {"sequence": n, "read_end_ns": read, "read_clock_error_ns": 500_000}
                )
                row = {"sequence": n, "reference_error_ns": 500_000}
                row.update(
                    midpoint_low_ns=mid - 2_000_000,
                    midpoint_high_ns=mid + 2_000_000,
                    first_code=str(n),
                    last_code=str(n),
                )
                trace["events"].append(
                    {
                        "code": str(n),
                        "earliest_ns": mid - 2_000_000,
                        "latest_ns": mid + 2_000_000,
                    }
                )
                ref["rows"].append(row)
            raw = self.file(split + "-raw.json", trace)
            ref["source_sha256"] = raw["sha256"]
            change(split, cap, ref)
            info[split] = {
                "capture": self.file(split + "-cap.json", cap),
                "reference": self.file(split + "-ref.json", ref),
                "source": raw,
            }
        self.file("measurement.json", info)
        return self.root / "measurement.json"

    def test_signed_median_and_worst_heldout_error_include_independent_bounds(self):
        report, evidence = timing.validate(self.bundle(), self.meta)
        self.assertTrue(report["usable"])
        self.assertEqual(report["lag_s"], 0.05)
        self.assertEqual(report["uncertainty_s"], 0.007)
        self.assertEqual(report["sequences"]["fit"]["max_error_bound_ns"], 3_000_000)
        self.assertEqual(len(evidence), 7)

    def test_c920_driver_soe_flag_cannot_replace_an_optical_reference(self):
        with self.assertRaisesRegex(ValueError, "UVC"):
            timing.validate(
                self.bundle(
                    "v4l2_monotonic_soe",
                    lambda _, c, r: [
                        row.update(buffer_flags=0x12000) for row in r["rows"]
                    ],
                ),
                self.meta,
            )

    def test_independent_light_clock_width_is_used_even_if_decoded_bounds_are_too_tight(
        self,
    ):
        def narrow(split, c, r):
            for row in r["rows"]:
                mid = (row["midpoint_low_ns"] + row["midpoint_high_ns"]) // 2
                row.update(midpoint_low_ns=mid, midpoint_high_ns=mid)

        report, _ = timing.validate(self.bundle(change=narrow), self.meta)
        self.assertEqual(report["uncertainty_s"], 0.007)

    def test_worst_control_outlier_cannot_be_hidden_by_median(self):
        def change(split, cap, ref):
            if split == "control":
                ref["rows"][3]["midpoint_low_ns"] -= 18_000_000

        with self.assertRaisesRegex(ValueError, "25 ms"):
            timing.validate(self.bundle(change=change), self.meta)

    def test_preserves_diagnostic_and_previous_canonical_positive(self):
        report, evidence = timing.validate(self.bundle(), self.meta)
        target = self.root / "validation/so101-timing"
        target.mkdir(parents=True)
        diagnostic = target / (report["camera_sha256"] + ".json")
        diagnostic.write_text('{"usable":false}')
        installed = timing.install(report, evidence, target / "measured")
        self.assertEqual(
            timing.install(report, evidence, target / "measured"), installed
        )
        with self.assertRaisesRegex(ValueError, "preserved"):
            timing.install({**report, "lag_s": 0.1}, evidence, target / "measured")
        self.assertEqual(json.loads(installed.read_bytes()), report)
        self.assertEqual(json.loads(diagnostic.read_bytes()), {"usable": False})

    def test_installed_receipt_recomputed_from_blobs_without_original_source_files(
        self,
    ):
        path = self.bundle()
        report, evidence = timing.validate(path, self.meta)
        dest = self.root / "measured"
        receipt = timing.install(report, evidence, dest)
        for source in self.root.glob("*.json"):
            source.unlink()
        self.assertEqual(timing.verified_installed(receipt, self.meta), report)
        original = receipt.read_bytes()
        receipt.write_bytes(timing.serialized({**report, "lag_s": 0.123}))
        with self.assertRaisesRegex(ValueError, "recomputed"):
            timing.verified_installed(receipt, self.meta)
        receipt.write_bytes(original)
        (dest / "evidence" / report["sources"]["control"]["source"]).write_text(
            "modified"
        )
        with self.assertRaisesRegex(ValueError, "evidence changed"):
            timing.verified_installed(receipt, self.meta)
        receipt.write_text('{"usable": true, "lag_s": 0.05, "uncertainty_s": 0.001}')
        with self.assertRaisesRegex(ValueError, "manifest_sha256"):
            timing.verified_installed(receipt, self.meta)

    def test_rejects_eof_different_identity_overlap_missing_frames_and_unbound_evidence(
        self,
    ):
        mutations = [
            lambda c, r: r["rows"][0].update(first_code="unknown"),
            lambda c, r: r["rows"][0].update(first_code="2", last_code="1"),
            lambda c, r: r.update(image_rows=[200, 250]),
            lambda c, r: c["camera"]["controls_readback_before"].update(
                WB_TEMPERATURE=4049
            ),
            lambda c, r: c.update(source_calibration_sha256="b" * 64),
            lambda c, r: c.update(receipt="at_vidioc_dqbuf"),
            lambda c, r: r["rows"].pop(3),
            lambda c, r: r["rows"][3].update(sequence=5),
            lambda c, r: r.update(clock="CLOCK_REALTIME"),
            lambda c, r: c["rows"][0].update(read_end_ns=10_000_000_000),
            lambda c, r: r.update(source_sha256="c" * 64),
            lambda c, r: (c.update(capture_id="fit"), r.update(capture_id="fit")),
        ]
        for i, mutate in enumerate(mutations):
            with self.subTest(i=i):

                def change(split, cap, ref):
                    if split == "control":
                        mutate(cap, ref)

                with self.assertRaises(ValueError):
                    timing.validate(self.bundle(change=change), self.meta)
        path = self.bundle()
        (self.root / "control-raw.json").write_text("replacement")
        with self.assertRaisesRegex(ValueError, "changed"):
            timing.validate(path, self.meta)


if __name__ == "__main__":
    unittest.main()
