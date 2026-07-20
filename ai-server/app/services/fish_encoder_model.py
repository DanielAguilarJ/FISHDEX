"""
FishDex AI Server - FishEncoder Model Architecture
====================================================
Arquitectura completa del modelo FishEncoder basada en ConvNeXt small
con DeformConv2d, GeM pooling, AdaCos y fusión de alta resolución.

Extraída de testing_new_support__topN_sim.py con cambios de producción:
- pretrained=False  → no descarga pesos de internet en Docker/producción
- Loader con limpieza de prefijos module./model. de checkpoints DDP
- Logging detallado de cuántas keys se cargaron (detecta carga silenciosa mala)
- num_classes inferido automáticamente del checkpoint

Uso:
    from app.services.fish_encoder_model import load_model_for_infer, build_eval_transform
"""

from __future__ import annotations

import logging
import math
import os
from pathlib import Path
from typing import Optional

import timm
import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision import transforms
from torchvision.ops import DeformConv2d

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

def build_eval_transform(img_size: int = 128) -> transforms.Compose:
    """Standard ImageNet-normalised eval transform."""
    return transforms.Compose(
        [
            transforms.Resize((img_size, img_size)),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=(0.485, 0.456, 0.406),
                std=(0.229, 0.224, 0.225),
            ),
        ]
    )


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------

class MixStyle(nn.Module):
    """MixStyle domain augmentation (no-op at eval time)."""

    def __init__(self, p: float = 0.5, alpha: float = 0.3, eps: float = 1e-6):
        super().__init__()
        self.p = float(p)
        self.alpha = float(alpha)
        self.eps = float(eps)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if (not self.training) or torch.rand(1).item() > self.p:
            return x

        batch_size = x.size(0)
        mu = x.mean(dim=(2, 3), keepdim=True)
        var = x.var(dim=(2, 3), keepdim=True, unbiased=False)
        sigma = torch.sqrt(var + self.eps)
        x_normalized = (x - mu) / sigma

        permutation = torch.randperm(batch_size, device=x.device)
        lam = (
            torch.distributions.Beta(self.alpha, self.alpha)
            .sample((batch_size, 1, 1, 1))
            .to(device=x.device, dtype=x.dtype)
        )

        mixed_mu = lam * mu + (1.0 - lam) * mu[permutation]
        mixed_sigma = lam * sigma + (1.0 - lam) * sigma[permutation]
        return x_normalized * mixed_sigma + mixed_mu


