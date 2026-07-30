"""
FishDex AI Server - Identification jobs
=======================================
Upload a capture, register it as a job, trigger processing and read the result.

Authorisation model
-------------------
``POST /upload`` accepts either a signed session token or the shared client
secret. When a session token is present it is **authoritative**: the job is
attributed to the token's subject and the client-supplied ``user_id`` form field
is ignored. This closes the previous hole where any caller holding the shared
app secret could attribute a capture to an arbitrary user id.

Reads (``GET /{job_id}``, ``GET /{job_id}/result``) and re-processing require a
session token and enforce **ownership**: only the job's owner, a researcher or an
admin may access it. Previously the shared secret alone was sufficient, which let
anyone who extracted it from the APK enumerate every job and its GPS data.
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)

from app.config import settings
from app.data.czech_species import CZECH_SPECIES
from app.database import db_session
from app.middleware.auth import AuthenticatedUser, verify_auth
from app.routers.auth import ELEVATED_ROLES
from app.services.czech_area_service import validate_area_code
from app.services.job_service import process_identification_job
from app.services.result_cache import get_result_cache, invalidate_job_result
from app.utils.area_utils import normalize_area_code
from app.utils.media_validation import (
    MediaValidationError,
    looks_like_supported_media,
    resolve_media_type,
    safe_suffix_for,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])

Principal = Annotated[AuthenticatedUser, Depends(verify_auth)]

# Columns that must never reach a non-elevated client.
_INTERNAL_JOB_KEYS = ("linkage_json", "artifact_dir", "error_message")

_SENSITIVE_CATCH_KEYS = (
    "location_lat",
    "location_lng",
    "latitude",
    "longitude",
    "user_id",
    "first_seen_by",
    "last_seen_by",
)


# ─────────────────────────────────────────────────────────────────────────────
# Identity helpers
# ─────────────────────────────────────────────────────────────────────────────
def _lookup_role(conn: sqlite3.Connection, user_id: Optional[str]) -> str:
    """
    Read a user's role from the database. Never trusts a client-submitted role.

    Args:
        conn: Open connection.
        user_id: User to look up; may be None.

    Returns:
        The stored role, or ``"fisherman"`` when unknown.
    """
    if not user_id:
        return "fisherman"
    row = conn.execute(
        "SELECT role FROM users WHERE id = ? LIMIT 1", (user_id,)
    ).fetchone()
    if row is None:
        return "fisherman"
    return row["role"] or "fisherman"


def _user_exists(conn: sqlite3.Connection, user_id: str) -> bool:
    """
    Report whether a user id is present in the database.

    Args:
        conn: Open connection.
        user_id: Candidate id.

    Returns:
        True when the account exists.
    """
    return (
        conn.execute(
            "SELECT 1 FROM users WHERE id = ? LIMIT 1", (user_id,)
        ).fetchone()
        is not None
    )


def _require_session_user(principal: AuthenticatedUser) -> str:
    """
    Require a per-user session token rather than a shared machine secret.

    Args:
        principal: Result of :func:`app.middleware.auth.verify_auth`.

    Returns:
        The authenticated user id.

    Raises:
        HTTPException 403: The caller only proved possession of a shared secret.
    """
    if principal.is_machine:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Este recurso requiere autenticación de usuario. "
                "Inicie sesión en /api/v1/auth/login y use el token devuelto."
            ),
        )
    return principal.user_id


def _authorize_job_access(
    conn: sqlite3.Connection, job_row: sqlite3.Row, requester_id: str
) -> str:
    """
    Enforce that the requester owns the job or holds an elevated role.

    Args:
        conn: Open connection.
        job_row: Row from ``identification_jobs``.
        requester_id: Authenticated caller.

    Returns:
        The requester's role.

    Raises:
        HTTPException 403: Caller is neither the owner nor elevated.
    """
    requester_role = _lookup_role(conn, requester_id)
    if job_row["user_id"] == requester_id or requester_role in ELEVATED_ROLES:
        return requester_role
    logger.warning(
        "Blocked cross-user job access: requester=%s job_owner=%s",
        requester_id,
        job_row["user_id"],
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="No puedes acceder a un trabajo de otro usuario",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Response shaping
# ─────────────────────────────────────────────────────────────────────────────
def _strip_internal_keys(data: dict[str, Any]) -> dict[str, Any]:
    """
    Remove server-internal bookkeeping fields from an outbound payload.

    Args:
        data: Row dict.

    Returns:
        A new dict without internal keys (input is not mutated).
    """
    return {k: v for k, v in data.items() if k not in _INTERNAL_JOB_KEYS}


def _strip_sensitive_for_fisherman(data: dict[str, Any]) -> dict[str, Any]:
    """
    Redact historical GPS coordinates and user ids for the fisherman role.

    Args:
        data: Sighting payload, possibly containing nested catch records.

    Returns:
        A new payload with nested sensitive fields removed. Nested dicts are
        copied rather than mutated in place.
    """
    redacted = dict(data)

    for catch_key in ("previous_catch", "matched_reference_catch"):
        catch = redacted.get(catch_key)
        if isinstance(catch, dict):
            redacted[catch_key] = {
                k: v for k, v in catch.items() if k not in _SENSITIVE_CATCH_KEYS
            }

    sim_ref = redacted.get("similarity_reference")
    if isinstance(sim_ref, dict):
        redacted["similarity_reference"] = {
            k: v
            for k, v in sim_ref.items()
            if k
            not in ("reference_area_code", "reference_area_name", "distance_m")
        }
    return redacted


def _parse_json_column(raw: Optional[str], *, context: str) -> dict[str, Any]:
    """
    Parse a JSON text column, tolerating legacy/corrupt values.

    Args:
        raw: Raw column value.
        context: Identifier used in the warning log when parsing fails.

    Returns:
        The decoded dict, or an empty dict.
    """
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError) as exc:
        logger.warning("Malformed JSON in %s: %s", context, exc)
        return {}
    return parsed if isinstance(parsed, dict) else {}


# ─────────────────────────────────────────────────────────────────────────────
# Input validation
# ─────────────────────────────────────────────────────────────────────────────
def _resolve_species_slug(raw_slug: str) -> str:
    """
    Map a client-supplied species slug onto the canonical catalog entry.

    Args:
        raw_slug: Slug as sent by the client.

    Returns:
        The canonical slug from ``CZECH_SPECIES``.

    Raises:
        HTTPException 422: Slug is not in the catalog.
    """
    normalized = raw_slug.strip().lower().replace("-", "_")
    match = next(
        (item for item in CZECH_SPECIES if item["slug"].lower() == normalized), None
    )
    if match is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "species_slug es obligatorio y debe coincidir exactamente "
                "con un slug del catálogo de especies"
            ),
        )
    return match["slug"]


def _validate_coordinates(latitude: float, longitude: float) -> None:
    """
    Reject non-finite or out-of-range GPS coordinates.

    Args:
        latitude: Degrees north.
        longitude: Degrees east.

    Raises:
        HTTPException 422: Coordinates are unusable.
    """
    if (
        not math.isfinite(latitude)
        or not math.isfinite(longitude)
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Las coordenadas GPS de la captura no son válidas",
        )


def _validate_optional_area(area_code: Optional[str]) -> None:
    """
    Validate a Czech fishing-area code when one was supplied.

    Args:
        area_code: Raw area code or None.

    Raises:
        HTTPException 422: Code is present but invalid.
    """
    if not area_code or not area_code.strip():
        return
    is_valid, error = validate_area_code(area_code.strip())
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Código de revír inválido: {error}",
        )


def _validate_size_cm(size_cm: Optional[float]) -> None:
    """
    Sanity-check the reported fish length.

    Args:
        size_cm: Reported length in centimetres, or None.

    Raises:
        HTTPException 422: Value is non-finite or outside 0–400 cm.
    """
    if size_cm is None:
        return
    if not math.isfinite(size_cm) or not 0 < size_cm <= 400:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="size_cm debe estar entre 0 y 400 cm",
        )


async def _persist_upload(
    upload_file: UploadFile, job_id: str, media_type: str
) -> tuple[str, Path]:
    """
    Stream the upload to disk under a server-generated filename.

    The stored name is derived from ``job_id`` plus an allow-listed extension, so
    a hostile ``filename`` cannot influence the path or the served content type.

    Args:
        upload_file: Incoming file.
        job_id: Generated job identifier.
        media_type: ``"image"`` or ``"video"``.

    Returns:
        Tuple of (relative filename, absolute path).

    Raises:
        HTTPException 413: File exceeds the configured size limit.
        HTTPException 400: File is empty.
        HTTPException 500: Write failure.
    """
    suffix = safe_suffix_for(upload_file.filename, media_type)
    relative_name = f"raw_videos/{job_id}_raw{suffix}"
    local_path = Path(settings.server_data_dir) / "storage" / relative_name
    local_path.parent.mkdir(parents=True, exist_ok=True)

    max_size_bytes = int(settings.max_video_size_mb or 50) * 1024 * 1024
    content = await upload_file.read()

    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo de captura está vacío",
        )
    if len(content) > max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                "El archivo excede el límite de tamaño permitido de "
                f"{settings.max_video_size_mb}MB"
            ),
        )
    if not looks_like_supported_media(content[:32]):
        logger.warning(
            "Rejected upload for job %s: header does not match a known media format",
            job_id,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El contenido del archivo no corresponde a una imagen o video válido",
        )

    try:
        local_path.write_bytes(content)
    except OSError as exc:
        logger.error("Failed to write uploaded capture file to disk: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al escribir el archivo de captura en el disco",
        )

    logger.info(
        "Saved raw %s for job %s (%.1f KB)", media_type, job_id, len(content) / 1024
    )
    return relative_name, local_path


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_job_video(
    background_tasks: BackgroundTasks,
    principal: Principal,
    video: Optional[UploadFile] = File(default=None),
    file: Optional[UploadFile] = File(default=None),
    user_id: Optional[str] = Form(default=None),
    area_code: Optional[str] = Form(default=None),
    area_name: Optional[str] = Form(default=None),
    latitude: float = Form(...),
    longitude: float = Form(...),
    species_slug: str = Form(...),
    notes: Optional[str] = Form(default=None),
    weather: Optional[str] = Form(default=None),
    bite: Optional[str] = Form(default=None),
    size_cm: Optional[float] = Form(default=None),
    fish_state: Optional[str] = Form(default=None),
    custom_name: Optional[str] = Form(default=None),
    gps_accuracy_m: Optional[float] = Form(default=None),
    gps_timestamp: Optional[str] = Form(default=None),
    gps_is_mocked: Optional[bool] = Form(default=False),
    gps_source: Optional[str] = Form(default="current"),
    area_selection_source: Optional[str] = Form(default="user_selected"),
) -> dict[str, str]:
    """
    Register a raw capture (photo or video) and queue it for identification.

    Args:
        background_tasks: FastAPI background task registry.
        principal: Authenticated caller.
        video: Capture file (preferred field name).
        file: Alternative capture field name, for older clients.
        user_id: Legacy attribution field. Ignored when a session token is used.
        area_code: Czech fishing-area code.
        area_name: Human-readable area name.
        latitude: Capture latitude.
        longitude: Capture longitude.
        species_slug: Species slug from the Czech catalog.
        notes: Free-text notes.
        weather: Weather conditions.
        bite: Bait or lure used.
        size_cm: Measured length in centimetres.
        fish_state: Injuries or distinguishing marks.
        custom_name: User-assigned nickname.
        gps_accuracy_m: Reported GPS accuracy.
        gps_timestamp: Client GPS timestamp.
        gps_is_mocked: Whether the OS flagged the location as mocked.
        gps_source: How the location was obtained.
        area_selection_source: How the area was chosen.

    Returns:
        Dict containing the new ``job_id``.

    Raises:
        HTTPException 400: No file supplied, or file empty.
        HTTPException 401/403: Authentication or attribution problem.
        HTTPException 413: File too large.
        HTTPException 422: Invalid species, coordinates, area or GPS.
        HTTPException 500: Persistence failure.
    """
    canonical_species = _resolve_species_slug(species_slug)
    _validate_coordinates(latitude, longitude)
    _validate_optional_area(area_code)
    _validate_size_cm(size_cm)

    if gps_is_mocked:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="GPS simulado detectado. Use ubicación real para la captura.",
        )

    upload_file = file or video
    if upload_file is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se proporcionó ningún archivo (video o file)",
        )

    try:
        media_type = resolve_media_type(
            upload_file.content_type, upload_file.filename
        )
    except MediaValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        )

    owner_id = _resolve_owner_id(principal, user_id)

    job_id = str(uuid.uuid4())
    relative_name, local_path = await _persist_upload(upload_file, job_id, media_type)

    try:
        _insert_job_row(
            job_id=job_id,
            owner_id=owner_id,
            relative_name=relative_name,
            media_type=media_type,
            original_filename=upload_file.filename or "unknown",
            content_type=(upload_file.content_type or "").lower().strip(),
            area_code=area_code,
            area_name=area_name,
            latitude=latitude,
            longitude=longitude,
            species_slug=canonical_species,
            notes=notes,
            weather=weather,
            bite=bite,
            size_cm=size_cm,
            fish_state=fish_state,
            custom_name=custom_name,
            gps_accuracy_m=gps_accuracy_m,
            gps_timestamp=gps_timestamp,
            gps_is_mocked=bool(gps_is_mocked),
            gps_source=gps_source,
            area_selection_source=area_selection_source,
        )
    except sqlite3.Error as exc:
        local_path.unlink(missing_ok=True)
        logger.error("Failed to register job in SQLite: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al registrar el trabajo en la base de datos",
        )

    background_tasks.add_task(process_identification_job, job_id)
    return {"job_id": job_id}


def _resolve_owner_id(
    principal: AuthenticatedUser, submitted_user_id: Optional[str]
) -> str:
    """
    Decide which user a capture belongs to.

    A session token always wins. A machine principal must supply a ``user_id``
    that exists, which prevents attributing captures to arbitrary strings.

    Args:
        principal: Authenticated caller.
        submitted_user_id: ``user_id`` form field, if provided.

    Returns:
        The user id to store on the job.

    Raises:
        HTTPException 400: Machine caller omitted ``user_id``.
        HTTPException 403: Machine caller referenced an unknown user.
    """
    if not principal.is_machine:
        if submitted_user_id and submitted_user_id != principal.user_id:
            logger.warning(
                "Ignoring client-supplied user_id %s; using token subject %s",
                submitted_user_id,
                principal.user_id,
            )
        return principal.user_id

    if not submitted_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user_id es obligatorio cuando se usa el secreto de cliente",
        )

    with db_session() as conn:
        if not _user_exists(conn, submitted_user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="user_id desconocido para la atribución de la captura",
            )
    return submitted_user_id


def _insert_job_row(
    *,
    job_id: str,
    owner_id: str,
    relative_name: str,
    media_type: str,
    original_filename: str,
    content_type: str,
    area_code: Optional[str],
    area_name: Optional[str],
    latitude: float,
    longitude: float,
    species_slug: str,
    notes: Optional[str],
    weather: Optional[str],
    bite: Optional[str],
    size_cm: Optional[float],
    fish_state: Optional[str],
    custom_name: Optional[str],
    gps_accuracy_m: Optional[float],
    gps_timestamp: Optional[str],
    gps_is_mocked: bool,
    gps_source: Optional[str],
    area_selection_source: Optional[str],
) -> None:
    """
    Insert the job row inside a committed transaction.

    Args are the validated capture metadata; see :func:`upload_job_video`.

    Raises:
        sqlite3.Error: Propagated so the caller can clean up the stored file.
    """
    now_str = datetime.now(timezone.utc).isoformat()
    with db_session(commit=True) as conn:
        conn.execute(
            """INSERT INTO identification_jobs (
                id, user_id, status, raw_video_filename, area_code, area_name,
                latitude, longitude, species_slug, notes,
                weather, bite, size_cm, fish_state, custom_name,
                created_at, media_type, original_filename, content_type,
                raw_media_filename, gps_accuracy_m, gps_timestamp,
                gps_is_mocked, gps_source, area_selection_source
            ) VALUES (?, ?, 'uploaded', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job_id,
                owner_id,
                relative_name,
                normalize_area_code(area_code),
                area_name,
                latitude,
                longitude,
                species_slug,
                notes,
                weather,
                bite,
                size_cm,
                fish_state,
                custom_name,
                now_str,
                media_type,
                original_filename,
                content_type,
                relative_name,
                gps_accuracy_m,
                gps_timestamp,
                1 if gps_is_mocked else 0,
                gps_source or "current",
                area_selection_source or "user_selected",
            ),
        )


