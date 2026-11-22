"""ROSMASTER grasp planners. Inputs are metric target XY from the calibrated look camera.

The two LeRobot policies output eight trajectory coefficients. The decoder fitted
to demonstration commands returns 20 Hz native servo targets. This module never
opens a hardware connection.
"""

import hashlib
from pathlib import Path

import numpy as np

RANK = 8
VISION_SHA256 = "a2967027c4a87e7d91f819aee9a15d581a2d80630ee80d9b53ea145bec4d08d8"
MOTOR_SHA256 = "3bd820bbea2bdd3cf320dc8f55412efd25c7a6a379a0971d95e2417cbd46f55c"
PHYSICS_SHA256 = "0e44d9f93c8dd4b9a6452e009097b205209f509ebe0653dc78a339783e5925dc"
PROFILE = "rosmaster_floor_pick_recorded_start_sim"
LOOK_COMMAND = [90.0, 57.0, 24.0, 0.0, 75.0, 30.0]
LOOK_STEPS = 20
SLEW_DEGREES_PER_SECOND = np.array([45.0, 45.0, 45.0, 45.0, 45.0, 120.0])


def file_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_localizer(path):
    import torch
    from torch import nn
    from torchvision.models import resnet18

    if file_hash(path) != VISION_SHA256:
        raise ValueError("Unexpected RGB localization checkpoint")
    network = resnet18(weights=None)
    estimator = nn.Sequential(
        network.conv1,
        network.bn1,
        network.relu,
        network.maxpool,
        network.layer1,
        network.layer2,
        nn.Conv2d(128, 16, 1),
        nn.ReLU(),
        nn.AdaptiveAvgPool2d((8, 10)),
        nn.Flatten(),
        nn.Linear(1280, 128),
        nn.ReLU(),
        nn.Linear(128, 2),
    )
    estimator.load_state_dict(torch.load(path, map_location="cpu", weights_only=True))
    return estimator.eval()


def locate_cube(estimator, rgb):
    """Predict base-frame XY (metres) from an RGB image at the study's look pose."""
    import cv2
    import torch

    rgb = np.asarray(rgb)
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("Expected RGB uint8 image")
    image = cv2.resize(rgb, (160, 120), interpolation=cv2.INTER_AREA)
    pixels = torch.from_numpy(image.copy()).permute(2, 0, 1)[None].float().div_(255)
    mean = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
    scale = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)
    with torch.inference_mode():
        xy = estimator((pixels - mean) / scale)[0].numpy()
    return xy * 0.05 + np.array([0.21, 0.0], np.float32)


def fit_decoder(xy, actions):
    flat = actions.reshape(len(actions), -1)
    mean = flat.mean(axis=0)
    _, _, basis = np.linalg.svd(flat - mean, full_matrices=False)
    basis = basis[:RANK]
    scores = (flat - mean) @ basis.T
    amplitude = np.abs(scores).max(axis=0).clip(min=1e-8)
    return dict(
        mean=mean,
        basis=basis,
        amplitude=amplitude,
        xy_center=xy.mean(axis=0),
        xy_scale=np.abs(xy - xy.mean(axis=0)).max(axis=0).clip(min=1e-8),
        shape=np.asarray(actions.shape[1:]),
    ), scores / amplitude


def lerobot_inputs(xy, architecture):
    # LeRobot state-only ACT and Diffusion require separate state and environment
    # features. Both scalars below come from the same measured RGB position.
    state, environment = xy[:, :1], xy[:, 1:]
    if architecture == "diffusion":
        state, environment = state[:, None], environment[:, None]
    return {"observation.state": state, "observation.environment_state": environment}


def create_policy(architecture, device):
    from lerobot.configs.types import FeatureType, PolicyFeature
    from lerobot.policies.act.configuration_act import ACTConfig
    from lerobot.policies.act.modeling_act import ACTPolicy
    from lerobot.policies.diffusion.configuration_diffusion import DiffusionConfig
    from lerobot.policies.diffusion.modeling_diffusion import DiffusionPolicy

    features = dict(
        device=device,
        input_features={
            "observation.state": PolicyFeature(type=FeatureType.STATE, shape=(1,)),
            "observation.environment_state": PolicyFeature(type=FeatureType.ENV, shape=(1,)),
        },
        output_features={"action": PolicyFeature(type=FeatureType.ACTION, shape=(1,))},
        push_to_hub=False,
    )
    if architecture == "act":
        config = ACTConfig(
            **features,
            chunk_size=RANK,
            n_action_steps=RANK,
            dim_model=64,
            n_heads=4,
            dim_feedforward=128,
            n_encoder_layers=2,
            n_decoder_layers=1,
            use_vae=False,
            dropout=0.0,
        )
        return ACTPolicy(config).to(device)
    if architecture == "diffusion":
        config = DiffusionConfig(
            **features,
            horizon=RANK,
            n_obs_steps=1,
            n_action_steps=RANK,
            down_dims=(32, 64),
            n_groups=4,
            kernel_size=3,
            diffusion_step_embed_dim=32,
            noise_scheduler_type="DDIM",
            num_train_timesteps=100,
            num_inference_steps=12,
            prediction_type="sample",
            drop_n_last_frames=0,
        )
        return DiffusionPolicy(config).to(device)
    raise ValueError(f"Unsupported motor policy {architecture}")


class TrajectoryPolicy:
    """Compile one six-servo trajectory from a calibrated camera position."""

    def __init__(self, bundle, architecture, device="cpu"):
        from lerobot.policies.factory import get_policy_class

        self.architecture = architecture
        self.device = device
        root = Path(bundle)
        with np.load(root / "decoder.npz", allow_pickle=False) as decoder:
            self.decoder = dict(decoder)
        self.policy = get_policy_class(architecture).from_pretrained(root / architecture).to(device).eval()

    def trajectory(self, xy):
        import torch

        decoder = self.decoder
        if np.asarray(xy).shape != (2,) or not np.isfinite(xy).all():
            raise ValueError("Expected finite metric XY")
        conditioned = (np.asarray(xy) - decoder["xy_center"]) / decoder["xy_scale"]
        tensor = torch.tensor(conditioned, dtype=torch.float32, device=self.device)[None]
        batch = lerobot_inputs(tensor, self.architecture)
        with torch.inference_mode():
            if self.architecture == "diffusion":
                # Fixed starting noise and deterministic DDIM for paired comparisons.
                generator = torch.Generator(device="cpu").manual_seed(1000)
                noise = torch.randn((1, RANK, 1), generator=generator).to(self.device)
                result = self.policy.predict_action_chunk(batch, noise=noise)
            else:
                result = self.policy.predict_action_chunk(batch)
        coeff = result[0, :, 0].cpu().numpy() * decoder["amplitude"]
        return (decoder["mean"] + coeff @ decoder["basis"]).reshape(tuple(decoder["shape"]))
