# =============================================================================
# FishDex AI Server - Dockerfile
# Servidor FastAPI para identificación de peces con modelo PyTorch
# =============================================================================

FROM python:3.11-slim

# Instalar dependencias del sistema para OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar requirements e instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código de la aplicación
COPY app/ ./app/

# Crear estructura de directorios para modelos y datos (se montan como volúmenes)
# models/detector/ → YOLO OBB .pt
# models/reid/     → FishEncoder .pt
# data/            → caché de embeddings + frames del servidor
RUN mkdir -p /app/models/detector /app/models/reid /app/data

# Puerto de la aplicación
EXPOSE 8000

# Ejecutar con uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