@router.post("/{job_id}/process", status_code=status.HTTP_202_ACCEPTED)
async def process_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    principal: Principal,
    force: bool = Query(default=False),
) -> dict[str, str]:
    """
    Queue an existing job for (re)processing.

    Args:
        job_id: Job to process.
        background_tasks: FastAPI background task registry.
        principal: Authenticated caller; must own the job or be elevated.
        force: Reprocess even when already processing or completed. Restricted to
            elevated roles because it is computationally expensive.

    Returns:
        Dict with the job id and its resulting status.

    Raises:
        HTTPException 403: Caller does not own the job, or requested ``force``
            without an elevated role.
        HTTPException 404: Job does not exist.
    """
    requester_id = _require_session_user(principal)

    with db_session() as conn:
        row = conn.execute(
            "SELECT id, status, user_id FROM identification_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Job {job_id} not found"
            )
        requester_role = _authorize_job_access(conn, row, requester_id)

    if force and requester_role not in ELEVATED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo Researchers y Admins pueden forzar el reprocesamiento",
        )

    current_status = row["status"]
    if current_status in ("processing", "completed") and not force:
        logger.info("Job %s already in status '%s'", job_id, current_status)
        return {
            "job_id": job_id,
            "status": current_status,
            "message": f"Job is already {current_status}",
        }

    logger.info("Scheduling job %s for background processing (force=%s)", job_id, force)
    # Drop any cached document so a forced rerun cannot serve the previous result.
    invalidate_job_result(job_id)
    background_tasks.add_task(process_identification_job, job_id, force=force)
    return {"job_id": job_id, "status": "processing_started"}


