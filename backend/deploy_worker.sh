#!/bin/bash
# Deploy the RQ worker to Cloud Run.

set -e

PROJECT_ID="wtroy-test-proj"
REGION="us-central1"
SERVICE_NAME="critter-worker"
VPC_CONNECTOR="critter-redis-connector"
CLOUD_SQL_INSTANCE="${PROJECT_ID}:${REGION}:critter-sql"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}🚀 Deploying critter-worker (RQ) to Cloud Run${NC}"

gcloud config set project $PROJECT_ID
gcloud config set run/region $REGION

echo -e "${YELLOW}📦 Building worker image...${NC}"
gcloud builds submit . \
  --tag gcr.io/$PROJECT_ID/$SERVICE_NAME:latest \
  --config=- <<EOF
steps:
- name: 'gcr.io/cloud-builders/docker'
  args: ['build', '-f', 'Dockerfile.worker', '-t', 'gcr.io/$PROJECT_ID/$SERVICE_NAME:latest', '.']
images: ['gcr.io/$PROJECT_ID/$SERVICE_NAME:latest']
EOF

gcloud run deploy $SERVICE_NAME \
  --image gcr.io/$PROJECT_ID/$SERVICE_NAME:latest \
  --platform managed \
  --region $REGION \
  --no-allow-unauthenticated \
  --port 8080 \
  --memory 2Gi --cpu 2 \
  --max-instances 5 --min-instances 1 \
  --timeout 3600 \
  --vpc-connector $VPC_CONNECTOR \
  --vpc-egress private-ranges-only \
  --set-env-vars "PROD_DEPLOY=True,GOOGLE_CLOUD_PROJECT_ID=${PROJECT_ID}" \
  --add-cloudsql-instances $CLOUD_SQL_INSTANCE \
  --set-secrets "GCP_SQL_PROD_USER=critter-sql-user:latest,GCP_SQL_PROD_PASSWORD=critter-sql-password:latest,GCP_SQL_DB_NAME=critter-sql-db-name:latest,GCP_SQL_CONNECTION_NAME=critter-sql-connection-name:latest,SECRET_KEY=critter-django-secret:latest,GOOGLE_SA_KEYFILE=critter-service-account-key:latest,GS_BUCKET_NAME=critter-bucket-clean:latest,GS_UNSCANNED_BUCKET_NAME=critter-bucket-unscanned:latest,GS_QUARANTINE_BUCKET_NAME=critter-bucket-quarantine:latest,REDIS_HOST=critter-redis-host:latest,REDIS_PORT=critter-redis-port:latest,ANTHROPIC_API_KEY=critter-anthropic-key:latest,RUNWAY_API_KEY=critter-runway-key:latest,KLING_ACCESS_KEY=critter-kling-access-key:latest,KLING_SECRET_KEY=critter-kling-secret-key:latest" \
  --project $PROJECT_ID

echo -e "${GREEN}✅ Worker deployed${NC}"
