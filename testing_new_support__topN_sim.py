"""Build capped fish-identity prototypes and identify one query identity.

This is a standalone script containing the FishEncoder architecture,
checkpoint loading, capped support-image sampling, query-image sampling,
nearest-prototype voting, and final similarity output.

Expected support structure:
    SUPPORT_DIR/identity_001/image1.jpg
    SUPPORT_DIR/identity_002/image1.jpg

QUERY_DIR should contain images of one unknown identity, either directly
or inside nested folders.
"""

from __future__ import annotations

import argparse
import math
import os
import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import timm
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms
from torchvision.datasets import ImageFolder
from torchvision.ops import DeformConv2d


def build_eval_transform(img_size: int = 384) -> transforms.Compose:
    return transforms.Compose(
        [
            transforms.Resize((img_size, img_size)),
            transforms.ToTensor(),
            transforms.Normalize(
                (0.485, 0.456, 0.406),
                (0.229, 0.224, 0.225),
            ),
        ]
    )


class MixStyle(nn.Module):
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
        lam = torch.distributions.Beta(self.alpha, self.alpha).sample(
            (batch_size, 1, 1, 1)
        ).to(device=x.device, dtype=x.dtype)

        mixed_mu = lam * mu + (1.0 - lam) * mu[permutation]
        mixed_sigma = lam * sigma + (1.0 - lam) * sigma[permutation]
        return x_normalized * mixed_sigma + mixed_mu


