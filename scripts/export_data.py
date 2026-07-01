#!/usr/bin/env python3
"""
export_data.py - Exportador de datos de avistamientos de peces desde Appwrite Storage.

Descarga imagenes/videos asociados a documentos de la coleccion fish_sightings
y los organiza por fish_id en una estructura de directorios local.

Estructura de salida:
    data/raw/{fish_id}/image_001.jpg
    data/raw/{fish_id}/image_002.jpg
"""

import os
import sys
import json
import argparse
import logging
from pathlib import Path
from typing import Optional

import httpx

# --- Configuracion de logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# --- Constantes de Appwrite ---
DATABASE_ID = "fishdex_db"
COLLECTION_ID = "fish_sightings"
BUCKET_ID = "fish_media"
LIST_LIMIT = 100  # Documentos por pagina


def get_env_config() -> dict:
    """Obtiene la configuracion de Appwrite desde variables de entorno."""
    endpoint = os.environ.get("APPWRITE_ENDPOINT")
    project_id = os.environ.get("APPWRITE_PROJECT_ID")
    api_key = os.environ.get("APPWRITE_API_KEY")

    if not all([endpoint, project_id, api_key]):
        logger.error(
            "Faltan variables de entorno requeridas: "
            "APPWRITE_ENDPOINT, APPWRITE_PROJECT_ID, APPWRITE_API_KEY"
        )
        sys.exit(1)

    return {
        "endpoint": endpoint.rstrip("/"),
        "project_id": project_id,
        "api_key": api_key,
    }


def build_headers(config: dict) -> dict:
    """Construye los headers para las peticiones a la API de Appwrite."""
    return {
        "X-Appwrite-Project": config["project_id"],
        "X-Appwrite-Key": config["api_key"],
        "Content-Type": "application/json",
    }


def list_all_documents(client: httpx.Client, config: dict) -> list:
    """
    Obtiene todos los documentos de la coleccion fish_sightings.
    Maneja la paginacion automaticamente.
    """
    headers = build_headers(config)
    documents = []
    offset = 0

    logger.info("Obteniendo documentos de la coleccion '%s'...", COLLECTION_ID)

    while True:
        url = (
            f"{config['endpoint']}/databases/{DATABASE_ID}"
            f"/collections/{COLLECTION_ID}/documents"
        )
        params = {
            "limit": LIST_LIMIT,
            "offset": offset,
        }

        try:
            response = client.get(url, headers=headers, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error("Error al listar documentos (HTTP %d): %s", e.response.status_code, e.response.text)
            sys.exit(1)
        except httpx.RequestError as e:
            logger.error("Error de conexion al listar documentos: %s", e)
            sys.exit(1)

        data = response.json()
        batch = data.get("documents", [])
        documents.extend(batch)

        total = data.get("total", 0)
        logger.info("  Descargados %d/%d documentos", len(documents), total)

        # Si ya obtuvimos todos los documentos, salir del loop
        if len(documents) >= total or len(batch) < LIST_LIMIT:
            break

        offset += LIST_LIMIT

    logger.info("Total de documentos obtenidos: %d", len(documents))
    return documents


def download_file(
    client: httpx.Client,
    config: dict,
    file_id: str,
    output_path: Path,
) -> bool:
    """
    Descarga un archivo desde Appwrite Storage y lo guarda en disco.
    Retorna True si fue exitoso, False en caso contrario.
    """
    headers = build_headers(config)
    url = f"{config['endpoint']}/storage/buckets/{BUCKET_ID}/files/{file_id}/view"

    try:
        # Usar streaming para archivos grandes (videos)
        with client.stream("GET", url, headers=headers) as response:
            response.raise_for_status()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as f:
                for chunk in response.iter_bytes(chunk_size=8192):
                    f.write(chunk)
        return True
    except httpx.HTTPStatusError as e:
        logger.warning(
            "Error al descargar archivo '%s' (HTTP %d): %s",
            file_id, e.response.status_code, e.response.text
        )
        return False
    except httpx.RequestError as e:
        logger.warning("Error de conexion al descargar '%s': %s", file_id, e)
        return False


def determine_extension(file_id: str, mime_type: Optional[str] = None) -> str:
    """Determina la extension del archivo basandose en el tipo MIME."""
    mime_map = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "video/mp4": ".mp4",
        "video/quicktime": ".mov",
    }
    if mime_type and mime_type in mime_map:
        return mime_map[mime_type]
    # Default a .jpg para imagenes
    return ".jpg"


