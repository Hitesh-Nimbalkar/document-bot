#!/bin/bash
set -e

IMAGE_NAME="brain-ui"
CONTAINER_NAME="brain-ui-local"
PORT=3000

# ========== Build Phase ==========
echo "🔹 Step 1: Build UI Docker image..."
if [[ "$1" == "--fresh" ]]; then
  echo "   (Full rebuild, ignoring cache)"
  docker build --no-cache --pull -t $IMAGE_NAME .
else
  docker build -t $IMAGE_NAME .
fi

# ========== Container Setup ==========
echo "🔹 Step 2: Stop & remove old UI container if running..."
docker stop $CONTAINER_NAME >/dev/null 2>&1 || true
docker rm $CONTAINER_NAME >/dev/null 2>&1 || true

# Run UI container
echo "🔹 Step 3: Starting UI container..."
docker run -d \
  --name $CONTAINER_NAME \
  -p $PORT:80 \
  $IMAGE_NAME

# ========== Boot ==========
sleep 2
echo "✅ UI running at http://localhost:${PORT}"
echo "   Run './run-ui.sh --fresh' for a clean rebuild."
