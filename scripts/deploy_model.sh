#!/usr/bin/env bash
# =============================================================================
# deploy_model.sh - Script de despliegue del modelo de identificacion de peces
#
# Verifica que la evaluacion haya sido aprobada, copia el modelo al servidor AI,
# reinicia el contenedor y verifica que todo funcione correctamente.
#
# Uso:
#   ./deploy_model.sh [--model-path models/fish_model_v1.pt] [--eval-report models/eval_report_v1.json]
#
# Variables de entorno requeridas:
#   APPWRITE_ENDPOINT    - URL del endpoint de Appwrite
#   APPWRITE_PROJECT_ID  - ID del proyecto
#   APPWRITE_API_KEY     - API Key con permisos de escritura
# =============================================================================

set -euo pipefail

# --- Colores para la salida ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # Sin color

# --- Configuracion por defecto ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
MODELS_DIR="${PROJECT_DIR}/models"
AI_SERVER_DIR="${PROJECT_DIR}/ai-server/model"
HEALTH_ENDPOINT="http://localhost:8080/health"
HEALTH_TIMEOUT=30
DOCKER_SERVICE="ai-server"
APPWRITE_DATABASE_ID="fishdex_db"
APPWRITE_COLLECTION_ID="model_versions"

# --- Funciones de utilidad ---

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# --- Parseo de argumentos ---

MODEL_PATH=""
EVAL_REPORT=""
SKIP_HEALTH_CHECK=false
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --model-path)
            MODEL_PATH="$2"
            shift 2
            ;;
        --eval-report)
            EVAL_REPORT="$2"
            shift 2
            ;;
        --skip-health-check)
            SKIP_HEALTH_CHECK=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --help)
            echo "Uso: $0 [opciones]"
            echo ""
            echo "Opciones:"
            echo "  --model-path PATH       Ruta al modelo .pt (auto-detecta si no se especifica)"
            echo "  --eval-report PATH      Ruta al reporte de evaluacion JSON"
            echo "  --skip-health-check     Omitir verificacion del endpoint de salud"
            echo "  --dry-run               Simular sin ejecutar cambios reales"
            echo "  --help                  Mostrar esta ayuda"
            exit 0
            ;;
        *)
            log_error "Argumento desconocido: $1"
            exit 1
            ;;
    esac
done

# --- Paso 0: Auto-detectar modelo y reporte si no se especificaron ---

if [ -z "$MODEL_PATH" ]; then
    # Buscar el modelo mas reciente
    MODEL_PATH=$(ls -t "${MODELS_DIR}"/fish_model_v*.pt 2>/dev/null | head -1)
    if [ -z "$MODEL_PATH" ]; then
        log_error "No se encontro ningun modelo en ${MODELS_DIR}/"
        exit 1
    fi
    log_info "Modelo auto-detectado: ${MODEL_PATH}"
fi

if [ -z "$EVAL_REPORT" ]; then
    # Buscar el reporte mas reciente
    EVAL_REPORT=$(ls -t "${MODELS_DIR}"/eval_report_v*.json 2>/dev/null | head -1)
    if [ -z "$EVAL_REPORT" ]; then
        log_error "No se encontro ningun reporte de evaluacion en ${MODELS_DIR}/"
        exit 1
    fi
    log_info "Reporte auto-detectado: ${EVAL_REPORT}"
fi

# --- Paso 1: Verificar que la evaluacion fue aprobada ---

log_info "Verificando reporte de evaluacion..."

if [ ! -f "$EVAL_REPORT" ]; then
    log_error "Reporte de evaluacion no encontrado: ${EVAL_REPORT}"
    exit 1
fi