class GeM(nn.Module):
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
    def __init__(
            self,
            in_dim: int,
            n_classes: int,
            m: float = 0.2,
            init_s: float = 30.0,
    ):
        super().__init__()
        self.weight = nn.Parameter(torch.empty(n_classes, in_dim))
        nn.init.xavier_normal_(self.weight)
        self.s = float(init_s)
        self.m = float(m)

    def forward(
            self,
            x: torch.Tensor,
            labels: torch.Tensor | None = None,
    ) -> torch.Tensor:
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
    def __init__(
            self,
            in_ch: int,
            out_ch: int,
            mid_ch: int | None = None,
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
            mid_ch,
            2 * k * k * groups,
            kernel_size=k,
            padding=padding,
            dilation=dilation,
        )
        self.mask = nn.Conv2d(
            mid_ch,
            k * k * groups,
            kernel_size=k,
            padding=padding,
            dilation=dilation,
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
        self.post = nn.Sequential(
            nn.BatchNorm2d(out_ch),
            nn.SiLU(inplace=True),
        )
        self.proj = (
            nn.Conv2d(in_ch, out_ch, kernel_size=1, bias=False)
            if in_ch != out_ch
            else nn.Identity()
        )

        self.last_offset: torch.Tensor | None = None
        self.last_mask: torch.Tensor | None = None

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        z = self.pre(x)
        offset = self.offset(z)
        mask = torch.sigmoid(self.mask(z))
        y = self.dcn(z, offset, mask)
        y = self.post(y)
        self.last_offset = offset
        self.last_mask = mask
        return y + self.proj(x)


class AddCoords(nn.Module):
    def __init__(self, with_r: bool = True):
        super().__init__()
        self.with_r = bool(with_r)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        batch_size, _, height, width = x.shape
        yy = torch.linspace(
            -1.0,
            1.0,
            steps=height,
            device=x.device,
            dtype=x.dtype,
        ).view(1, 1, height, 1)
        xx = torch.linspace(
            -1.0,
            1.0,
            steps=width,
            device=x.device,
            dtype=x.dtype,
        ).view(1, 1, 1, width)

        yy = yy.expand(batch_size, 1, height, width)
        xx = xx.expand(batch_size, 1, height, width)

        if self.with_r:
            radius = torch.sqrt(torch.clamp(xx.square() + yy.square(), min=0.0))
            return torch.cat([x, xx, yy, radius], dim=1)
        return torch.cat([x, xx, yy], dim=1)


class CoordConv2d(nn.Module):
    def __init__(
            self,
            in_channels: int,
            out_channels: int,
            kernel_size: int = 3,
            stride: int = 1,
            padding: int | None = None,
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
    def __init__(self, channels: int, reduction: int = 4):
        super().__init__()
        hidden_channels = max(1, channels // reduction)
        self.fc1 = nn.Conv2d(channels, hidden_channels, 1, bias=False)
        self.act = nn.SiLU(inplace=True)
        self.fc2 = nn.Conv2d(hidden_channels, channels, 1, bias=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        context = x.mean(dim=(2, 3), keepdim=True)
        weights = self.fc2(self.act(self.fc1(context)))
        return x * torch.sigmoid(weights)


class HighResFusion(nn.Module):
    def __init__(
            self,
            ch_high: int,
            ch_tgt: int,
            out_ch: int,
            mixstyle: nn.Module | None = None,
            with_r: bool = True,
    ):
        super().__init__()
        self.align = nn.Conv2d(ch_high, ch_high, kernel_size=1, bias=False)
        self.bn_align = nn.BatchNorm2d(ch_high)

        self.cc_high = CoordConv2d(
            in_channels=ch_high,
            out_channels=ch_high,
            kernel_size=3,
            bias=False,
            with_r=with_r,
        )
        self.bn_cc = nn.BatchNorm2d(ch_high)

        self.deform_refine_high = DeformRefine(
            in_ch=ch_high,
            out_ch=ch_high,
            k=3,
            groups=2,
            dilation=1,
        )
        self.ms_high = mixstyle if mixstyle is not None else MixStyle()

        self.down = nn.Sequential(
            nn.Conv2d(
                ch_high,
                ch_high,
                kernel_size=3,
                stride=2,
                padding=1,
                groups=ch_high,
                bias=False,
            ),
            nn.BatchNorm2d(ch_high),
            nn.SiLU(inplace=True),
            nn.Conv2d(ch_high, ch_high, kernel_size=1, bias=False),
            nn.BatchNorm2d(ch_high),
            nn.SiLU(inplace=True),
        )

        self.fuse_conv = nn.Conv2d(
            ch_tgt + ch_high,
            out_ch,
            kernel_size=1,
            bias=False,
        )
        self.fuse_bn = nn.BatchNorm2d(out_ch)
        self.fuse_act = nn.SiLU(inplace=True)
        self.gc = GlobalContext(out_ch, reduction=4)
        self.proj_res = (
            nn.Conv2d(ch_tgt, out_ch, kernel_size=1, bias=False)
            if out_ch != ch_tgt
            else nn.Identity()
        )

    def forward(
            self,
            x_high: torch.Tensor,
            x_tgt: torch.Tensor,
    ) -> torch.Tensor:
        xh = F.silu(self.bn_align(self.align(x_high)), inplace=True)
        xh = F.silu(self.bn_cc(self.cc_high(xh)), inplace=True)
        xh = self.deform_refine_high(xh)
        xh = self.ms_high(xh)
        xh = self.down(xh)

        if xh.shape[-2:] != x_tgt.shape[-2:]:
            xh = F.interpolate(
                xh,
                size=x_tgt.shape[-2:],
                mode="bilinear",
                align_corners=False,
            )

        fused = torch.cat([x_tgt, xh], dim=1)
        fused = self.fuse_act(self.fuse_bn(self.fuse_conv(fused)))
        fused = self.gc(fused)
        return fused + self.proj_res(x_tgt)


class DropBlock2D(nn.Module):
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
            center_mask,
            kernel_size=self.block_size,
            stride=1,
            padding=padding,
        )
        block_mask = block_mask.repeat(1, channels, 1, 1)

        keep_ratio = block_mask.mean()
        if keep_ratio <= 0:
            return x
        return x * block_mask / keep_ratio


class FishEncoder(nn.Module):
    def __init__(
            self,
            num_classes: int,
            out_dim: int = 256,
            model_name: str = "convnext_large.fb_in22k_ft_in1k",
    ):
        super().__init__()
        self.backbone = timm.create_model(
            model_name,
            pretrained=True,
            features_only=True,
            out_indices=(0, 1, 2),
        )

        reductions = self.backbone.feature_info.reduction()
        self.tgt_idx = (
            reductions.index(8)
            if 8 in reductions
            else min(
                range(len(reductions)),
                key=lambda index: abs(reductions[index] - 8),
            )
        )

        channels = self.backbone.feature_info.channels()
        target_channels = channels[self.tgt_idx]
        self.fuse = self.tgt_idx > 0

        self.cc_s8 = CoordConv2d(
            target_channels,
            target_channels,
            kernel_size=3,
            bias=False,
            with_r=True,
        )

        self.fuse_block: HighResFusion | None = None
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

        self.deform_refine_s8 = DeformRefine(
            in_ch=target_channels,
            out_ch=target_channels,
            k=3,
            groups=1,
            dilation=1,
        )
        self.ms_s8 = MixStyle(p=0.5, alpha=0.3)
        self.dropblock_s8 = DropBlock2D(drop_prob=0.0, block_size=5)

        self.reduce = nn.Conv2d(
            target_channels,
            out_dim,
            kernel_size=1,
            bias=False,
        )
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
        return self.forward(x)


def get_device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def load_model_for_proto_infer(
        model_path: str,
        model_name: str = "convnext_small.fb_in22k_ft_in1k_384",
        out_dim: int = 256,
) -> FishEncoder:
    device = get_device()

    try:
        checkpoint = torch.load(
            model_path,
            map_location=device,
            weights_only=True,
        )
    except TypeError as exc:
        # Do NOT silently fall back to an unsafe load: torch.load without
        # weights_only unpickles the file and can execute arbitrary code.
        raise RuntimeError(
            "This PyTorch build does not support torch.load(weights_only=True). "
            "Upgrade to torch>=2.4 rather than loading checkpoints unsafely."
        ) from exc

    state = checkpoint.get("state_dict", checkpoint)
    if not isinstance(state, dict):
        raise TypeError("Checkpoint does not contain a valid state dictionary.")

    num_classes = 1
    classifier_weight = state.get("classifier.weight")
    if isinstance(classifier_weight, torch.Tensor) and classifier_weight.ndim == 2:
        num_classes = int(classifier_weight.shape[0])

    model = FishEncoder(
        num_classes=num_classes,
        out_dim=out_dim,
        model_name=model_name,
    ).to(device)

    current_state = model.state_dict()
    compatible_state = {
        key: value
        for key, value in state.items()
        if key in current_state and current_state[key].shape == value.shape
    }
    model.load_state_dict(compatible_state, strict=False)

    for parameter in model.classifier.parameters():
        parameter.requires_grad_(False)

    model.eval()
    return model


# -----------------------------------------------------------------------------
# Prototype building and single-identity matching
# -----------------------------------------------------------------------------
IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
}


class ImagePathDataset(Dataset):
    def __init__(self, records, transform):
        self.records = list(records)
        self.transform = transform

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int):
        path, label = self.records[index]
        with Image.open(path) as image:
            image = image.convert("RGB")
            tensor = self.transform(image)
        return tensor, label


@dataclass(frozen=True)
class MatchResult:
    identity: str
    average_similarity: float
    query_images_used: int
    winning_votes: int


def _validate_positive_limit(name: str, value: int) -> None:
    if value < 1:
        raise ValueError(f"{name} must be at least 1, got {value}.")


def _list_query_images(query_dir: str) -> list[str]:
    root = Path(query_dir)
    if not root.is_dir():
        raise NotADirectoryError(f"Query directory does not exist: {query_dir}")

    paths = sorted(
        str(path)
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )
    if not paths:
        raise RuntimeError(f"No supported images found in query directory: {query_dir}")
    return paths


def _sample_paths(
        paths: list[str],
        maximum: int,
        rng: random.Random,
) -> list[str]:
    if len(paths) <= maximum:
        return list(paths)
    return sorted(rng.sample(paths, maximum))


@torch.inference_mode()
def build_prototypes(
        model,
        support_dir: str,
        max_images_per_identity: int,
        img_size: int = 128,
        batch_size: int = 128,
        num_workers: int = 4,
        seed: int = 1234,
) -> tuple[torch.Tensor, list[str]]:
    """Build one normalized mean prototype per support identity.

    At most ``max_images_per_identity`` randomly selected images are used for
    each identity. Sampling is deterministic for a fixed seed.
    """
    _validate_positive_limit(
        "max_images_per_identity",
        max_images_per_identity,
    )

    source = ImageFolder(support_dir, transform=None)
    if len(source) == 0:
        raise RuntimeError(f"No support images found in: {support_dir}")

    grouped_paths: dict[int, list[str]] = defaultdict(list)
    for path, label in source.samples:
        grouped_paths[int(label)].append(path)

    rng = random.Random(seed)
    selected_records: list[tuple[str, int]] = []
    for label in range(len(source.classes)):
        identity_paths = sorted(grouped_paths[label])
        selected_paths = _sample_paths(
            identity_paths,
            max_images_per_identity,
            rng,
        )
        selected_records.extend((path, label) for path in selected_paths)

    transform = build_eval_transform(img_size)
    loader = DataLoader(
        ImagePathDataset(selected_records, transform),
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=(get_device().type == "cuda"),
    )

    embeddings_by_identity: dict[int, list[torch.Tensor]] = defaultdict(list)
    device = next(model.parameters()).device

    for images, labels in loader:
        images = images.to(device, non_blocking=True)
        embeddings = model.forward_embed_bn(images)
        for embedding, label in zip(embeddings, labels.tolist()):
            embeddings_by_identity[int(label)].append(embedding)

    prototypes = []
    prototype_names = []
    for label, identity_name in enumerate(source.classes):
        identity_embeddings = embeddings_by_identity.get(label, [])
        if not identity_embeddings:
            continue

        matrix = torch.stack(identity_embeddings, dim=0)
        prototype = F.normalize(matrix.mean(dim=0), dim=0)
        prototypes.append(prototype)
        prototype_names.append(identity_name)

    if not prototypes:
        raise RuntimeError("No prototypes could be created.")

    return torch.stack(prototypes, dim=0), prototype_names


@torch.inference_mode()
def identify_query_identity(
        model,
        prototype_matrix: torch.Tensor,
        prototype_names: list[str],
        query_dir: str,
        max_query_images_for_vote: int,
        img_size: int = 128,
        batch_size: int = 128,
        num_workers: int = 4,
        seed: int = 1234,
) -> MatchResult:
    """Identify one query identity using per-image nearest-prototype voting.

    Each sampled query image votes for its nearest prototype. If identities tie
    on vote count, the identity with the greater mean similarity across all
    sampled query images wins. The reported average similarity is the mean
    cosine similarity from every sampled query image to the winning prototype.
    """
    _validate_positive_limit(
        "max_query_images_for_vote",
        max_query_images_for_vote,
    )

    if prototype_matrix.ndim != 2:
        raise ValueError("prototype_matrix must have shape [identities, embedding_dim].")
    if prototype_matrix.shape[0] != len(prototype_names):
        raise ValueError("prototype_matrix rows and prototype_names length do not match.")

    rng = random.Random(seed)
    query_paths = _sample_paths(
        _list_query_images(query_dir),
        max_query_images_for_vote,
        rng,
    )

    transform = build_eval_transform(img_size)
    query_records = [(path, 0) for path in query_paths]
    loader = DataLoader(
        ImagePathDataset(query_records, transform),
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=(get_device().type == "cuda"),
    )

    device = next(model.parameters()).device
    query_embeddings = []
    for images, _ in loader:
        images = images.to(device, non_blocking=True)
        query_embeddings.append(model.forward_embed_bn(images))

    query_matrix = torch.cat(query_embeddings, dim=0)
    prototype_matrix = prototype_matrix.to(device)
    similarities = query_matrix @ prototype_matrix.T

    per_image_winners = similarities.argmax(dim=1)
    vote_counts = Counter(per_image_winners.tolist())
    maximum_votes = max(vote_counts.values())
    tied_indices = [
        index for index, count in vote_counts.items() if count == maximum_votes
    ]

    if len(tied_indices) == 1:
        winning_index = tied_indices[0]
    else:
        winning_index = max(
            tied_indices,
            key=lambda index: float(similarities[:, index].mean().item()),
        )

    average_similarity = float(similarities[:, winning_index].mean().item())
    return MatchResult(
        identity=prototype_names[winning_index],
        average_similarity=average_similarity,
        query_images_used=len(query_paths),
        winning_votes=vote_counts[winning_index],
    )


def _parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments.

    Returns:
        Namespace with ``model_path``, ``support_dir``, ``query_dir`` and the
        sampling/threshold knobs.

    Raises:
        SystemExit: A required path is missing or does not exist.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Identify a query fish against a support gallery using FishEncoder "
            "prototypes and top-N majority voting."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--model-path",
        default=os.environ.get("FISHDEX_REID_MODEL_PATH"),
        help="FishEncoder checkpoint (.pt) (env: FISHDEX_REID_MODEL_PATH)",
    )
    parser.add_argument(
        "--support-dir",
        default=os.environ.get("FISHDEX_REID_SUPPORT_DIR"),
        help=(
            "Gallery directory with one subdirectory per known identity "
            "(env: FISHDEX_REID_SUPPORT_DIR)"
        ),
    )
    parser.add_argument(
        "--query-dir",
        default=os.environ.get("FISHDEX_REID_QUERY_DIR"),
        help=(
            "Directory holding images of the single identity to identify "
            "(env: FISHDEX_REID_QUERY_DIR)"
        ),
    )
    parser.add_argument(
        "--max-support-images",
        type=int,
        default=int(os.environ.get("FISHDEX_REID_MAX_SUPPORT_IMAGES", "5")),
        help="Maximum support images used to build each identity prototype",
    )
    parser.add_argument(
        "--max-query-images",
        type=int,
        default=int(os.environ.get("FISHDEX_REID_MAX_QUERY_IMAGES", "5")),
        help="Maximum query images sampled for majority voting",
    )
    parser.add_argument(
        "--img-size",
        type=int,
        default=int(os.environ.get("FISHDEX_REID_IMG_SIZE", "128")),
        help="Model input resolution; must match the value used at training time",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=int(os.environ.get("FISHDEX_REID_RANDOM_SEED", "1234")),
        help="Random seed for support/query sampling (reproducibility)",
    )
    args = parser.parse_args()

    missing = [
        flag
        for flag, value in (
            ("--model-path", args.model_path),
            ("--support-dir", args.support_dir),
            ("--query-dir", args.query_dir),
        )
        if not value
    ]
    if missing:
        parser.error(f"missing required argument(s): {', '.join(missing)}")

    if not Path(args.model_path).is_file():
        parser.error(f"model checkpoint not found: {args.model_path}")
    for flag, directory in (
        ("--support-dir", args.support_dir),
        ("--query-dir", args.query_dir),
    ):
        if not Path(directory).is_dir():
            parser.error(f"{flag} directory not found: {directory}")

    return args


