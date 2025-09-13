#!/bin/bash
set -e

IMAGE_NAME="brain-lambda"
CONTAINER_NAME="brain-lambda-local"
PORT=9000
ROLE_ARN="arn:aws:iam::454842419567:role/org-dev-chatbot-document-v2-lambda-llm_lambda_test-role"
SESSION_NAME="brain-lambda-local-test"

# Env vars
DOCUMENTS_S3_BUCKET="chatbot-document-v2-config"
TEMP_DATA_KEY="project_data/uploads/temp"
DOCUMENTS_DATA_KEY="project_data/uploads/documents"
METADATA_TABLE="document-metadata"
CHAT_HISTORY_TABLE="chat-history"
CONFIG_BUCKET="chatbot-document-v2-config"
CONFIG_KEY="config/config.yaml"
VECTOR_DB_HOST="28b2ee72-9fc9-4ecd-acdf-d024c1c7bf5d.eu-west-1-0.aws.cloud.qdrant.io"
VECTOR_DB_PORT="6333"
VECTOR_DB_API_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIn0.U6PprcKnZl1ByQCBOurGp-ObPUmn0hKaUeZtenYEQ_8"
COLLECTION_NAME="Demo"
VECTOR_DIMENSION="1024"

# ========== Build Phase ==========
echo "🔹 Step 0: Pull base image (ensure latest Python layer)..."
docker pull amazon/aws-lambda-python:3.11 || true


if [[ "$1" == "--fresh" ]]; then
  echo "🔹 Step 1: Full rebuild (ignoring cache)..."
  docker build --no-cache --pull -t $IMAGE_NAME .
else
  echo "🔹 Step 1: Build Docker image (cache enabled, deps only rebuilt if requirements.txt changed)..."
  docker build -t $IMAGE_NAME .
fi

# ========== Container Setup ==========
echo "🔹 Step 2: Stop & remove old container if running..."
docker stop $CONTAINER_NAME >/dev/null 2>&1 || true
docker rm $CONTAINER_NAME >/dev/null 2>&1 || true

if [ -n "$ROLE_ARN" ]; then
  echo "🔹 Step 3a: Assuming role $ROLE_ARN ..."
  CREDS=$(aws sts assume-role \
    --role-arn $ROLE_ARN \
    --role-session-name $SESSION_NAME \
    --output json)

  AWS_ACCESS_KEY_ID=$(echo $CREDS | grep -o '"AccessKeyId": *"[^"]*' | cut -d'"' -f4)
  AWS_SECRET_ACCESS_KEY=$(echo $CREDS | grep -o '"SecretAccessKey": *"[^"]*' | cut -d'"' -f4)
  AWS_SESSION_TOKEN=$(echo $CREDS | grep -o '"SessionToken": *"[^"]*' | cut -d'"' -f4)
  AWS_REGION=$(aws configure get region)

  echo "✅ Got creds for $ROLE_ARN"
  docker run -d \
    --name $CONTAINER_NAME \
    -p $PORT:8080 \
    -e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID \
    -e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
    -e AWS_SESSION_TOKEN=$AWS_SESSION_TOKEN \
    -e AWS_DEFAULT_REGION=$AWS_REGION \
    -e DOCUMENTS_S3_BUCKET=$DOCUMENTS_S3_BUCKET \
    -e TEMP_DATA_KEY=$TEMP_DATA_KEY \
    -e DOCUMENTS_DATA_KEY=$DOCUMENTS_DATA_KEY \
    -e METADATA_TABLE=$METADATA_TABLE \
    -e CHAT_HISTORY_TABLE=$CHAT_HISTORY_TABLE \
    -e CONFIG_BUCKET=$CONFIG_BUCKET \
    -e CONFIG_KEY=$CONFIG_KEY \
    -e VECTOR_DB_HOST=$VECTOR_DB_HOST \
    -e VECTOR_DB_PORT=$VECTOR_DB_PORT \
    -e VECTOR_DB_API_KEY=$VECTOR_DB_API_KEY \
    -e COLLECTION_NAME=$COLLECTION_NAME \
    -e VECTOR_DIMENSION=$VECTOR_DIMENSION \
    $IMAGE_NAME
else
  echo "🔹 Step 3a: Using local ~/.aws credentials..."
  docker run -d \
    --name $CONTAINER_NAME \
    -p $PORT:8080 \
    -v ~/.aws:/root/.aws \
    -e DOCUMENTS_S3_BUCKET=$DOCUMENTS_S3_BUCKET \
    -e TEMP_DATA_KEY=$TEMP_DATA_KEY \
    -e DOCUMENTS_DATA_KEY=$DOCUMENTS_DATA_KEY \
    -e METADATA_TABLE=$METADATA_TABLE \
    -e CHAT_HISTORY_TABLE=$CHAT_HISTORY_TABLE \
    -e CONFIG_BUCKET=$CONFIG_BUCKET \
    -e CONFIG_KEY=$CONFIG_KEY \
    -e VECTOR_DB_HOST=$VECTOR_DB_HOST \
    -e VECTOR_DB_PORT=$VECTOR_DB_PORT \
    -e VECTOR_DB_API_KEY=$VECTOR_DB_API_KEY \
    -e COLLECTION_NAME=$COLLECTION_NAME \
    -e VECTOR_DIMENSION=$VECTOR_DIMENSION \
    -e PYTHONUNBUFFERED=1 \
    $IMAGE_NAME
fi

# ========== Boot ==========
sleep 5
echo "✅ Lambda running at http://localhost:${PORT}"
echo "   Run './run.sh --fresh' for a clean rebuild (ignores cache)."
