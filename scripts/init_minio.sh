#!/usr/bin/env bash
# ==============================================================================
# AEGIS-Marine — MinIO Local Bucket Initialization Utility
# ==============================================================================
set -euo pipefail

MINIO_ENDPOINT="${MINIO_ENDPOINT:-http://localhost:9000}"
MINIO_ROOT_USER="${MINIO_ROOT_USER:-aegis_minio_admin}"
MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:-aegis_minio_secret}"
MINIO_BUCKET="${MINIO_BUCKET:-aegis-storage}"

echo "======================================================================"
echo "AEGIS-Marine: Initializing MinIO Object Storage"
echo "Endpoint: ${MINIO_ENDPOINT}"
echo "Bucket  : ${MINIO_BUCKET}"
echo "======================================================================"

if command -v mc >/dev/null 2>&1; then
    echo "Configuring MinIO client (mc) alias 'aegis-local'..."
    mc alias set aegis-local "${MINIO_ENDPOINT}" "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}"

    echo "Ensuring bucket '${MINIO_BUCKET}' exists..."
    mc mb --ignore-existing "aegis-local/${MINIO_BUCKET}"

    echo "Configuring public download access for 'public/' folder..."
    mc anonymous set download "aegis-local/${MINIO_BUCKET}/public" || true

    echo "✅ MinIO bucket '${MINIO_BUCKET}' initialized successfully via mc."
else
    echo "Note: 'mc' CLI not found on host. Checking endpoint reachability via curl..."
    if curl -s -f "${MINIO_ENDPOINT}/minio/health/live" >/dev/null 2>&1; then
        echo "✅ MinIO service is alive at ${MINIO_ENDPOINT}."
        echo "When running via Docker Compose, 'minio-init' container creates '${MINIO_BUCKET}' automatically."
    else
        echo "ℹ️  MinIO is not currently running locally on port 9000."
        echo "Run: docker compose -f docker/docker-compose.yml up -d minio minio-init"
    fi
fi
