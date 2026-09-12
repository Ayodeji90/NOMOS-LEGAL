#!/bin/bash
# NOMOS Backend Deployment Script
# Deploys to Cloud Run with proper infrastructure checks

set -e

# Configuration
PROJECT_ID="${PROJECT_ID:-nomos-dev}"
REGION="${REGION:-us-central1}"
ENVIRONMENT="${ENVIRONMENT:-staging}"
SERVICE_NAME="${ENVIRONMENT}-nomos-backend"
IMAGE_NAME="${SERVICE_NAME}:latest"
REGISTRY_URL="${REGION}-docker.pkg.dev/${PROJECT_ID}/${ENVIRONMENT}-nomos-backend-repo"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    if ! command -v gcloud &> /dev/null; then
        log_error "gcloud CLI not found. Please install it first."
        exit 1
    fi
    
    if ! command -v docker &> /dev/null; then
        log_error "Docker not found. Please install it first."
        exit 1
    fi
    
    # Check if authenticated
    if ! gcloud auth list --filter="status:ACTIVE" --format="value(account)" | grep -q "@"; then
        log_error "Not authenticated with gcloud. Run: gcloud auth login"
        exit 1
    fi
    
    log_info "Prerequisites check passed."
}

# Set GCP project
set_project() {
    log_info "Setting GCP project to ${PROJECT_ID}..."
    gcloud config set project "${PROJECT_ID}"
}

# Enable required APIs
enable_apis() {
    log_info "Enabling required APIs..."
    gcloud services enable \
        run.googleapis.com \
        sqladmin.googleapis.com \
        redis.googleapis.com \
        firestore.googleapis.com \
        secretmanager.googleapis.com \
        artifactregistry.googleapis.com \
        aiplatform.googleapis.com \
        cloudbuild.googleapis.com
}

# Build Docker image
build_image() {
    log_info "Building Docker image..."
    docker build -f Dockerfile.dev -t "${IMAGE_NAME}" --target production .
    log_info "Docker image built successfully."
}

# Tag and push to Artifact Registry
push_image() {
    log_info "Pushing image to Artifact Registry..."
    
    # Create repository if it doesn't exist
    if ! gcloud artifacts repositories describe "${ENVIRONMENT}-nomos-backend-repo" --location="${REGION}" &>/dev/null; then
        log_info "Creating Artifact Registry repository..."
        gcloud artifacts repositories create "${ENVIRONMENT}-nomos-backend-repo" \
            --repository-format=docker \
            --location="${REGION}" \
            --description="NOMOS Backend ${ENVIRONMENT}"
    fi
    
    # Tag image for registry
    FULL_IMAGE_URL="${REGISTRY_URL}/${IMAGE_NAME}"
    docker tag "${IMAGE_NAME}" "${FULL_IMAGE_URL}"
    
    # Push image
    docker push "${FULL_IMAGE_URL}"
    log_info "Image pushed successfully."
}

# Deploy to Cloud Run
deploy_cloud_run() {
    log_info "Deploying to Cloud Run..."
    
    FULL_IMAGE_URL="${REGISTRY_URL}/${IMAGE_NAME}"
    
    # Check if service exists
    if gcloud run services describe "${SERVICE_NAME}" --region="${REGION}" &>/dev/null; then
        log_info "Updating existing service..."
        gcloud run services update "${SERVICE_NAME}" \
            --region="${REGION}" \
            --image="${FULL_IMAGE_URL}" \
            --platform=managed \
            --allow-unauthenticated
    else
        log_info "Creating new service..."
        gcloud run deploy "${SERVICE_NAME}" \
            --region="${REGION}" \
            --image="${FULL_IMAGE_URL}" \
            --platform=managed \
            --allow-unauthenticated \
            --set-env-vars="ENVIRONMENT=${ENVIRONMENT}"
    fi
    
    log_info "Cloud Run deployment successful."
}

# Run database migrations
run_migrations() {
    log_info "Running database migrations..."
    
    # Get Cloud SQL connection details
    # This assumes you have Cloud SQL proxy or similar setup
    # For production, you'd use Cloud SQL proxy or direct connection
    log_warn "Database migrations should be run via Cloud SQL proxy or separate migration job."
    log_warn "Skipping automatic migrations for safety."
}

# Verify deployment
verify_deployment() {
    log_info "Verifying deployment..."
    
    SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
        --region="${REGION}" \
        --format="value(status.url)")
    
    # Wait for service to be ready
    log_info "Waiting for service to be ready..."
    sleep 10
    
    # Health check
    if curl -f -s "${SERVICE_URL}/health" > /dev/null; then
        log_info "Health check passed."
    else
        log_error "Health check failed."
        exit 1
    fi
    
    log_info "Deployment verification successful."
    log_info "Service URL: ${SERVICE_URL}"
}

# Rollback function
rollback() {
    log_warn "Initiating rollback..."
    
    # Get previous revision
    PREVIOUS_REVISION=$(gcloud run revisions list \
        --service="${SERVICE_NAME}" \
        --region="${REGION}" \
        --limit=2 \
        --format="value(name)" | tail -n 1)
    
    if [ -z "$PREVIOUS_REVISION" ]; then
        log_error "No previous revision found for rollback."
        exit 1
    fi
    
    log_info "Rolling back to revision: ${PREVIOUS_REVISION}"
    gcloud run services update-traffic "${SERVICE_NAME}" \
        --region="${REGION}" \
        --to-revisions="${PREVIOUS_REVISION}=100"
    
    log_info "Rollback completed."
}

# Main deployment flow
main() {
    log_info "Starting deployment for ${ENVIRONMENT} environment..."
    
    check_prerequisites
    set_project
    enable_apis
    build_image
    push_image
    deploy_cloud_run
    run_migrations
    verify_deployment
    
    log_info "Deployment completed successfully!"
}

# Handle rollback flag
if [ "$1" == "rollback" ]; then
    rollback
    exit 0
fi

# Run main deployment
main
