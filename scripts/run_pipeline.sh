#!/usr/bin/env bash
# =============================================================================
# run_pipeline.sh - Pipeline maestro de reentrenamiento del modelo FishDex
#
# Ejecuta el pipeline completo en orden:
#   1. Exportar datos desde Appwrite
#   2. Preprocesar imagenes
#   3. Entrenar modelo
#   4. Evaluar modelo
#   5. Desplegar (solo si la evaluacion es aprobada)
#
# Uso:
#   ./run_pipeline.sh
#   ./run_pipeline.sh --skip-export        # Omitir descarga de datos
#   ./run_pipeline.sh --skip-deploy        # No desplegar automaticamente
#   ./run_pipeline.sh --epochs 100         # Pasar argumentos al entrenamiento
#
# Variables de entorno requeridas:
#   APPWRITE_ENDPOINT, APPWRITE_PROJECT_ID, APPWRITE_API_KEY
# =============================================================================

# Detener ejecucion inmediatamente si cualquier comando falla
set -e

# --- Colores para la salida ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# --- Configuracion ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DATA_RAW="${SCRIPT_DIR}/data/raw"
DATA_PROCESSED="${SCRIPT_DIR}/data/processed"
MODELS_DIR="${SCRIPT_DIR}/models"
LOG_FILE="${SCRIPT_DIR}/pipeline_$(date +%Y%m%d_%H%M%S).log"

# --- Valores por defecto ---
SKIP_EXPORT=false
SKIP_PREPROCESS=false
SKIP_TRAIN=false
SKIP_EVAL=false
SKIP_DEPLOY=false
EPOCHS=50
BATCH_SIZE=32
LR=0.001
MIN_ACCURACY=85.0

# --- Parseo de argumentos ---
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-export)
            SKIP_EXPORT=true
            shift
            ;;
        --skip-preprocess)
            SKIP_PREPROCESS=true
            shift
            ;;
        --skip-train)
            SKIP_TRAIN=true
            shift
            ;;
        --skip-eval)
            SKIP_EVAL=true
            shift
            ;;
        --skip-deploy)
            SKIP_DEPLOY=true
            shift
            ;;
        --epochs)
            EPOCHS="$2"
            shift 2
            ;;
        --batch-size)
            BATCH_SIZE="$2"
            shift 2
            ;;
        --lr)
            LR="$2"
            shift 2
            ;;
        --min-accuracy)
            MIN_ACCURACY="$2"
            shift 2
            ;;
        --help)
            echo "Uso: $0 [opciones]"
            echo ""
            echo "Opciones:"
            echo "  --skip-export       Omitir paso de exportacion de datos"
            echo "  --skip-preprocess   Omitir paso de preprocesamiento"
            echo "  --skip-train        Omitir paso de entrenamiento"
            echo "  --skip-eval         Omitir paso de evaluacion"
            echo "  --skip-deploy       Omitir paso de despliegue"
            echo "  --epochs N          Numero de epocas (default: 50)"
            echo "  --batch-size N      Tamano de batch (default: 32)"
            echo "  --lr FLOAT          Learning rate (default: 0.001)"
            echo "  --min-accuracy N    Umbral minimo de accuracy (default: 85.0)"
            echo "  --help              Mostrar esta ayuda"
            exit 0
            ;;
        *)
            echo -e "${RED}Argumento desconocido: $1${NC}"
            exit 1
            ;;
    esac
done

# --- Funciones de utilidad ---

print_header() {
    echo ""
    echo -e "${BOLD}${CYAN}============================================================${NC}"
    echo -e "${BOLD}${CYAN}  $1${NC}"
    echo -e "${BOLD}${CYAN}============================================================${NC}"
    echo ""
}

print_step() {
    echo -e "${BLUE}[PASO $1/$2]${NC} ${BOLD}$3${NC}"
}

print_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