def export_sightings(output_dir: Path, config: dict) -> None:
    """
    Proceso principal de exportacion:
    1. Lista todos los avistamientos
    2. Descarga las imagenes/videos asociados
    3. Organiza por fish_id
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Crear cliente HTTP con timeout generoso para archivos grandes
    with httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
        # Paso 1: Obtener todos los documentos de avistamientos
        documents = list_all_documents(client, config)

        if not documents:
            logger.warning("No se encontraron documentos de avistamientos.")
            return

        # Paso 2: Descargar archivos organizados por fish_id
        stats = {"total": 0, "descargados": 0, "errores": 0, "omitidos": 0}
        manifest = []  # Registro de todas las descargas

        for doc in documents:
            fish_id = doc.get("fish_id")
            media_files = doc.get("media_files", [])  # Lista de file_ids
            photo_id = doc.get("photo_id")  # Campo alternativo para una sola foto
            mime_type = doc.get("mime_type")

            if not fish_id:
                logger.warning("Documento '%s' sin fish_id, omitiendo.", doc.get("$id"))
                stats["omitidos"] += 1
                continue

            # Recopilar todos los IDs de archivos del documento
            file_ids = []
            if media_files:
                file_ids.extend(media_files)
            elif photo_id:
                file_ids.append(photo_id)
            else:
                logger.debug("Documento '%s' sin archivos multimedia.", doc.get("$id"))
                stats["omitidos"] += 1
                continue

            # Crear directorio para este fish_id
            fish_dir = output_dir / fish_id
            fish_dir.mkdir(parents=True, exist_ok=True)

            # Contar imagenes existentes para numerar secuencialmente
            existing_count = len(list(fish_dir.iterdir()))

            for i, file_id in enumerate(file_ids):
                stats["total"] += 1
                ext = determine_extension(file_id, mime_type)
                image_num = existing_count + i + 1
                filename = f"image_{image_num:03d}{ext}"
                output_path = fish_dir / filename

                # No re-descargar si ya existe
                if output_path.exists():
                    logger.debug("Archivo ya existe: %s", output_path)
                    stats["omitidos"] += 1
                    continue

                logger.info("Descargando: %s -> %s", file_id, output_path)
                success = download_file(client, config, file_id, output_path)

                if success:
                    stats["descargados"] += 1
                    manifest.append({
                        "fish_id": fish_id,
                        "file_id": file_id,
                        "local_path": str(output_path),
                        "document_id": doc.get("$id"),
                    })
                else:
                    stats["errores"] += 1

        # Paso 3: Guardar manifiesto de descargas
        manifest_path = output_dir / "download_manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        # Resumen final
        logger.info("=" * 50)
        logger.info("RESUMEN DE EXPORTACION")
        logger.info("=" * 50)
        logger.info("  Total de archivos procesados: %d", stats["total"])
        logger.info("  Descargados exitosamente:     %d", stats["descargados"])
        logger.info("  Errores de descarga:          %d", stats["errores"])
        logger.info("  Omitidos (ya existentes):     %d", stats["omitidos"])
        logger.info("  Manifiesto guardado en:       %s", manifest_path)
        logger.info("=" * 50)

        # Listar clases encontradas
        class_dirs = [d for d in output_dir.iterdir() if d.is_dir()]
        logger.info("Clases de peces encontradas: %d", len(class_dirs))
        for class_dir in sorted(class_dirs):
            count = len(list(class_dir.iterdir()))
            logger.info("  %s: %d archivos", class_dir.name, count)


def parse_args() -> argparse.Namespace:
    """Parsea los argumentos de linea de comandos."""
    parser = argparse.ArgumentParser(
        description="Exporta imagenes de avistamientos de peces desde Appwrite Storage.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Variables de entorno requeridas:
  APPWRITE_ENDPOINT     URL del endpoint de Appwrite (ej: https://cloud.appwrite.io/v1)
  APPWRITE_PROJECT_ID   ID del proyecto en Appwrite
  APPWRITE_API_KEY      API Key con permisos de lectura en Storage y Database

Ejemplo de uso:
  export APPWRITE_ENDPOINT="https://cloud.appwrite.io/v1"
  export APPWRITE_PROJECT_ID="mi_proyecto"
  export APPWRITE_API_KEY="mi_api_key"
  python export_data.py --output-dir ./data/raw
        """,
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/raw",
        help="Directorio de salida para las imagenes (default: data/raw)",
    )
    parser.add_argument(
        "--database-id",
        type=str,
        default=DATABASE_ID,
        help=f"ID de la base de datos en Appwrite (default: {DATABASE_ID})",
    )
    parser.add_argument(
        "--collection-id",
        type=str,
        default=COLLECTION_ID,
        help=f"ID de la coleccion de avistamientos (default: {COLLECTION_ID})",
    )
    parser.add_argument(
        "--bucket-id",
        type=str,
        default=BUCKET_ID,
        help=f"ID del bucket de almacenamiento (default: {BUCKET_ID})",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Habilitar logging detallado (DEBUG)",
    )
    return parser.parse_args()


def main() -> None:
    """Punto de entrada principal del script."""
    args = parse_args()

    # Configurar nivel de logging
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Actualizar constantes globales si se proporcionaron argumentos
    global DATABASE_ID, COLLECTION_ID, BUCKET_ID
    DATABASE_ID = args.database_id
    COLLECTION_ID = args.collection_id
    BUCKET_ID = args.bucket_id

    # Obtener configuracion de Appwrite
    config = get_env_config()

    logger.info("Iniciando exportacion de datos de FishDex")
    logger.info("  Endpoint:   %s", config["endpoint"])
    logger.info("  Proyecto:   %s", config["project_id"])
    logger.info("  Base datos: %s", DATABASE_ID)
    logger.info("  Coleccion:  %s", COLLECTION_ID)
    logger.info("  Bucket:     %s", BUCKET_ID)
    logger.info("  Salida:     %s", args.output_dir)

    # Ejecutar exportacion
    output_path = Path(args.output_dir)
    export_sightings(output_path, config)

    logger.info("Exportacion completada.")


if __name__ == "__main__":
    main()