# Leer el estado del reporte usando python para parsear JSON
EVAL_STATUS=$(python3 -c "
import json, sys
with open('${EVAL_REPORT}', 'r') as f:
    report = json.load(f)
threshold = report.get('threshold', {})
print(threshold.get('status', 'UNKNOWN'))
")

EVAL_ACCURACY=$(python3 -c "
import json
with open('${EVAL_REPORT}', 'r') as f:
    report = json.load(f)
print(f\"{report.get('metrics', {}).get('accuracy', 0):.2f}\")
")

MODEL_VERSION=$(python3 -c "
import json
with open('${EVAL_REPORT}', 'r') as f:
    report = json.load(f)
print(report.get('version', 0))
")

if [ "$EVAL_STATUS" != "APROBADO" ]; then
    log_error "La evaluacion NO fue aprobada (status: ${EVAL_STATUS})"
    log_error "Accuracy obtenido: ${EVAL_ACCURACY}%"
    log_error "No se puede desplegar un modelo que no pasa el umbral minimo."
    exit 1
fi

log_success "Evaluacion aprobada - Accuracy: ${EVAL_ACCURACY}%"
log_info "Version del modelo: v${MODEL_VERSION}"

# --- Paso 2: Verificar que el modelo existe ---

if [ ! -f "$MODEL_PATH" ]; then
    log_error "Modelo no encontrado: ${MODEL_PATH}"
    exit 1
fi

MODEL_SIZE=$(du -h "$MODEL_PATH" | cut -f1)
log_info "Tamano del modelo: ${MODEL_SIZE}"

# --- Paso 3: Copiar modelo al directorio del ai-server ---

log_info "Copiando modelo al servidor AI..."

if [ "$DRY_RUN" = true ]; then
    log_warning "[DRY RUN] Se copiaria ${MODEL_PATH} -> ${AI_SERVER_DIR}/"
else
    # Crear directorio si no existe
    mkdir -p "$AI_SERVER_DIR"

    # Hacer backup del modelo anterior si existe
    CURRENT_MODEL="${AI_SERVER_DIR}/fish_model.pt"
    if [ -f "$CURRENT_MODEL" ]; then
        BACKUP_PATH="${AI_SERVER_DIR}/fish_model_backup_$(date +%Y%m%d_%H%M%S).pt"
        cp "$CURRENT_MODEL" "$BACKUP_PATH"
        log_info "Backup del modelo anterior: ${BACKUP_PATH}"
    fi

    # Copiar nuevo modelo
    cp "$MODEL_PATH" "$CURRENT_MODEL"
    log_success "Modelo copiado a: ${CURRENT_MODEL}"

    # Copiar tambien el reporte de evaluacion
    cp "$EVAL_REPORT" "${AI_SERVER_DIR}/eval_report_current.json"

    # Exportar modelo a ONNX para el ClassifierService
    log_info "Exportando modelo a ONNX..."
    if command -v python3 &> /dev/null; then
        python3 "${SCRIPT_DIR}/export_classifier_onnx.py" \
          --checkpoint "$MODEL_PATH" \
          --output-dir "${PROJECT_DIR}/ai-server/models/classifier"
    else
        python "${SCRIPT_DIR}/export_classifier_onnx.py" \
          --checkpoint "$MODEL_PATH" \
          --output-dir "${PROJECT_DIR}/ai-server/models/classifier"
    fi

    # Verificar que los archivos ONNX y labels existen en host
    if [ -f "${PROJECT_DIR}/ai-server/models/classifier/fish_species_v1.onnx" ] && \
       [ -f "${PROJECT_DIR}/ai-server/models/classifier/labels.json" ]; then
        log_success "Modelo ONNX y etiquetas exportados exitosamente en host."
    else
        log_error "Fallo al exportar el modelo a ONNX."
        exit 1
    fi
fi

# --- Paso 4: Reiniciar el contenedor del ai-server ---

log_info "Reiniciando contenedor del servidor AI..."

if [ "$DRY_RUN" = true ]; then
    log_warning "[DRY RUN] Se reiniciaria: docker compose restart ${DOCKER_SERVICE}"
else
    # Verificar que docker compose esta disponible
    if command -v docker &> /dev/null; then
        # Intentar reiniciar el servicio
        if docker compose -f "${PROJECT_DIR}/docker-compose.yml" restart "$DOCKER_SERVICE" 2>/dev/null; then
            log_success "Contenedor reiniciado exitosamente"
        elif docker-compose -f "${PROJECT_DIR}/docker-compose.yml" restart "$DOCKER_SERVICE" 2>/dev/null; then
            log_success "Contenedor reiniciado exitosamente (docker-compose legacy)"
        else
            log_warning "No se pudo reiniciar el contenedor. Verificar manualmente."
            log_warning "Comando: docker compose restart ${DOCKER_SERVICE}"
        fi

        # Verificar que el contenedor ve realmente los modelos exportados
        log_info "Verificando visibilidad del modelo dentro del contenedor..."
        if docker compose -f "${PROJECT_DIR}/docker-compose.yml" exec -T "$DOCKER_SERVICE" python -c "
from pathlib import Path
from app.config import settings
model = Path(settings.classifier_model_path)
labels = Path(settings.classifier_labels_path)
print('Visible:', model, model.exists(), labels, labels.exists())
if not model.exists() or not labels.exists():
    import sys
    sys.exit(1)
" 2>/dev/null; then
            log_success "El contenedor detecta correctamente el nuevo modelo y etiquetas."
        else
            log_warning "El contenedor no pudo validar el nuevo modelo/etiquetas. Verificar rutas."
        fi
    else
        log_warning "Docker no encontrado. Omitiendo reinicio del contenedor y verificacion interna."
    fi
fi

# --- Paso 5: Verificar endpoint de salud ---

if [ "$SKIP_HEALTH_CHECK" = true ]; then
    log_warning "Verificacion de salud omitida (--skip-health-check)"
elif [ "$DRY_RUN" = true ]; then
    log_warning "[DRY RUN] Se verificaria: ${HEALTH_ENDPOINT}"
else
    log_info "Verificando endpoint de salud (timeout: ${HEALTH_TIMEOUT}s)..."

    # Esperar a que el servidor este listo
    HEALTH_OK=false
    for i in $(seq 1 $HEALTH_TIMEOUT); do
        if curl -s -o /dev/null -w "%{http_code}" "$HEALTH_ENDPOINT" | grep -q "200"; then
            HEALTH_OK=true
            break
        fi
        sleep 1
    done

    if [ "$HEALTH_OK" = true ]; then
        log_success "Endpoint de salud respondiendo correctamente"

        # Verificar que el modelo cargado es la version correcta
        LOADED_VERSION=$(curl -s "$HEALTH_ENDPOINT" | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(data.get('model_version', 'unknown'))
" 2>/dev/null || echo "unknown")

        if [ "$LOADED_VERSION" != "unknown" ]; then
            log_info "Version del modelo en servidor: ${LOADED_VERSION}"
        fi
    else
        log_error "El endpoint de salud no responde despues de ${HEALTH_TIMEOUT}s"
        log_error "URL: ${HEALTH_ENDPOINT}"
        log_warning "El modelo fue copiado pero el servidor puede no estar funcionando."
        # No salir con error - el modelo fue desplegado, solo el healthcheck fallo
    fi
fi

# --- Paso 6: Actualizar registro de versiones en Appwrite ---

log_info "Registrando version del modelo en Appwrite..."

if [ "$DRY_RUN" = true ]; then
    log_warning "[DRY RUN] Se registraria version v${MODEL_VERSION} en Appwrite"
else
    # Verificar que las variables de entorno estan configuradas
    if [ -z "${APPWRITE_ENDPOINT:-}" ] || [ -z "${APPWRITE_PROJECT_ID:-}" ] || [ -z "${APPWRITE_API_KEY:-}" ]; then
        log_warning "Variables de Appwrite no configuradas. Omitiendo registro."
    else
        # Crear documento con la informacion de la version
        DEPLOY_TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
        DOCUMENT_DATA=$(python3 -c "
import json
data = {
    'version': ${MODEL_VERSION},
    'accuracy': ${EVAL_ACCURACY},
    'model_path': '${MODEL_PATH}',
    'deployed_at': '${DEPLOY_TIMESTAMP}',
    'status': 'active'
}
print(json.dumps({'data': data}))
")

        # Enviar a Appwrite via API REST
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
            -X POST \
            -H "Content-Type: application/json" \
            -H "X-Appwrite-Project: ${APPWRITE_PROJECT_ID}" \
            -H "X-Appwrite-Key: ${APPWRITE_API_KEY}" \
            -d "$DOCUMENT_DATA" \
            "${APPWRITE_ENDPOINT}/databases/${APPWRITE_DATABASE_ID}/collections/${APPWRITE_COLLECTION_ID}/documents" \
            2>/dev/null || echo "000")

        if [ "$HTTP_CODE" = "201" ] || [ "$HTTP_CODE" = "200" ]; then
            log_success "Version registrada en Appwrite"
        else
            log_warning "No se pudo registrar en Appwrite (HTTP ${HTTP_CODE})"
            log_warning "Esto no afecta el despliegue del modelo."
        fi
    fi
fi

# --- Resumen del despliegue ---

echo ""
echo "============================================================"
echo -e "${GREEN}  RESUMEN DE DESPLIEGUE${NC}"
echo "============================================================"
echo "  Modelo:        fish_model_v${MODEL_VERSION}.pt"
echo "  Accuracy:      ${EVAL_ACCURACY}%"
echo "  Tamano:        ${MODEL_SIZE}"
echo "  Destino:       ${AI_SERVER_DIR}/fish_model.pt"
echo "  Timestamp:     $(date '+%Y-%m-%d %H:%M:%S')"
if [ "$DRY_RUN" = true ]; then
    echo -e "  Estado:        ${YELLOW}DRY RUN (no se aplico)${NC}"
else
    echo -e "  Estado:        ${GREEN}DESPLEGADO${NC}"
fi
echo "============================================================"
echo ""

log_success "Despliegue completado exitosamente."