class GeM(nn.Module):
    """Generalized Mean Pooling with per-channel learnable exponents."""

    def __init__(self, in_dim: int, p: float = 3.0, eps: float = 1e-6):
        super().__init__()
        self.p = nn.Parameter(torch.ones(in_dim) * p)
        self.eps = float(eps)
        self.in_dim = int(in_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        p_vector = self.p.clamp(1.0, 6.0).view(1, self.in_dim, 1, 1)
        x = x.clamp(min=self.eps).pow(p_vector)
        x = F.avg_pool2d(x, (x.size(-2), x.size(-1)))
        return x.pow(1.0 / p_vector)


class AdaCos(nn.Module):
    """Adaptive cosine softmax classifier head."""

    def __init__(self, in_dim: int, n_classes: int, m: float = 0.2, init_s: float = 30.0):
        super().__init__()
        self.weight = nn.Parameter(torch.empty(n_classes, in_dim))
        nn.init.xavier_normal_(self.weight)
        self.s = float(init_s)
        self.m = float(m)

    def forward(self, x: torch.Tensor, labels: Optional[torch.Tensor] = None) -> torch.Tensor:
        x = F.normalize(x, dim=1)
        weight = F.normalize(self.weight, dim=1)
        logits = x @ weight.t()

        if labels is not None:
            one_hot = torch.zeros_like(logits)
            one_hot.scatter_(1, labels.view(-1, 1), 1.0)
            logits = logits - one_hot * self.m

            with torch.no_grad():
                batch_size = x.size(0)
                theta_median = torch.median(
                    torch.acos(logits.clamp(-1.0 + 1e-7, 1.0 - 1e-7))
                ).item()
                self.s = math.log(max(batch_size - 1, 2)) / math.cos(
                    min(math.pi / 4.0, theta_median)
                )

        return self.s * logits


class DeformRefine(nn.Module):
    """Deformable convolution refinement block."""

    def __init__(
        self,
        in_ch: int,
        out_ch: int,
        mid_ch: Optional[int] = None,
        k: int = 3,
        groups: int = 1,
        dilation: int = 1,
    ):
        super().__init__()
        padding = (k // 2) * dilation
        mid_ch = mid_ch or max(out_ch // 2, 32)

        self.pre = nn.Sequential(
            nn.Conv2d(in_ch, mid_ch, kernel_size=1, bias=False),
            nn.BatchNorm2d(mid_ch),
            nn.SiLU(inplace=True),
        )
        self.offset = nn.Conv2d(
            mid_ch, 2 * k * k * groups, kernel_size=k, padding=padding, dilation=dilation
        )
        self.mask = nn.Conv2d(
            mid_ch, k * k * groups, kernel_size=k, padding=padding, dilation=dilation
        )

        nn.init.constant_(self.offset.weight, 0.0)
        if self.offset.bias is not None:
            nn.init.constant_(self.offset.bias, 0.0)
        nn.init.constant_(self.mask.weight, 0.0)
        if self.mask.bias is not None:
            nn.init.constant_(self.mask.bias, -2.0)

        self.dcn = DeformConv2d(
            in_channels=mid_ch,
            out_channels=out_ch,
            kernel_size=k,
            padding=padding,
            dilation=dilation,
            groups=groups,
            bias=False,
        )
        self.post = nn.Sequential(nn.BatchNorm2d(out_ch), nn.SiLU(inplace=True))
        self.proj = (
            nn.Conv2d(in_ch, out_ch, kernel_size=1, bias=False)
            if in_ch != out_ch
            else nn.Identity()
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        z = self.pre(x)
        offset = self.offset(z)
        mask = torch.sigmoid(self.mask(z))
        y = self.dcn(z, offset, mask)
        y = self.post(y)
        return y + self.proj(x)


class AddCoords(nn.Module):
    """Append normalised (x, y [, r]) coordinate channels."""

    def __init__(self, with_r: bool = True):
        super().__init__()
        self.with_r = bool(with_r)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        batch_size, _, height, width = x.shape
        yy = torch.linspace(-1.0, 1.0, steps=height, device=x.device, dtype=x.dtype).view(
            1, 1, height, 1
        ).expand(batch_size, 1, height, width)
        xx = torch.linspace(-1.0, 1.0, steps=width, device=x.device, dtype=x.dtype).view(
            1, 1, 1, width
        ).expand(batch_size, 1, height, width)

        if self.with_r:
            radius = torch.sqrt(torch.clamp(xx.square() + yy.square(), min=0.0))
            return torch.cat([x, xx, yy, radius], dim=1)
        return torch.cat([x, xx, yy], dim=1)


class CoordConv2d(nn.Module):
    """Conv2d that receives extra coordinate channels via AddCoords."""

    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        kernel_size: int = 3,
        stride: int = 1,
        padding: Optional[int] = None,
        dilation: int = 1,
        groups: int = 1,
        bias: bool = False,
        with_r: bool = True,
    ):
        super().__init__()
        if padding is None:
            padding = (kernel_size // 2) * dilation
        extra_channels = 2 + int(with_r)
        self.addcoords = AddCoords(with_r=with_r)
        self.conv = nn.Conv2d(
            in_channels + extra_channels,
            out_channels,
            kernel_size=kernel_size,
            stride=stride,
            padding=padding,
            dilation=dilation,
            groups=groups,
            bias=bias,
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.conv(self.addcoords(x))


class GlobalContext(nn.Module):
    """Lightweight global context squeeze-excitation."""

    def __init__(self, channels: int, reduction: int = 4):
        super().__init__()
        hidden = max(1, channels // reduction)
        self.fc1 = nn.Conv2d(channels, hidden, 1, bias=False)
        self.act = nn.SiLU(inplace=True)
        self.fc2 = nn.Conv2d(hidden, channels, 1, bias=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        context = x.mean(dim=(2, 3), keepdim=True)
        return x * torch.sigmoid(self.fc2(self.act(self.fc1(context))))


class HighResFusion(nn.Module):
    """Fuse a high-resolution feature map into a target-stride map."""

    def __init__(
        self,
        ch_high: int,
        ch_tgt: int,
        out_ch: int,
        mixstyle: Optional[nn.Module] = None,
        with_r: bool = True,
    ):
        super().__init__()
        self.align = nn.Conv2d(ch_high, ch_high, kernel_size=1, bias=False)
        self.bn_align = nn.BatchNorm2d(ch_high)
        self.cc_high = CoordConv2d(ch_high, ch_high, kernel_size=3, bias=False, with_r=with_r)
        self.bn_cc = nn.BatchNorm2d(ch_high)
        self.deform_refine_high = DeformRefine(ch_high, ch_high, k=3, groups=2, dilation=1)
        self.ms_high = mixstyle if mixstyle is not None else MixStyle()
        self.down = nn.Sequential(
            nn.Conv2d(ch_high, ch_high, 3, stride=2, padding=1, groups=ch_high, bias=False),
            nn.BatchNorm2d(ch_high),
            nn.SiLU(inplace=True),
            nn.Conv2d(ch_high, ch_high, 1, bias=False),
            nn.BatchNorm2d(ch_high),
            nn.SiLU(inplace=True),
        )
        self.fuse_conv = nn.Conv2d(ch_tgt + ch_high, out_ch, kernel_size=1, bias=False)
        self.fuse_bn = nn.BatchNorm2d(out_ch)
        self.fuse_act = nn.SiLU(inplace=True)
        self.gc = GlobalContext(out_ch, reduction=4)
        self.proj_res = (
            nn.Conv2d(ch_tgt, out_ch, kernel_size=1, bias=False)
            if out_ch != ch_tgt
            else nn.Identity()
        )

    def forward(self, x_high: torch.Tensor, x_tgt: torch.Tensor) -> torch.Tensor:
        xh = F.silu(self.bn_align(self.align(x_high)), inplace=True)
        xh = F.silu(self.bn_cc(self.cc_high(xh)), inplace=True)
        xh = self.deform_refine_high(xh)
        xh = self.ms_high(xh)
        xh = self.down(xh)
        if xh.shape[-2:] != x_tgt.shape[-2:]:
            xh = F.interpolate(xh, size=x_tgt.shape[-2:], mode="bilinear", align_corners=False)
        fused = torch.cat([x_tgt, xh], dim=1)
        fused = self.fuse_act(self.fuse_bn(self.fuse_conv(fused)))
        fused = self.gc(fused)
        return fused + self.proj_res(x_tgt)


class DropBlock2D(nn.Module):
    """DropBlock regularisation (no-op at eval time)."""

    def __init__(self, drop_prob: float = 0.08, block_size: int = 3):
        super().__init__()
        self.drop_prob = float(drop_prob)
        self.block_size = int(block_size)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if (not self.training) or self.drop_prob <= 0.0:
            return x
        batch_size, channels, height, width = x.shape
        valid_height = height - self.block_size + 1
        valid_width = width - self.block_size + 1
        if valid_height <= 0 or valid_width <= 0:
            gamma = self.drop_prob
        else:
            gamma = (
                self.drop_prob
                * height
                * width
                / (self.block_size ** 2)
                / (valid_height * valid_width)
            )
        center_mask = (
            torch.rand(batch_size, 1, height, width, device=x.device) < gamma
        ).to(x.dtype)
        padding = self.block_size // 2
        block_mask = 1.0 - F.max_pool2d(
            center_mask, kernel_size=self.block_size, stride=1, padding=padding
        )
        block_mask = block_mask.repeat(1, channels, 1, 1)
        keep_ratio = block_mask.mean()
        if keep_ratio <= 0:
            return x
        return x * block_mask / keep_ratio


# ---------------------------------------------------------------------------
# FishEncoder
# ---------------------------------------------------------------------------

class FishEncoder(nn.Module):
    """
    Fish re-identification encoder.

    Backbone: ConvNeXt (timm) — features_only, out_indices=(0,1,2)
    Head:     CoordConv → MixStyle → DeformRefine → DropBlock
              → Reduce → GeM → BNneck → L2-normalise
    Classifier: AdaCos (used for training only; disabled at inference)
    """

    def __init__(
        self,
        num_classes: int,
        out_dim: int = 512,
        model_name: str = "convnext_small.fb_in22k_ft_in1k",
    ):
        super().__init__()
        # pretrained=False: weights come from the .pt checkpoint, not the internet
        self.backbone = timm.create_model(
            model_name,
            pretrained=False,
            features_only=True,
            out_indices=(0, 1, 2),
        )

        reductions = self.backbone.feature_info.reduction()
        self.tgt_idx = (
            reductions.index(8)
            if 8 in reductions
            else min(range(len(reductions)), key=lambda i: abs(reductions[i] - 8))
        )

        channels = self.backbone.feature_info.channels()
        target_channels = channels[self.tgt_idx]
        self.fuse = self.tgt_idx > 0

        self.cc_s8 = CoordConv2d(target_channels, target_channels, kernel_size=3, bias=False, with_r=True)

        self.fuse_block: Optional[HighResFusion] = None
        if self.fuse:
            high_channels = channels[self.tgt_idx - 1]
            self.ms_high = MixStyle(p=0.5, alpha=0.3)
            self.fuse_block = HighResFusion(
                ch_high=high_channels,
                ch_tgt=target_channels,
                out_ch=target_channels,
                mixstyle=self.ms_high,
                with_r=True,
            )
        else:
            self.ms_high = MixStyle(p=0.5, alpha=0.3)

        self.deform_refine_s8 = DeformRefine(target_channels, target_channels, k=3, groups=1, dilation=1)
        self.ms_s8 = MixStyle(p=0.5, alpha=0.3)
        self.dropblock_s8 = DropBlock2D(drop_prob=0.0, block_size=5)

        self.reduce = nn.Conv2d(target_channels, out_dim, kernel_size=1, bias=False)
        self.gem = GeM(in_dim=out_dim)
        self.bnneck = nn.BatchNorm1d(out_dim)
        self.classifier = AdaCos(out_dim, num_classes, m=0.2, init_s=30.0)

    def _pre_bn_feat(self, x: torch.Tensor) -> torch.Tensor:
        features = self.backbone(x)
        x_tgt = features[self.tgt_idx]

        if self.fuse and self.fuse_block is not None:
            x_high = features[self.tgt_idx - 1]
            x_tgt = self.fuse_block(x_high, x_tgt)

        x_tgt = self.cc_s8(x_tgt)
        x_tgt = self.ms_s8(x_tgt)
        x_tgt = self.deform_refine_s8(x_tgt)
        x_tgt = self.dropblock_s8(x_tgt)

        x = self.reduce(x_tgt)
        return self.gem(x).flatten(1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        feature = self._pre_bn_feat(x)
        feature_bn = self.bnneck(feature)
        return F.normalize(feature_bn, dim=-1)

    def forward_embed_bn(self, x: torch.Tensor) -> torch.Tensor:
        """Alias used by inference helpers — same as forward."""
        return self.forward(x)


# ---------------------------------------------------------------------------
# Checkpoint loader
# ---------------------------------------------------------------------------

def _clean_state_dict_keys(state: dict) -> dict:
    """Strip common DDP / wrapper prefixes from checkpoint keys."""
    cleaned: dict = {}
    for key, value in state.items():
        key = key.removeprefix("module.")
        key = key.removeprefix("model.")
        cleaned[key] = value
    return cleaned


def load_model_for_infer(
    model_path: str,
    model_name: str = "convnext_small.fb_in22k_ft_in1k",
    out_dim: int = 512,
    device: Optional[torch.device] = None,
) -> FishEncoder:
    """
    Load a FishEncoder checkpoint for inference.

    Args:
        model_path: Path to the .pt checkpoint file.
        model_name:  timm backbone identifier — must match the training config.
        out_dim:     Embedding dimension (512 for convnext_small runs).
        device:      Target device. Defaults to CUDA if available, else CPU.

    Returns:
        FishEncoder in eval mode on the target device.

    Raises:
        FileNotFoundError: If model_path does not exist.
        TypeError: If the checkpoint format is unexpected.
    """
    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    path = Path(model_path)
    if not path.is_file():
        raise FileNotFoundError(f"FishEncoder checkpoint not found: {path}")

    logger.info("Loading FishEncoder checkpoint: %s  device=%s", path, device)

    try:
        checkpoint = torch.load(str(path), map_location=device, weights_only=True)
    except TypeError:
        checkpoint = torch.load(str(path), map_location=device)

    state = checkpoint.get("state_dict", checkpoint)
    if not isinstance(state, dict):
        raise TypeError(
            f"Checkpoint at {path} does not contain a valid state dictionary. "
            f"Got: {type(state)}"
        )

    state = _clean_state_dict_keys(state)

    # Infer num_classes from AdaCos weight shape
    num_classes = 1
    classifier_weight = state.get("classifier.weight")
    if isinstance(classifier_weight, torch.Tensor) and classifier_weight.ndim == 2:
        num_classes = int(classifier_weight.shape[0])
        logger.info("Inferred num_classes=%d from checkpoint", num_classes)

    model = FishEncoder(num_classes=num_classes, out_dim=out_dim, model_name=model_name).to(device)

    current_state = model.state_dict()
    total_keys = len(current_state)

    # Only load keys where name AND shape match
    compatible_state: dict = {}
    missing_keys: list[str] = []
    shape_mismatches: list[str] = []

    for key in current_state:
        if key not in state:
            missing_keys.append(key)
        elif current_state[key].shape != state[key].shape:
            shape_mismatches.append(
                f"{key}: expected {current_state[key].shape}, got {state[key].shape}"
            )
        else:
            compatible_state[key] = state[key]

    loaded_keys = len(compatible_state)
    model.load_state_dict(compatible_state, strict=False)

    logger.info(
        "FishEncoder loaded: %d/%d keys compatible  |  missing=%d  shape_mismatch=%d",
        loaded_keys, total_keys, len(missing_keys), len(shape_mismatches),
    )
    if missing_keys:
        logger.debug("Missing keys (first 20): %s", missing_keys[:20])
    if shape_mismatches:
        logger.error("Shape mismatches (first 20): %s", shape_mismatches[:20])

    # Claves críticas de la cabeza — si faltan, los embeddings son basura.
    # NOTA: "classifier." (AdaCos) NO se incluye: solo se usa en entrenamiento
    # y se desactiva en inferencia; no afecta al embedding final (forward()
    # termina en bnneck + normalize, sin tocar el classifier).
    critical_prefixes = (
        "reduce.", "gem.", "bnneck.", "fuse_block.", "deform_refine", "cc_s8.",
    )
    critical_missing = [
        k for k in missing_keys
        if any(k.startswith(p) or p in k for p in critical_prefixes)
    ]

    strict_mode = os.getenv("FISHDEX_REID_STRICT_LOAD", "true").lower() == "true"

    if critical_missing or shape_mismatches:
        msg = (
            f"FishEncoder CRITICAL load failure: "
            f"critical_missing={critical_missing[:20]}  "
            f"shape_mismatches={shape_mismatches[:20]}. "
            f"Check FISHDEX_REID_MODEL_NAME='{model_name}' matches the training backbone. "
            f"Set FISHDEX_REID_STRICT_LOAD=false to bypass (dev only)."
        )
        if strict_mode:
            raise RuntimeError(msg)
        logger.error(msg)
    elif loaded_keys < total_keys * 0.9:
        msg_90 = (
            f"FishEncoder loaded only {100.0 * loaded_keys / total_keys:.0f}% of keys — "
            f"embeddings may be unreliable. "
            f"Check that FISHDEX_REID_MODEL_NAME='{model_name}' matches the training backbone."
        )
        if strict_mode:
            raise RuntimeError(msg_90)
        logger.error(msg_90)

    # Disable classifier head gradients (not needed at inference)
    for param in model.classifier.parameters():
        param.requires_grad_(False)

    model.eval()

    # --- WARM-UP SELF-TEST (Fase 2) ---
    # Verify the model produces valid embeddings before declaring readiness
    try:
        import torch
        img_size = getattr(settings, 'reid_img_size', 128)
        dummy_input = torch.randn(1, 3, img_size, img_size)
        with torch.no_grad():
            test_output = model(dummy_input)

        # Validate output
        expected_dim = getattr(settings, 'reid_embedding_dim', 512)
        actual_dim = test_output.shape[-1]

        if actual_dim != expected_dim:
            raise RuntimeError(
                f"FishEncoder self-test FAILED: expected dim={expected_dim}, got {actual_dim}"
            )
        if not torch.isfinite(test_output).all():
            raise RuntimeError(
                "FishEncoder self-test FAILED: output contains NaN or Inf"
            )

        norm = torch.norm(test_output, dim=-1).item()
        if norm < 0.5 or norm > 2.0:
            logger.warning(
                "FishEncoder self-test: L2 norm=%.4f (expected ~1.0). "
                "Model may not be properly trained.",
                norm,
            )

        # Verify deterministic output
        with torch.no_grad():
            test_output_2 = model(dummy_input)
        if not torch.allclose(test_output, test_output_2, atol=1e-6):
            raise RuntimeError(
                "FishEncoder self-test FAILED: non-deterministic output in eval mode"
            )

        logger.info(
            "FishEncoder self-test PASSED: dim=%d, norm=%.4f, deterministic=True",
            actual_dim, norm,
        )
    except ImportError:
        logger.warning("torch not available — skipping FishEncoder self-test")
    except RuntimeError as e:
        if strict_mode:
            raise
        logger.error("FishEncoder self-test failed (non-strict mode): %s", e)

    logger.info("FishEncoder ready for inference.")
    return model