@router.get("/{job_id}")
async def get_job(job_id: str, principal: Principal) -> dict[str, Any]:
    """
    Retrieve job metadata.

    Args:
        job_id: Job to read.
        principal: Authenticated caller; must own the job or be elevated.

    Returns:
        The job row, with internal bookkeeping fields removed for
        non-elevated callers.

    Raises:
        HTTPException 403: Caller does not own the job.
        HTTPException 404: Job does not exist.
    """
    requester_id = _require_session_user(principal)

    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM identification_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Job {job_id} not found"
            )
        requester_role = _authorize_job_access(conn, row, requester_id)

    job_data = dict(row)
    if requester_role in ELEVATED_ROLES:
        return job_data
    return _strip_internal_keys(job_data)


@router.get("/{job_id}/result")
async def get_job_result(job_id: str, principal: Principal) -> dict[str, Any]:
    """
    Retrieve the sighting document produced by a completed job.

    Completed results are cached briefly (see ``FISHDEX_RESULT_CACHE_TTL_SECONDS``)
    because the mobile client polls this endpoint every two seconds while the
    result screen is open. Only terminal results are cached, and the entry is
    invalidated whenever the job is re-processed.

    Args:
        job_id: Job to read.
        principal: Authenticated caller; must own the job or be elevated.

    Returns:
        The sighting payload, including the previous catch and the matched
        reference catch when linked. GPS history is redacted for fishermen.

    Raises:
        HTTPException 403: Caller does not own the job.
        HTTPException 404: Job, result id or sighting row missing.
    """
    requester_id = _require_session_user(principal)
    cache = get_result_cache()
    cache_key = f"job_result:{job_id}"

    cached = cache.get(cache_key)
    if cached is not None:
        # Authorisation is re-evaluated on every request; only the document body
        # is cached, never the decision about who may see it.
        with db_session() as conn:
            job_row = conn.execute(
                "SELECT id, user_id FROM identification_jobs WHERE id = ?", (job_id,)
            ).fetchone()
            if job_row is None:
                cache.invalidate(cache_key)
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Job {job_id} not found",
                )
            requester_role = _authorize_job_access(conn, job_row, requester_id)
        if requester_role in ELEVATED_ROLES:
            return cached
        return _strip_sensitive_for_fisherman(cached)

    with db_session() as conn:
        job_row = conn.execute(
            "SELECT * FROM identification_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if job_row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Job {job_id} not found"
            )
        requester_role = _authorize_job_access(conn, job_row, requester_id)

        job_data = dict(job_row)
        job_status = job_data.get("status")

        if job_status == "needs_manual_review":
            return _build_manual_review_payload(job_id, job_data)

        result_sighting_id = job_data.get("result_sighting_id")
        if not result_sighting_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job result sighting ID is missing",
            )

        sighting_row = conn.execute(
            "SELECT * FROM fish_sightings WHERE id = ?", (result_sighting_id,)
        ).fetchone()
        if sighting_row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Sighting result not found"
            )

        sighting_data = _assemble_sighting_result(conn, dict(sighting_row))

    # Only cache terminal states; an in-flight job's document still changes.
    if job_status == "completed":
        cache.set(cache_key, sighting_data)

    if requester_role in ELEVATED_ROLES:
        return sighting_data
    return _strip_sensitive_for_fisherman(sighting_data)


