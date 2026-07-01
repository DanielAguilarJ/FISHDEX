"""
FishDex AI Server - Aplicación Principal
=========================================
Servidor FastAPI que recibe videos de peces, extrae frames,
ejecuta el modelo de IA y devuelve la identificación del pez.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import identify

# Crear la aplicación FastAPI
app = FastAPI(
    title="FishDex AI Server",
    description="Servidor de identificación de peces por IA para la app FishDex",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configurar CORS para permitir requests desde la app Flutter
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, restringir a dominios específicos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrar routers
app.include_router(identify.router, prefix="/api/v1", tags=["Identificación"])


@app.get("/health", tags=["Sistema"])
async def health_check():
    """
    Endpoint de health check.
    Usado por Docker y load balancers para verificar que el servicio está activo.
    """
    return {
        "status": "healthy",
        "service": "fishdex-ai-server",
        "version": "1.0.0",
        "model_loaded": True,  # TODO: verificar que el modelo realmente está cargado
    }


@app.get("/", tags=["Sistema"])
async def root():
    """Endpoint raíz con información básica del servicio."""
    return {
        "service": "FishDex AI Server",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }
