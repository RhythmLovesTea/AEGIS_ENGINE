"""AEGIS-Marine: DeepLabv3+ Semantic Segmentation Architecture & Compound Loss.

Implements Tier 1 spaceborne SAR slick detection network:
1. DeepLabv3+ architecture with ASPP (rates: 6, 12, 18) and low-level feature decoder.
2. Multi-channel radar input support (VV, VV+VH).
3. Compound loss combining Focal Loss and Lovasz-Hinge Loss for severe class imbalance.
Reference: PRD Section 10 & Technical Specification Section 4.1.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F


# ---------------------------------------------------------------------------
# ASPP (Atrous Spatial Pyramid Pooling) Module
# ---------------------------------------------------------------------------

class _ASPPConv(nn.Module):
    """Atrous Conv block with BatchNorm and ReLU."""

    def __init__(self, in_channels: int, out_channels: int, dilation: int) -> None:
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(
                in_channels,
                out_channels,
                kernel_size=3,
                padding=dilation,
                dilation=dilation,
                bias=False,
            ),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.conv(x)


class _ASPPPooled(nn.Module):
    """Global Average Pooling branch with bilinear upsampling."""

    def __init__(self, in_channels: int, out_channels: int) -> None:
        super().__init__()
        self.conv = nn.Sequential(
            nn.AdaptiveAvgPool2d((1, 1)),
            nn.Conv2d(in_channels, out_channels, kernel_size=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        size = x.shape[-2:]
        pooled = self.conv(x)
        return F.interpolate(pooled, size=size, mode="bilinear", align_corners=False)


class ASPP(nn.Module):
    """Atrous Spatial Pyramid Pooling with atrous rates (6, 12, 18).

    Captures multi-scale contextual features across diverse oil slick extents.
    """

    def __init__(
        self,
        in_channels: int,
        out_channels: int = 256,
        atrous_rates: Tuple[int, int, int] = (6, 12, 18),
    ) -> None:
        super().__init__()
        modules: List[nn.Module] = [
            nn.Sequential(
                nn.Conv2d(in_channels, out_channels, kernel_size=1, bias=False),
                nn.BatchNorm2d(out_channels),
                nn.ReLU(inplace=True),
            )
        ]

        for rate in atrous_rates:
            modules.append(_ASPPConv(in_channels, out_channels, dilation=rate))

        modules.append(_ASPPPooled(in_channels, out_channels))
        self.convs = nn.ModuleList(modules)

        # Projection layer
        self.project = nn.Sequential(
            nn.Conv2d(len(self.convs) * out_channels, out_channels, kernel_size=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Dropout(0.5),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        res = [conv(x) for conv in self.convs]
        res = torch.cat(res, dim=1)
        return self.project(res)


# ---------------------------------------------------------------------------
# Backbone Feature Extractor (ResNet Residual Blocks)
# ---------------------------------------------------------------------------

class _ResidualBlock(nn.Module):
    """Basic 2-layer residual block with optional downsampling."""

    def __init__(self, in_ch: int, out_ch: int, stride: int = 1, dilation: int = 1) -> None:
        super().__init__()
        self.conv1 = nn.Conv2d(
            in_ch,
            out_ch,
            kernel_size=3,
            stride=stride,
            padding=dilation,
            dilation=dilation,
            bias=False,
        )
        self.bn1 = nn.BatchNorm2d(out_ch)
        self.relu = nn.ReLU(inplace=True)
        self.conv2 = nn.Conv2d(
            out_ch,
            out_ch,
            kernel_size=3,
            stride=1,
            padding=dilation,
            dilation=dilation,
            bias=False,
        )
        self.bn2 = nn.BatchNorm2d(out_ch)

        self.downsample: Optional[nn.Sequential] = None
        if stride != 1 or in_ch != out_ch:
            self.downsample = nn.Sequential(
                nn.Conv2d(in_ch, out_ch, kernel_size=1, stride=stride, bias=False),
                nn.BatchNorm2d(out_ch),
            )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        identity = x
        out = self.conv1(x)
        out = self.bn1(out)
        out = self.relu(out)
        out = self.conv2(out)
        out = self.bn2(out)

        if self.downsample is not None:
            identity = self.downsample(x)

        out += identity
        return self.relu(out)


class ResNetBackbone(nn.Module):
    """Multi-stage ResNet feature extractor for SAR imagery."""

    def __init__(self, in_channels: int = 1) -> None:
        super().__init__()
        # Initial stem: 7x7 conv with stride 2 -> 1/2 resolution
        self.stem = nn.Sequential(
            nn.Conv2d(in_channels, 64, kernel_size=7, stride=2, padding=3, bias=False),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(kernel_size=3, stride=2, padding=1),  # -> 1/4 resolution
        )

        # Stage 1 (Low-level features at 1/4 resolution, 64 channels)
        self.layer1 = nn.Sequential(
            _ResidualBlock(64, 64, stride=1),
            _ResidualBlock(64, 64, stride=1),
        )

        # Stage 2 (1/8 resolution, 128 channels)
        self.layer2 = nn.Sequential(
            _ResidualBlock(64, 128, stride=2),
            _ResidualBlock(128, 128, stride=1),
        )

        # Stage 3 (1/16 resolution, 256 channels)
        self.layer3 = nn.Sequential(
            _ResidualBlock(128, 256, stride=2),
            _ResidualBlock(256, 256, stride=1),
        )

        # Stage 4 (High-level features, 1/16 resolution with dilated convs, 512 channels)
        self.layer4 = nn.Sequential(
            _ResidualBlock(256, 512, stride=1, dilation=2),
            _ResidualBlock(512, 512, stride=1, dilation=2),
        )

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """Returns (low_level_features, high_level_features)."""
        x_stem = self.stem(x)
        low_level = self.layer1(x_stem)  # 64 ch, H/4, W/4
        x = self.layer2(low_level)       # 128 ch, H/8, W/8
        x = self.layer3(x)               # 256 ch, H/16, W/16
        high_level = self.layer4(x)      # 512 ch, H/16, W/16
        return low_level, high_level


# ---------------------------------------------------------------------------
# DeepLabv3+ Decoder & Full Model
# ---------------------------------------------------------------------------

class DeepLabV3PlusDecoder(nn.Module):
    """DeepLabv3+ decoder merging ASPP output with low-level spatial features."""

    def __init__(
        self,
        low_level_channels: int = 64,
        aspp_channels: int = 256,
        num_classes: int = 1,
    ) -> None:
        super().__init__()
        # Project low-level features to reduce channel count
        self.project_low = nn.Sequential(
            nn.Conv2d(low_level_channels, 48, kernel_size=1, bias=False),
            nn.BatchNorm2d(48),
            nn.ReLU(inplace=True),
        )

        # Refinement convolution layers after concatenation
        self.refine = nn.Sequential(
            nn.Conv2d(aspp_channels + 48, 256, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(256),
            nn.ReLU(inplace=True),
            nn.Dropout(0.1),
            nn.Conv2d(256, 256, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(256),
            nn.ReLU(inplace=True),
            nn.Dropout(0.1),
            nn.Conv2d(256, num_classes, kernel_size=1),
        )

    def forward(self, high_level_aspp: torch.Tensor, low_level: torch.Tensor) -> torch.Tensor:
        # Upsample ASPP features 4x to match low-level spatial resolution (H/4, W/4)
        aspp_upsampled = F.interpolate(
            high_level_aspp,
            size=low_level.shape[-2:],
            mode="bilinear",
            align_corners=False,
        )
        low_proj = self.project_low(low_level)
        concat = torch.cat([aspp_upsampled, low_proj], dim=1)
        return self.refine(concat)


class DeepLabV3Plus(nn.Module):
    """DeepLabv3+ Semantic Segmentation Network for Spaceborne SAR Oil Spill Detection.

    Reference: PRD Section 10 (DeepLabv3+/U-Net), Architecture Doc Section Tier 1.
    """

    def __init__(
        self,
        in_channels: int = 1,
        num_classes: int = 1,
        atrous_rates: Tuple[int, int, int] = (6, 12, 18),
    ) -> None:
        super().__init__()
        self.backbone = ResNetBackbone(in_channels=in_channels)
        self.aspp = ASPP(in_channels=512, out_channels=256, atrous_rates=atrous_rates)
        self.decoder = DeepLabV3PlusDecoder(
            low_level_channels=64,
            aspp_channels=256,
            num_classes=num_classes,
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        input_size = x.shape[-2:]
        low_level, high_level = self.backbone(x)
        aspp_out = self.aspp(high_level)
        decoded = self.decoder(aspp_out, low_level)
        # Upsample 4x to restore exact input spatial dimensions
        return F.interpolate(decoded, size=input_size, mode="bilinear", align_corners=False)


# ---------------------------------------------------------------------------
# Compound Loss: Focal Loss + Lovasz-Hinge Loss
# ---------------------------------------------------------------------------

class BinaryFocalLoss(nn.Module):
    """Binary Focal Loss addressing severe class imbalance (spill << ocean clutter).

    L_focal = -alpha * (1 - p_t)^gamma * log(p_t)
    """

    def __init__(self, alpha: float = 0.25, gamma: float = 2.0) -> None:
        super().__init__()
        self.alpha = alpha
        self.gamma = gamma

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        bce_loss = F.binary_cross_entropy_with_logits(logits, targets, reduction="none")
        probs = torch.sigmoid(logits)
        p_t = probs * targets + (1.0 - probs) * (1.0 - targets)
        alpha_factor = self.alpha * targets + (1.0 - self.alpha) * (1.0 - targets)
        modulating_factor = torch.pow(1.0 - p_t, self.gamma)
        loss = alpha_factor * modulating_factor * bce_loss
        return loss.mean()


def _lovasz_grad(gt_sorted: torch.Tensor) -> torch.Tensor:
    """Compute gradient of the Lovasz extension w.r.t sorted errors."""
    p = len(gt_sorted)
    gts = gt_sorted.sum()
    intersection = gts - gt_sorted.float().cumsum(0)
    union = gts + (1 - gt_sorted).float().cumsum(0)
    jaccard = 1.0 - intersection / (union + 1e-7)
    if p > 1:
        jaccard[1:p] = jaccard[1:p] - jaccard[0:-1]
    return jaccard


class BinaryLovaszLoss(nn.Module):
    """Lovasz-Hinge Loss directly optimizing the Jaccard index / mIoU.

    Reference: PRD Section 10 & 14 (Target mIoU >= 82.5%).
    """

    def __init__(self, per_image: bool = True) -> None:
        super().__init__()
        self.per_image = per_image

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        if self.per_image:
            losses = []
            for logit, target in zip(logits, targets):
                losses.append(self._lovasz_hinge_flat(logit.view(-1), target.view(-1)))
            return torch.stack(losses).mean()
        return self._lovasz_hinge_flat(logits.view(-1), targets.view(-1))

    def _lovasz_hinge_flat(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        if len(targets) == 0:
            return logits.sum() * 0.0

        signs = 2.0 * targets.float() - 1.0
        errors = 1.0 - logits * signs
        errors_sorted, perm = torch.sort(errors, dim=0, descending=True)
        perm = perm.data
        gt_sorted = targets[perm]
        grad = _lovasz_grad(gt_sorted)
        loss = torch.dot(F.relu(errors_sorted), grad)
        return loss


class CompoundLoss(nn.Module):
    """Compound loss combining Focal Loss and Lovasz-Hinge Loss.

    Formula: L_total = lambda_1 * L_Focal + lambda_2 * L_Lovasz
    """

    def __init__(
        self,
        lambda_focal: float = 1.0,
        lambda_lovasz: float = 1.0,
        focal_alpha: float = 0.25,
        focal_gamma: float = 2.0,
    ) -> None:
        super().__init__()
        self.lambda_focal = lambda_focal
        self.lambda_lovasz = lambda_lovasz
        self.focal_loss = BinaryFocalLoss(alpha=focal_alpha, gamma=focal_gamma)
        self.lovasz_loss = BinaryLovaszLoss(per_image=True)

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> Dict[str, torch.Tensor]:
        loss_focal = self.focal_loss(logits, targets)
        loss_lovasz = self.lovasz_loss(logits, targets)
        loss_total = self.lambda_focal * loss_focal + self.lambda_lovasz * loss_lovasz
        return {
            "total_loss": loss_total,
            "focal_loss": loss_focal,
            "lovasz_loss": loss_lovasz,
        }
