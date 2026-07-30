# =============================================================================
# FishDex AI Server - Dockerfile
# FastAPI service for fish identification (YOLOv8 OBB + FishEncoder ReID)
# =============================================================================
# Two stages so the build toolchain and pip cache never reach the runtime image.
# =============================================================================

# ── Stage 1: build the dependency tree ──────────────────────────────────────
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Build-only toolchain, discarded with this stage.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
# Install into a relocatable prefix that the runtime stage copies wholesale.
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip setuptools wheel \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt


# ── Stage 2: runtime ────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Runtime-only system libraries for OpenCV and video decoding.
# libgl1-mesa-glx was replaced by libgl1 in Debian 12 (bookworm).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender1 \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Keep native BLAS from oversubscribing cores; the app manages its own
    # thread budget for inference.
    OMP_NUM_THREADS=2 \
    MKL_NUM_THREADS=2

COPY --from=builder /opt/venv /opt/venv

# SECURITY: run as an unprivileged user. A container escape or an RCE in a
# dependency would otherwise land with uid 0 on the mounted data volume.
RUN groupadd --gid 10001 fishdex \
    && useradd --uid 10001 --gid fishdex --create-home --shell /usr/sbin/nologin fishdex

WORKDIR /app

# Directories for model weights and runtime data (bind-mounted in compose).
#   models/detector/ → YOLO OBB .pt
#   models/reid/     → FishEncoder .pt
#   data/            → SQLite, embeddings cache, stored frames
RUN mkdir -p /app/models/detector /app/models/reid /app/data \
    && chown -R fishdex:fishdex /app

COPY --chown=fishdex:fishdex app/ ./app/

USER fishdex

EXPOSE 8000

# Container-level healthcheck. Compose overrides this, but keeping it here means
# `docker run` also gets a health signal.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=5).status == 200 else sys.exit(1)"

# No --reload in production: the reloader watches the filesystem, doubles memory
# by keeping a supervisor process, and reloads on any volume write.
# Single worker by design — the models are loaded once per process and each copy
# costs hundreds of MB; scale out with replicas, not workers.
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*", \
     "--timeout-keep-alive", "65", \
     "--no-server-header"]
