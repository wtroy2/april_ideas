#!/bin/bash
# Deploy the Critter backend to Cloud Run.
# Mirrors the RateRail deploy.sh pattern but targets the wtroy-test-proj GCP project.

set -e

PROJECT_ID="wtroy-test-proj"
REGION="us-central1"
SERVICE_NAME="critter-backend"
VPC_CONNECTOR="critter-redis-connector"
CLOUD_SQL_INSTANCE="${PROJECT_ID}:${REGION}:critter-sql"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}🚀 Deploying critter-backend to Cloud Run (${PROJECT_ID})${NC}"

gcloud config set project $PROJECT_ID
gcloud config set run/region $REGION

echo -e "${YELLOW}📦 Building image...${NC}"
gcloud builds submit . --tag gcr.io/$PROJECT_ID/$SERVICE_NAME:latest --project $PROJECT_ID

echo -e "${YELLOW}🌐 Deploying to Cloud Run with VPC connector for Redis...${NC}"
gcloud run deploy $SERVICE_NAME \
  --image gcr.io/$PROJECT_ID/$SERVICE_NAME:latest \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --port 8080 \
  --memory 2Gi \
  --cpu 2 \
  --concurrency 1000 \
  --max-instances 10 \
  --min-instances 0 \
  --timeout 3600 \
  --vpc-connector $VPC_CONNECTOR \
  --vpc-egress private-ranges-only \
  --set-env-vars "PROD_DEPLOY=True,GOOGLE_CLOUD_PROJECT_ID=${PROJECT_ID},GOOGLE_CLOUD_REGION=${REGION}" \
  --add-cloudsql-instances $CLOUD_SQL_INSTANCE \
  --set-secrets "GCP_SQL_PROD_USER=critter-sql-user:latest,GCP_SQL_PROD_PASSWORD=critter-sql-password:latest,GCP_SQL_DB_NAME=critter-sql-db-name:latest,GCP_SQL_CONNECTION_NAME=critter-sql-connection-name:latest,SECRET_KEY=critter-django-secret:latest,GOOGLE_SA_KEYFILE=critter-service-account-key:latest,GS_BUCKET_NAME=critter-bucket-clean:latest,GS_UNSCANNED_BUCKET_NAME=critter-bucket-unscanned:latest,GS_QUARANTINE_BUCKET_NAME=critter-bucket-quarantine:latest,REDIS_HOST=critter-redis-host:latest,REDIS_PORT=critter-redis-port:latest,ANTHROPIC_API_KEY=critter-anthropic-key:latest,RUNWAY_API_KEY=critter-runway-key:latest,ELEVENLABS_API_KEY=critter-elevenlabs-key:latest,KLING_ACCESS_KEY=critter-kling-access-key:latest,KLING_SECRET_KEY=critter-kling-secret-key:latest,STRIPE_SECRET_KEY=critter-stripe-secret:latest,STRIPE_WEBHOOK_SECRET=critter-stripe-webhook-secret:latest" \
  --project $PROJECT_ID

SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format='value(status.url)')
echo -e "${GREEN}✅ Backend deployed: $SERVICE_URL${NC}"

echo -e "${YELLOW}🗄️  Running migrations as a Cloud Run job...${NC}"
gcloud run jobs delete critter-migrate --region=$REGION --project=$PROJECT_ID --quiet 2>/dev/null || true
gcloud run jobs create critter-migrate \
  --image gcr.io/$PROJECT_ID/$SERVICE_NAME:latest \
  --region $REGION \
  --memory 1Gi --cpu 1 \
  --set-env-vars "PROD_DEPLOY=True,GOOGLE_CLOUD_PROJECT_ID=${PROJECT_ID}" \
  --set-cloudsql-instances $CLOUD_SQL_INSTANCE \
  --set-secrets "GCP_SQL_PROD_USER=critter-sql-user:latest,GCP_SQL_PROD_PASSWORD=critter-sql-password:latest,GCP_SQL_DB_NAME=critter-sql-db-name:latest,GCP_SQL_CONNECTION_NAME=critter-sql-connection-name:latest,SECRET_KEY=critter-django-secret:latest,GOOGLE_SA_KEYFILE=critter-service-account-key:latest,GS_BUCKET_NAME=critter-bucket-clean:latest" \
  --task-timeout 900 \
  --command python --args manage.py,migrate,--verbosity=2 \
  --project $PROJECT_ID

gcloud run jobs execute critter-migrate --region=$REGION --project=$PROJECT_ID --wait

echo -e "${GREEN}✅ Migrations done.${NC}"
echo "Service URL: $SERVICE_URL"
echo "Next: ./deploy_worker.sh to deploy the RQ worker"
