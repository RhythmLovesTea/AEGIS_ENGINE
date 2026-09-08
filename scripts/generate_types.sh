#!/usr/bin/env bash
# ==============================================================================
# AEGIS-Marine: OpenAPI TypeScript Type Generation Script (TASK-040)
# Generates end-to-end typed TypeScript contracts from FastAPI OpenAPI schema.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
FRONTEND_DIR="${ROOT_DIR}/frontend"
OUTPUT_FILE="${FRONTEND_DIR}/src/types/api.ts"
TEMP_SCHEMA="$(mktemp /tmp/aegis_openapi_XXXXXX.json)"

cleanup() {
    rm -f "${TEMP_SCHEMA}"
}
trap cleanup EXIT

echo "🌊 [AEGIS-Marine] Generating OpenAPI TypeScript definitions..."

# Step 1: Obtain OpenAPI JSON schema
API_URL="${API_URL:-http://localhost:8000/openapi.json}"

if curl -s -f -m 2 "${API_URL}" > "${TEMP_SCHEMA}" 2>/dev/null; then
    echo "📡 Retrieved OpenAPI schema from live API server (${API_URL})."
else
    echo "🐍 Live API server not detected. Extracting schema via FastAPI application..."
    if [[ -f "${ROOT_DIR}/.venv/bin/python3" ]]; then
        PYTHON_BIN="${ROOT_DIR}/.venv/bin/python3"
    else
        PYTHON_BIN="python3"
    fi
    "${PYTHON_BIN}" -c "import json; from backend.app.main import create_app; print(json.dumps(create_app().openapi(), indent=2))" > "${TEMP_SCHEMA}"
    echo "✅ Schema successfully extracted from FastAPI application factory."
fi

# Step 2: Run openapi-typescript
echo "⚙️  Running openapi-typescript to generate ${OUTPUT_FILE}..."
mkdir -p "$(dirname "${OUTPUT_FILE}")"

(cd "${FRONTEND_DIR}" && npx openapi-typescript "${TEMP_SCHEMA}" -o "${OUTPUT_FILE}")

echo "✨ TypeScript contracts successfully generated at: ${OUTPUT_FILE}"
ls -lh "${OUTPUT_FILE}"