def _build_manual_review_payload(
    job_id: str, job_data: dict[str, Any]
) -> dict[str, Any]:
    """
    Shape the response for a job awaiting manual review.

    Args:
        job_id: Job identifier.
        job_data: Job row as a dict.

    Returns:
        Payload containing the recorded linkage evidence.
    """
    raw = job_data.get("result_json") or job_data.get("linkage_json")
    parsed = _parse_json_column(raw, context=f"job {job_id} result_json")
    linkage = parsed.get("linkage", parsed)
    if not isinstance(linkage, dict):
        linkage = {}
    return {
        "status": "needs_manual_review",
        "job_id": job_id,
        "similarity_reference": linkage.get("similarity_reference"),
        "linkage": linkage,
    }


def _assemble_sighting_result(
    conn: sqlite3.Connection, sighting_data: dict[str, Any]
) -> dict[str, Any]:
    """
    Attach linkage metadata and related catches to a sighting payload.

    Args:
        conn: Open connection.
        sighting_data: Sighting row as a dict.

    Returns:
        The enriched payload.
    """
    linkage = _parse_json_column(
        sighting_data.get("linkage_json"),
        context=f"sighting {sighting_data.get('id')} linkage_json",
    )
    sighting_data["linkage"] = linkage
    sighting_data["similarity_reference"] = linkage.get("similarity_reference")

    previous_id = sighting_data.get("previous_sighting_id")
    sighting_data["previous_catch"] = _fetch_sighting(conn, previous_id)

    reference_id = sighting_data.get("match_reference_sighting_id")
    if reference_id and reference_id != previous_id:
        sighting_data["matched_reference_catch"] = _fetch_sighting(conn, reference_id)
    else:
        sighting_data["matched_reference_catch"] = None

    return sighting_data


def _fetch_sighting(
    conn: sqlite3.Connection, sighting_id: Optional[str]
) -> Optional[dict[str, Any]]:
    """
    Load a sighting by id.

    Args:
        conn: Open connection.
        sighting_id: Identifier, or None.

    Returns:
        The row as a dict, or None when absent.
    """
    if not sighting_id:
        return None
    row = conn.execute(
        "SELECT * FROM fish_sightings WHERE id = ?", (sighting_id,)
    ).fetchone()
    return dict(row) if row is not None else None
