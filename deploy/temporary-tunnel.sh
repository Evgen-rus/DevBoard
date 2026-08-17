#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-/opt/DevBoard}"
RUNTIME_DIR="${PROJECT_ROOT}/runtime"
STORAGE_DIR="${RUNTIME_DIR}/storage"
AUTH_DIR="${RUNTIME_DIR}/nginx"
AUTH_FILE="${AUTH_DIR}/.htpasswd"
ACCESS_FILE="${RUNTIME_DIR}/access.txt"
NETWORK="devboard-temporary-net"
API_CONTAINER="devboard-api"
WEB_CONTAINER="devboard-web"
TUNNEL_CONTAINER="devboard-tunnel"
API_IMAGE="devboard-api:temporary"
WEB_IMAGE="devboard-web:temporary"

require_file() {
    if [[ ! -f "$1" ]]; then
        echo "Required file is missing: $1" >&2
        exit 1
    fi
}

require_directory() {
    if [[ ! -d "$1" ]]; then
        echo "Required directory is missing: $1" >&2
        exit 1
    fi
}

require_file "${RUNTIME_DIR}/.env"
require_directory "${STORAGE_DIR}"

mkdir -p "${AUTH_DIR}"
chmod 700 "${RUNTIME_DIR}" "${AUTH_DIR}"
chmod 600 "${RUNTIME_DIR}/.env"

if [[ ! -s "${ACCESS_FILE}" ]]; then
    umask 077
    head -c 24 /dev/urandom | base64 | tr -d '\n' > "${ACCESS_FILE}"
    printf '\n' >> "${ACCESS_FILE}"
    echo "Temporary Basic Auth password created in ${ACCESS_FILE}."
fi

password="$(<"${ACCESS_FILE}")"
printf '%s\n' "${password}" | docker run --rm -i httpd:2.4-alpine \
    htpasswd -i -nB devboard > "${AUTH_FILE}"
unset password
chmod 644 "${AUTH_FILE}"
chmod 600 "${ACCESS_FILE}"

docker network inspect "${NETWORK}" >/dev/null 2>&1 \
    || docker network create "${NETWORK}" >/dev/null

docker build --tag "${API_IMAGE}" "${PROJECT_ROOT}/backend"
docker build --tag "${WEB_IMAGE}" "${PROJECT_ROOT}/frontend"

docker rm --force "${TUNNEL_CONTAINER}" "${WEB_CONTAINER}" "${API_CONTAINER}" \
    >/dev/null 2>&1 || true

docker run --detach \
    --name "${API_CONTAINER}" \
    --network "${NETWORK}" \
    --restart unless-stopped \
    --env-file "${RUNTIME_DIR}/.env" \
    --env STORAGE_DIR=/data/storage \
    --volume "${STORAGE_DIR}:/data/storage" \
    --security-opt no-new-privileges \
    "${API_IMAGE}" >/dev/null

api_ready=false
for _ in $(seq 1 30); do
    if docker exec "${API_CONTAINER}" python -c \
        'import json, urllib.request; data=json.load(urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=2)); assert data["ok"] and data["github"] and data["storage"]' \
        >/dev/null 2>&1; then
        api_ready=true
        break
    fi
    if [[ "$(docker inspect --format '{{.State.Running}}' "${API_CONTAINER}" 2>/dev/null || true)" != "true" ]]; then
        break
    fi
    sleep 1
done

if [[ "${api_ready}" != "true" ]]; then
    echo "API did not pass health-check. Inspect: docker logs --tail 100 ${API_CONTAINER}" >&2
    exit 1
fi

docker run --detach \
    --name "${WEB_CONTAINER}" \
    --network "${NETWORK}" \
    --restart unless-stopped \
    --volume "${PROJECT_ROOT}/deploy/nginx/default.conf:/etc/nginx/conf.d/default.conf:ro" \
    --volume "${AUTH_FILE}:/etc/nginx/auth/.htpasswd:ro" \
    --security-opt no-new-privileges \
    "${WEB_IMAGE}" >/dev/null

if ! docker exec "${WEB_CONTAINER}" nginx -t >/dev/null 2>&1; then
    echo "Nginx configuration is invalid. Inspect: docker logs --tail 100 ${WEB_CONTAINER}" >&2
    exit 1
fi

docker run --detach \
    --name "${TUNNEL_CONTAINER}" \
    --network "${NETWORK}" \
    --restart unless-stopped \
    --security-opt no-new-privileges \
    cloudflare/cloudflared:latest tunnel --no-autoupdate \
    --url "http://${WEB_CONTAINER}:80" >/dev/null

url=""
for _ in $(seq 1 30); do
    url="$(docker logs "${TUNNEL_CONTAINER}" 2>&1 \
        | grep -Eo 'https://[-a-z0-9]+\.trycloudflare\.com' | tail -n 1 || true)"
    if [[ -n "${url}" ]]; then
        break
    fi
    sleep 1
done

if [[ -z "${url}" ]]; then
    echo "Containers started, but the Cloudflare URL is not available yet." >&2
    echo "Inspect: docker logs ${TUNNEL_CONTAINER}" >&2
    exit 1
fi

for container in "${API_CONTAINER}" "${WEB_CONTAINER}" "${TUNNEL_CONTAINER}"; do
    if [[ "$(docker inspect --format '{{.State.Running}}' "${container}" 2>/dev/null || true)" != "true" ]]; then
        echo "Container ${container} is not running. Inspect its logs." >&2
        exit 1
    fi
done

echo
echo "Temporary HTTPS URL: ${url}"
echo "Basic Auth login: devboard"
echo "Basic Auth password is stored only in ${ACCESS_FILE}"
