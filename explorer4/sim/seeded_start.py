"""Reproduce RGB, native pose and sampled dynamics of a recorded-start development scene."""

import hashlib
import json
import tempfile

import cv2
import numpy as np

from explorer4.paths import DATA

# EGL can round a single colour channel by one level on an otherwise identical frame.
# Both limits apply. At 640 x 480 the count bound allows nine rounded channel samples.
MAX_CHANNEL_LEVEL_ERROR = 1
MAX_DIFFERENT_FRACTION = 0.00001


def fingerprint(seed, env, obs):
    sampled = json.dumps([env.episode_parameters, env.lag_s], sort_keys=True, allow_nan=False).encode()
    return {
        "seed": seed,
        "initial_qpos_sha256": hashlib.sha256(np.asarray(env.data.qpos, dtype="<f8").tobytes()).hexdigest(),
        "initial_rgb_sha256": hashlib.sha256(obs["rgb"].tobytes()).hexdigest(),
        "initial_parameters_sha256": hashlib.sha256(sampled).hexdigest(),
    }


def compare_rgb(image, reference):
    if image.shape != reference.shape or image.dtype != np.uint8 or reference.dtype != np.uint8:
        raise ValueError("Development camera type or resolution changed")
    error = cv2.absdiff(image, reference)
    count = int(np.count_nonzero(error))
    maximum = int(error.max())
    if maximum > MAX_CHANNEL_LEVEL_ERROR or count > image.size * MAX_DIFFERENT_FRACTION:
        raise ValueError(f"Development RGB changed ({count} channel values, maximum error {maximum}/255)")
    return maximum, count


def save_reference(image):
    ok, encoded = cv2.imencode(".png", cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
    if not ok:
        raise ValueError("Could not save development RGB frame")
    data = encoded.tobytes()
    digest = hashlib.sha256(data).hexdigest()
    directory = DATA / "development-starts"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (digest + ".png")
    if not target.is_file():
        with tempfile.NamedTemporaryFile(dir=directory, delete=False) as tmp:
            tmp.write(data)
        from pathlib import Path

        Path(tmp.name).replace(target)
    if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
        raise ValueError("Saved reference image changed")
    return digest


def checked_fingerprint(seed, env, obs, expected):
    observed = fingerprint(seed, env, obs)
    for key in ("seed", "initial_qpos_sha256", "initial_parameters_sha256"):
        if observed[key] != expected[key]:
            raise ValueError(f"Development {key} changed at seed {seed}")
    rgb = obs["rgb"]
    maximum = count = 0
    if observed["initial_rgb_sha256"] != expected["initial_rgb_sha256"]:
        digest = expected["reference_png_sha256"]
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("Invalid reference image fingerprint")
        data = (DATA / "development-starts" / (digest + ".png")).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError("Saved reference image changed")
        reference = cv2.cvtColor(
            cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB
        )
        if hashlib.sha256(reference.tobytes()).hexdigest() != expected["initial_rgb_sha256"]:
            raise ValueError("Reference image and expected RGB differ")
        maximum, count = compare_rgb(rgb, reference)
    return {
        **observed,
        "reference_png_sha256": expected["reference_png_sha256"],
        "reference_rgb_sha256": expected["initial_rgb_sha256"],
        "rgb_max_level_error": maximum,
        "rgb_different_channels": count,
        "rgb_channels": int(rgb.size),
    }


def probe():
    from explorer4.floor_development_gate import PROFILE, SEEDS

    from .factory import make

    reference = {}
    for repetition, order in enumerate((SEEDS, tuple(reversed(SEEDS)))):
        env = make(PROFILE, images=True)
        try:
            for seed in order:
                obs, _ = env.reset(seed=seed)
                if repetition == 0:
                    reference[seed] = {
                        **fingerprint(seed, env, obs),
                        "reference_png_sha256": save_reference(obs["rgb"]),
                    }
                else:
                    checked_fingerprint(seed, env, obs, reference[seed])
        finally:
            env.close()
    return {"xml_sha256": env.manifest["xml_sha256"], "rows": [reference[s] for s in SEEDS]}


if __name__ == "__main__":
    print(json.dumps(probe(), allow_nan=False))
