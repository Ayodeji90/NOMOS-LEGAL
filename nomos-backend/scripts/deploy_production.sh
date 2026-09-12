#!/bin/bash
# Production deployment script for NOMOS Backend to Cloud Run
# Usage: ./scripts/deploy_production.sh [staging|production]

set -e

# Configuration
PROJECT_ID="project-a98ee197-e936-490c-adb"
REGION="us-central1"
ENVIRONMENT="${1:-staging}"
REPO_NAME="nomos-backend-repo"
SERVICE_NAME="nomos-backend-${ENVIRONMENT}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== NOMOS Backend Deployment Script ===${NC}"
echo "Environment: ${ENVIRONMENT}"
echo "Region: ${REGION}"
echo "Project: ${PROJECT_ID}"
echo ""

# Set project
echo -e "${YELLOW}Setting project...${NC}"
gcloud config set project ${PROJECT_ID}

# Create Artifact Registry repository if it doesn't exist
echo -e "${YELLOW}Checking Artifact Registry repository...${NC}"
if ! gcloud artifacts repositories describe ${REPO_NAME} --location=${REGION} &>/dev/null; then
    echo "Creating Artifact Registry repository..."
    gcloud artifacts repositories create ${REPO_NAME} \
        --repository-format=docker \
        --location=${REGION} \
        --description="NOMOS Backend ${ENVIRONMENT}"
fi

# Build Docker image
echo -e "${YELLOW}Building Docker image...${NC}"
IMAGE_TAG="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${SERVICE_NAME}:$(date +%Y%m%d-%H%M%S)"
docker build -f Dockerfile -t ${IMAGE_TAG} .
docker tag ${IMAGE_TAG} ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${SERVICE_NAME}:latest

# Push to Artifact Registry
echo -e "${YELLOW}Pushing to Artifact Registry...${NC}"
docker push ${IMAGE_TAG}
docker push ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${SERVICE_NAME}:latest

# Get Cloud SQL connection name
SQL_INSTANCE_NAME="nomos-postgres"
SQL_CONNECTION_NAME=$(gcloud sql instances describe ${SQL_INSTANCE_NAME} --format="value(connectionName)")

# Get Redis connection details
REDIS_INSTANCE_NAME="nomos-redis"
REDIS_HOST=$(gcloud redis instances describe ${REDIS_INSTANCE_NAME} --region=${REGION} --format="value(host)")
REDIS_PORT=$(gcloud redis instances describe ${REDIS_INSTANCE_NAME} --region=${REGION} --format="value(port)")

# Deploy to Cloud Run
echo -e "${YELLOW}Deploying to Cloud Run...${NC}"
gcloud run deploy ${SERVICE_NAME} \
    --image=${IMAGE_TAG} \
    --region=${REGION} \
    --platform=managed \
    --allow-unauthenticated \
    --cpu=2 \
    --memory=4Gi \
    --max-instances=100 \
    --min-instances=0 \
    --timeout=300 \
    --concurrency=80 \
    --set-env-vars="ENVIRONMENT=${ENVIRONMENT}" \
    --set-env-vars="DATABASE_URL=postgresql+asyncpg://nomos_user:\$(nomos-db-password)@/nomos?host=/cloudsql/${SQL_CONNECTION_NAME}" \
    --set-env-vars="REDIS_URL=redis://:\$(nomos-redis-password)@${REDIS_HOST}:${REDIS_PORT}/0" \
    --set-env-vars="FIRESTORE_PROJECT_ID=${PROJECT_ID}" \
    --set-env-vars="GCP_PROJECT_ID=${PROJECT_ID}" \
    --set-env-vars="VERTEX_AI_LOCATION=${REGION}" \
    --set-env-vars="SECRET_KEY=\$(nomos-secret-key)" \
    --set-env-vars="VERTEX_API_KEY=\$(nomos-vertex-api-key)" \
    --set-env-vars="EMBEDDING_PROVIDER=vertex" \
    --set-env-vars="LOG_LEVEL=INFO" \
    --set-cloudsql-instances=${SQL_CONNECTION_NAME} \
    --set-secrets="nomos-db-password=nomos-db-password:latest,nomos-redis-password=nomos-redis-password:latest,nomos-secret-key=nomos-secret-key:latest,nomos-vertex-api-key=nomos-vertex-api-key:latest"

# Grant Cloud Run service account IAM permissions
echo -e "${YELLOW}Granting IAM permissions...${NC}"
SERVICE_ACCOUNT=$(gcloud iam service-accounts list --filter="displayName:Cloud Run Service Account" --format="value(email)")

# Grant Cloud SQL Client role
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/cloudsql.client" \
    --condition=None

# Grant Redis User role
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/redis.user" \
    --condition=None

# Grant Firestore User role
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/datastore.user" \
    --condition=None

# Grant Secret Accessor role
for SECRET in nomos-db-password nomos-redis-password nomos-secret-key nomos-vertex-api-key; do
    gcloud secrets add-iam-policy-binding ${SECRET} \
        --member="serviceAccount:${SERVICE_ACCOUNT}" \
        --role="roles/secretmanager.secretAccessor"
done

# Grant Vertex AI User role
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/aiplatform.user" \
    --condition=None

# Run database migrations
echo -e "${YELLOW}Running database migrations...${NC}"
# Note: This requires Cloud SQL proxy or direct connection
# For now, we'll skip this and provide manual instructions
echo -e "${YELLOW}Database migrations need to be run manually:${NC}"
echo "1. Set up Cloud SQL proxy: cloud-sql-proxy ${SQL_CONNECTION_NAME}"
echo "2. Run migrations: DATABASE_URL='postgresql+asyncpg://nomos_user:password@localhost:5432/nomos' alembic upgrade head"

# Get service URL
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} \
    --region=${REGION} \
    --format="value(status.url)")

# Health check
echo -e "${YELLOW}Running health check...${NC}"
sleep 10
curl -f ${SERVICE_URL}/health || {
    echo -e "${RED}Health check failed!${NC}"
    exit 1
}

echo -e "${GREEN}=== Deployment Successful ===${NC}"
echo "Service URL: ${SERVICE_URL}"
echo "Health check: ${SERVICE_URL}/health"
echo ""
echo "Next steps:"
echo "1. Run database migrations manually"
echo "2. Test the /search endpoint"
echo "3. Monitor logs: gcloud logs tail /projects/${PROJECT_ID}/logs/run.googleapis.com%2Frequests"
