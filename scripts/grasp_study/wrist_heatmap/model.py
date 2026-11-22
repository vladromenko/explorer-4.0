"""Single-cube keypoint heatmap and RGB-conditioned correction to a fixed planar camera map."""

import torch
from torch import nn
from torch.nn import functional as F
from torchvision.models import ResNet18_Weights, resnet18


class WristKeypoint(nn.Module):
    def __init__(self, homography, pretrained=False):
        super().__init__()
        trunk = resnet18(weights=ResNet18_Weights.IMAGENET1K_V1 if pretrained else None)
        self.stem = nn.Sequential(trunk.conv1, trunk.bn1, trunk.relu, trunk.maxpool, trunk.layer1)
        self.context = trunk.layer2
        self.fine = nn.Conv2d(64, 16, 1)
        self.coarse = nn.Conv2d(128, 32, 1)
        self.heatmap = nn.Sequential(nn.Conv2d(48, 32, 3, padding=1), nn.ReLU(), nn.Conv2d(32, 1, 1))
        self.calibration_offset = nn.Sequential(
            nn.Conv2d(128, 16, 1),
            nn.ReLU(),
            nn.AdaptiveAvgPool2d((4, 5)),
            nn.Flatten(),
            nn.Linear(320, 32),
            nn.ReLU(),
            nn.Linear(32, 2),
        )
        nn.init.zeros_(self.calibration_offset[-1].weight)
        nn.init.zeros_(self.calibration_offset[-1].bias)
        yy, xx = torch.meshgrid(torch.arange(30), torch.arange(40), indexing="ij")
        self.register_buffer("grid", torch.stack([xx, yy], dim=-1).reshape(-1, 2).float() * 4 + 1.5)
        self.register_buffer("homography", torch.as_tensor(homography, dtype=torch.float32))
        self.register_buffer("mu", torch.tensor([0.485, 0.456, 0.406]).reshape(1, 3, 1, 1))
        self.register_buffer("sigma", torch.tensor([0.229, 0.224, 0.225]).reshape(1, 3, 1, 1))

    def project(self, uv):
        xyw = torch.cat([uv, torch.ones_like(uv[:, :1])], dim=1) @ self.homography.T
        return xyw[:, :2] / xyw[:, 2:]

    def forward(self, rgb):
        x = rgb.permute(0, 3, 1, 2).float() / 255.0
        if self.training:
            # Preserve the cube position while varying illumination and colour saturation.
            shape = (len(x), 1, 1, 1)
            sat = torch.rand(shape, device=x.device) * 1.1
            x = x.mean(dim=1, keepdim=True) + sat * (x - x.mean(dim=1, keepdim=True))
            x = (x * (0.8 + 0.4 * torch.rand(shape, device=x.device))).clamp(0, 1)
        low = self.stem((x - self.mu) / self.sigma)
        deep = self.context(low)
        up = F.interpolate(self.coarse(deep), size=low.shape[-2:], mode="bilinear", align_corners=False)
        logits = self.heatmap(torch.cat([self.fine(low), up], dim=1)).flatten(1)
        uv = logits.softmax(1) @ self.grid
        offset = self.calibration_offset(deep)
        return self.project(uv) + 0.01 * offset, uv, logits, offset

    def loss(self, rgb, target_uv, target_xy):
        _, _, logits, offset = self(rgb)
        distance2 = (target_uv[:, None] - self.grid[None]).square().sum(2)
        reference = (-distance2 / (2 * 4.0**2)).softmax(dim=1)
        image_loss = -(reference * logits.log_softmax(1)).sum(1).mean()
        residual = (target_xy - self.project(target_uv)) / 0.01
        return image_loss + F.smooth_l1_loss(offset, residual, beta=0.2)


class WristCubeLocator:
    """Read-only RGB to base XY (metres) and image centre (160x120 pixels).

    Input is one uint8 RGB frame at 640x480 or its area-resized 160x120 version,
    at the ROSMASTER recorded-start look pose. Loads one frozen fit receipt and
    verifies its checkpoint. It opens no camera, sensor or control connection.
    """

    def __init__(self, directory, device="cpu"):
        import json
        from pathlib import Path
        from explorer4.conditioned_grasp import file_hash

        directory = Path(directory)
        weights = directory / "heatmap.pt"
        self.fit = json.loads((directory / "fit.json").read_text())
        if (
            file_hash(weights) != self.fit["weights_sha256"]
            or file_hash(directory / "protocol.json") != self.fit["protocol_sha256"]
        ):
            raise ValueError("Unverified wrist localization weights or protocol")
        self.device = torch.device(device)
        self.network = WristKeypoint(torch.eye(3)).to(self.device)
        self.network.load_state_dict(torch.load(weights, weights_only=True, map_location=self.device))
        self.network.eval()

    @torch.inference_mode()
    def locate(self, rgb):
        import cv2
        import numpy as np

        rgb = np.asarray(rgb)
        if rgb.dtype != np.uint8 or rgb.shape not in {(480, 640, 3), (120, 160, 3)}:
            raise ValueError("Expected 640x480 or 160x120 uint8 RGB in the calibrated wrist view")
        image = cv2.resize(rgb, (160, 120), interpolation=cv2.INTER_AREA)
        xy, uv, _, _ = self.network(torch.from_numpy(image.copy())[None].to(self.device))
        return {"xy_m": xy[0].cpu().tolist(), "uv_160x120": uv[0].cpu().tolist()}
