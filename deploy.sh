#!/usr/bin/env bash
# Server-side deploy script. Run on 192.168.1.252 (amd5950x).
# Expects this directory to contain: docker-compose.yml, .env
# Creates ./logs/ if absent (mounted into the container for persistent logs).

set -euo pipefail

# Resolve script directory, then cd there so relative paths work.
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

REGISTRY="192.168.1.252:15000"
IMAGE="${REGISTRY}/vidistill:latest"
COMPOSE_FILE="docker-compose.yml"

# --- Pre-flight checks ---
if [ ! -f "$COMPOSE_FILE" ]; then
  echo "[FAIL] $COMPOSE_FILE not found in $SCRIPT_DIR"
  exit 1
fi
if [ ! -f ".env" ]; then
  echo "[FAIL] .env not found in $SCRIPT_DIR"
  echo "       Create one containing: DASHSCOPE_API_KEY=sk-..."
  exit 1
fi

# Ensure logs directory exists for the bind mount.
mkdir -p logs

echo
echo "============================================================"
echo "  Pulling latest image: $IMAGE"
echo "============================================================"
docker pull "$IMAGE"

echo
echo "============================================================"
echo "  Restarting vidistill (force-recreate)"
echo "============================================================"
docker compose -f "$COMPOSE_FILE" up -d --force-recreate

echo
echo "============================================================"
echo "  Pruning old dangling images"
echo "============================================================"
docker image prune -f

echo
echo "============================================================"
echo "  Container status"
echo "============================================================"
docker compose -f "$COMPOSE_FILE" ps

echo
echo "============================================================"
echo "  Recent uvicorn output (last 20 lines)"
echo "============================================================"
docker compose -f "$COMPOSE_FILE" logs --tail=20 vidistill || true

echo
echo "============================================================"
echo "  Deploy complete."
echo "  Web:  http://$(hostname -I | awk '{print $1}'):8000"
echo "  Logs: tail -f $SCRIPT_DIR/logs/vidistill.log"
echo "============================================================"
