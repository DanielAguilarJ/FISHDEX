"""
FishDex AI Server - Upload media validation
===========================================
Decides whether an uploaded file is an image or a video, and derives a safe
on-disk extension.

Why the extension is regenerated
--------------------------------
The client-supplied ``filename`` must never influence the stored path or the
extension. An attacker could otherwise upload ``payload.html`` and — because the
storage directory is served statically in development — get same-origin HTML
executed in the dashboard's context (stored XSS). Only extensions from the
allow-lists below are ever written to disk.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Final, Optional

logger = logging.getLogger(__name__)


class MediaValidationError(ValueError):
    """Raised when an upload cannot be accepted as an image or a video."""


IMAGE_SUFFIXES: Final[frozenset[str]] = frozenset(
    {".jpg", ".jpeg", ".png", ".webp", ".heic"}
)
VIDEO_SUFFIXES: Final[frozenset[str]] = frozenset(
    {".mp4", ".mov", ".avi", ".mkv", ".3gp", ".webm"}
)

_GENERIC_CONTENT_TYPES: Final[frozenset[str]] = frozenset(
    {"", "application/octet-stream", "binary/octet-stream"}
)

DEFAULT_IMAGE_SUFFIX: Final[str] = ".jpg"
DEFAULT_VIDEO_SUFFIX: Final[str] = ".mp4"


def resolve_media_type(content_type: Optional[str], filename: Optional[str]) -> str:
    """
    Classify an upload as an image or a video.

    Resolution order: declared MIME type, then file extension, then a generic
    binary fallback that assumes video (the capture field is a camera recording).

    Args:
        content_type: MIME type declared by the client.
        filename: Original filename declared by the client.

    Returns:
        Either ``"image"`` or ``"video"``.

    Raises:
        MediaValidationError: The upload is neither an image nor a video.
    """
    normalized_type = (content_type or "").lower().strip()
    suffix = _client_suffix(filename)

    if normalized_type.startswith("image/") or suffix in IMAGE_SUFFIXES:
        return "image"
    if normalized_type.startswith("video/") or suffix in VIDEO_SUFFIXES:
        return "video"
    if normalized_type in _GENERIC_CONTENT_TYPES:
        logger.warning(
            "Generic content_type %r for file %r; treating as video",
            normalized_type,
            filename,
        )
        return "video"

    raise MediaValidationError(
        "Formato de archivo no soportado. Debe ser imagen o video "
        f"(recibido: {normalized_type or 'desconocido'})"
    )


def safe_suffix_for(filename: Optional[str], media_type: str) -> str:
    """
    Derive an allow-listed file extension for on-disk storage.

    Args:
        filename: Client-supplied filename (used only as a hint).
        media_type: ``"image"`` or ``"video"``.

    Returns:
        A lowercase extension that is guaranteed to be in the allow-list for
        ``media_type``; falls back to a safe default otherwise.
    """
    allowed = IMAGE_SUFFIXES if media_type == "image" else VIDEO_SUFFIXES
    default = DEFAULT_IMAGE_SUFFIX if media_type == "image" else DEFAULT_VIDEO_SUFFIX

    suffix = _client_suffix(filename)
    if suffix in allowed:
        return suffix
    if suffix:
        logger.info(
            "Rejected client suffix %r for %s upload; using %s",
            suffix,
            media_type,
            default,
        )
    return default


def _client_suffix(filename: Optional[str]) -> str:
    """
    Extract a lowercase extension from an untrusted filename.

    Uses only the basename so that directory components in the supplied name
    cannot leak into the result.

    Args:
        filename: Client-supplied filename.

    Returns:
        The lowercase suffix including the dot, or an empty string.
    """
    if not filename:
        return ""
    # PurePath handles both separators; take the final component only.
    basename = Path(filename.replace("\\", "/")).name
    return Path(basename).suffix.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Content sniffing
# ─────────────────────────────────────────────────────────────────────────────
_IMAGE_MAGIC: Final[tuple[bytes, ...]] = (
    b"\xff\xd8\xff",  # JPEG
    b"\x89PNG\r\n\x1a\n",  # PNG
)

_ISO_BMFF_BRAND_OFFSET: Final[int] = 4
_ISO_BMFF_BRAND: Final[bytes] = b"ftyp"  # MP4/MOV/3GP/HEIC container


def looks_like_supported_media(header: bytes) -> bool:
    """
    Cheap magic-byte sanity check on the first bytes of an upload.

    This is defence in depth, not authentication: decoding still happens later in
    the pipeline. It rejects obvious non-media payloads (scripts, archives, HTML)
    before they are written to disk.

    Args:
        header: First bytes of the uploaded file (32 bytes is enough).

    Returns:
        True when the header matches a known image or container signature.
    """
    if len(header) < 12:
        return False
    if header.startswith(_IMAGE_MAGIC):
        return True
    if header[_ISO_BMFF_BRAND_OFFSET : _ISO_BMFF_BRAND_OFFSET + 4] == _ISO_BMFF_BRAND:
        return True
    if header.startswith(b"RIFF") and header[8:12] in (b"AVI ", b"WEBP"):
        return True
    if header.startswith(b"\x1a\x45\xdf\xa3"):  # Matroska / WebM
        return True
    return False