def main() -> None:
    # ---------------- REQUIRED INPUTS ----------------
    # Paths were hardcoded to /home/dev/... and made this script unrunnable
    # elsewhere. They are now CLI arguments with environment-variable fallbacks.
    args = _parse_args()
    MODEL_PATH = args.model_path

    # Contains one subdirectory per known identity.
    SUPPORT_DIR = args.support_dir

    # Contains images of ONE identity to identify. It may be a direct image
    # directory or a directory containing nested image folders.
    QUERY_DIR = args.query_dir

    # Maximum number of support images used to build EACH identity prototype.
    MAX_SUPPORT_IMAGES_PER_IDENTITY = args.max_support_images

    # Maximum number of query images sampled and used in majority voting.
    MAX_QUERY_IMAGES_FOR_VOTE = args.max_query_images

    # ---------------- MODEL SETTINGS ----------------
    IMG_SIZE = args.img_size
    BATCH_SIZE = 128
    NUM_WORKERS = 4
    RANDOM_SEED = args.seed
    MODEL_NAME = "convnext_small.fb_in22k_ft_in1k"
    EMBEDDING_DIM = 512

    if not os.path.isfile(MODEL_PATH):
        raise FileNotFoundError(f"Model checkpoint not found: {MODEL_PATH}")

    model = load_model_for_proto_infer(
        model_path=MODEL_PATH,
        model_name=MODEL_NAME,
        out_dim=EMBEDDING_DIM,
    )

    prototype_matrix, prototype_names = build_prototypes(
        model=model,
        support_dir=SUPPORT_DIR,
        max_images_per_identity=MAX_SUPPORT_IMAGES_PER_IDENTITY,
        img_size=IMG_SIZE,
        batch_size=BATCH_SIZE,
        num_workers=NUM_WORKERS,
        seed=RANDOM_SEED,
    )

    result = identify_query_identity(
        model=model,
        prototype_matrix=prototype_matrix,
        prototype_names=prototype_names,
        query_dir=QUERY_DIR,
        max_query_images_for_vote=MAX_QUERY_IMAGES_FOR_VOTE,
        img_size=IMG_SIZE,
        batch_size=BATCH_SIZE,
        num_workers=NUM_WORKERS,
        seed=RANDOM_SEED,
    )

    # Only the requested final output.
    print(f"Most similar ID: {result.identity}")
    print(f"Average similarity: {result.average_similarity:.6f}")


if __name__ == "__main__":
    main()