print_skip() {
    echo -e "${YELLOW}[SKIP]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

get_elapsed() {
    local start=$1
    local end=$(date +%s)
    local elapsed=$((end - start))
    local minutes=$((elapsed / 60))
    local seconds=$((elapsed % 60))
    echo "${minutes}m ${seconds}s"
}

# --- Inicio del pipeline ---

PIPELINE_START=$(date +%s)

print_header "PIPELINE DE REENTRENAMIENTO - FishDex"

echo "  Fecha:          $(date '+%Y-%m-%d %H:%M:%S')"
echo "  Directorio:     ${SCRIPT_DIR}"
echo "  Log:            ${LOG_FILE}"
echo "  Epochs:         ${EPOCHS}"
echo "  Batch size:     ${BATCH_SIZE}"
echo "  Learning rate:  ${LR}"
echo "  Min accuracy:   ${MIN_ACCURACY}%"
echo ""

# Redirigir tambien al archivo de log
exec > >(tee -a "$LOG_FILE") 2>&1

# --- Paso 1: Exportar datos ---

STEP_START=$(date +%s)
print_step 1 5 "Exportacion de datos desde Appwrite"

if [ "$SKIP_EXPORT" = true ]; then
    print_skip "Exportacion omitida (--skip-export)"
else
    # Verificar variables de entorno
    if [ -z "${APPWRITE_ENDPOINT:-}" ] || [ -z "${APPWRITE_PROJECT_ID:-}" ] || [ -z "${APPWRITE_API_KEY:-}" ]; then
        print_error "Variables de entorno de Appwrite no configuradas"
        print_error "Requeridas: APPWRITE_ENDPOINT, APPWRITE_PROJECT_ID, APPWRITE_API_KEY"
        exit 1
    fi

    python3 "${SCRIPT_DIR}/export_data.py" \
        --output-dir "$DATA_RAW"

    print_success "Datos exportados en $(get_elapsed $STEP_START)"
fi

echo ""

# --- Paso 2: Preprocesamiento ---

STEP_START=$(date +%s)
print_step 2 5 "Preprocesamiento de imagenes"

if [ "$SKIP_PREPROCESS" = true ]; then
    print_skip "Preprocesamiento omitido (--skip-preprocess)"
else
    # Verificar que hay datos crudos
    if [ ! -d "$DATA_RAW" ] || [ -z "$(ls -A "$DATA_RAW" 2>/dev/null)" ]; then
        print_error "No hay datos en ${DATA_RAW}/"
        print_error "Ejecuta primero el paso de exportacion."
        exit 1
    fi

    python3 "${SCRIPT_DIR}/preprocess.py" \
        --input-dir "$DATA_RAW" \
        --output-dir "$DATA_PROCESSED" \
        --num-augmented 3 \
        --seed 42

    print_success "Preprocesamiento completado en $(get_elapsed $STEP_START)"
fi

echo ""

# --- Paso 3: Entrenamiento ---

STEP_START=$(date +%s)
print_step 3 5 "Entrenamiento del modelo"

if [ "$SKIP_TRAIN" = true ]; then
    print_skip "Entrenamiento omitido (--skip-train)"
else
    # Verificar que hay datos procesados
    if [ ! -f "${DATA_PROCESSED}/metadata.json" ]; then
        print_error "No se encontro metadata.json en ${DATA_PROCESSED}/"
        print_error "Ejecuta primero el paso de preprocesamiento."
        exit 1
    fi

    python3 "${SCRIPT_DIR}/train.py" \
        --data-dir "$DATA_PROCESSED" \
        --models-dir "$MODELS_DIR" \
        --epochs "$EPOCHS" \
        --batch-size "$BATCH_SIZE" \
        --lr "$LR" \
        --freeze-epochs 5 \
        --patience 10

    print_success "Entrenamiento completado en $(get_elapsed $STEP_START)"
fi

echo ""

# --- Paso 4: Evaluacion ---

STEP_START=$(date +%s)
print_step 4 5 "Evaluacion del modelo"

if [ "$SKIP_EVAL" = true ]; then
    print_skip "Evaluacion omitida (--skip-eval)"
    EVAL_PASSED=true
else
    # Buscar el modelo mas reciente
    LATEST_MODEL=$(ls -t "${MODELS_DIR}"/fish_model_v*.pt 2>/dev/null | head -1)
    if [ -z "$LATEST_MODEL" ]; then
        print_error "No se encontro ningun modelo entrenado en ${MODELS_DIR}/"
        exit 1
    fi

    echo "  Evaluando modelo: ${LATEST_MODEL}"

    # Ejecutar evaluacion - capturar el codigo de salida
    EVAL_PASSED=false
    if python3 "${SCRIPT_DIR}/evaluate.py" \
        --model-path "$LATEST_MODEL" \
        --data-dir "$DATA_PROCESSED" \
        --models-dir "$MODELS_DIR" \
        --min-accuracy "$MIN_ACCURACY"; then
        EVAL_PASSED=true
        print_success "Evaluacion APROBADA en $(get_elapsed $STEP_START)"
    else
        print_error "Evaluacion RECHAZADA - El modelo no alcanza ${MIN_ACCURACY}% de accuracy"
    fi
fi

echo ""

# --- Paso 5: Despliegue ---

STEP_START=$(date +%s)
print_step 5 5 "Despliegue del modelo"

if [ "$SKIP_DEPLOY" = true ]; then
    print_skip "Despliegue omitido (--skip-deploy)"
elif [ "$EVAL_PASSED" = false ]; then
    print_error "Despliegue cancelado: la evaluacion no fue aprobada"
    print_error "El modelo no sera desplegado hasta que pase el umbral de ${MIN_ACCURACY}%"
else
    bash "${SCRIPT_DIR}/deploy_model.sh"
    print_success "Despliegue completado en $(get_elapsed $STEP_START)"
fi

# --- Resumen final ---

PIPELINE_END=$(date +%s)
TOTAL_TIME=$(get_elapsed $PIPELINE_START)

print_header "PIPELINE COMPLETADO"

echo "  Tiempo total:    ${TOTAL_TIME}"
echo "  Evaluacion:      $([ "$EVAL_PASSED" = true ] && echo -e "${GREEN}APROBADA${NC}" || echo -e "${RED}RECHAZADA${NC}")"
echo "  Despliegue:      $([ "$SKIP_DEPLOY" = true ] && echo "OMITIDO" || ([ "$EVAL_PASSED" = true ] && echo -e "${GREEN}COMPLETADO${NC}" || echo -e "${YELLOW}NO APLICADO${NC}"))"
echo "  Log completo:    ${LOG_FILE}"
echo ""

# Codigo de salida final
if [ "$EVAL_PASSED" = true ]; then
    echo -e "${GREEN}Pipeline ejecutado exitosamente.${NC}"
    exit 0
else
    echo -e "${RED}Pipeline completado con errores (modelo no aprobado).${NC}"
    exit 1
fi
