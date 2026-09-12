# NOMOS Backend Deployment Guide

## Prerequisites

- GCP Project with appropriate permissions
- gcloud CLI installed and authenticated
- Docker installed
- Terraform installed (for infrastructure provisioning)

## Infrastructure Setup

### 1. Using Terraform (Recommended for Production)

```bash
cd terraform

# Initialize Terraform
terraform init

# Plan the deployment
terraform plan \
  -var="project_id=your-project-id" \
  -var="environment=staging"

# Apply the deployment
terraform apply \
  -var="project_id=your-project-id" \
  -var="environment=staging"
```

### 2. Manual Setup (Quick Start)

```bash
# Set project
gcloud config set project your-project-id

# Enable required APIs
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  redis.googleapis.com \
  firestore.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  aiplatform.googleapis.com \
  cloudbuild.googleapis.com

# Create Artifact Registry repository
gcloud artifacts repositories create staging-nomos-backend-repo \
  --repository-format=docker \
  --location=us-central1 \
  --description="NOMOS Backend Staging"
```

## Deployment

### Automated Deployment Script

```bash
# Set environment variables
export PROJECT_ID=your-project-id
export REGION=us-central1
export ENVIRONMENT=staging

# Run deployment
./scripts/deploy.sh
```

### Manual Deployment

```bash
# Build Docker image
docker build -f Dockerfile -t staging-nomos-backend:latest .

# Tag for Artifact Registry
docker tag staging-nomos-backend:latest \
  us-central1-docker.pkg.dev/your-project-id/staging-nomos-backend-repo/staging-nomos-backend:latest

# Push to Artifact Registry
docker push us-central1-docker.pkg.dev/your-project-id/staging-nomos-backend-repo/staging-nomos-backend:latest

# Deploy to Cloud Run
gcloud run deploy staging-nomos-backend \
  --image=us-central1-docker.pkg.dev/your-project-id/staging-nomos-backend-repo/staging-nomos-backend:latest \
  --region=us-central1 \
  --platform=managed \
  --allow-unauthenticated \
  --set-env-vars="ENVIRONMENT=staging"
```

## Cloud Build CI/CD

### Trigger Manual Build

```bash
gcloud builds submit \
  --config=cloudbuild.yaml \
  --substitutions=_REGION=us-central1,_ENVIRONMENT=staging,_REPO_NAME=staging-nomos-backend-repo,_SERVICE_NAME=staging-nomos-backend
```

### Setup Automated Triggers

```bash
# Create build trigger for main branch
gcloud builds triggers create github \
  --name=nomos-backend-staging \
  --repo-owner=your-org \
  --repo-name=nomos-legal \
  --branch-pattern=^main$ \
  --build-config=cloudbuild.yaml \
  --substitutions=_REGION=us-central1,_ENVIRONMENT=staging,_REPO_NAME=staging-nomos-backend-repo,_SERVICE_NAME=staging-nomos-backend
```

## Database Migrations

### Running Migrations

```bash
# Set up Cloud SQL proxy
cloud-sql-proxy your-project-id:us-central1:staging-nomos-backend-postgres

# Run migrations
DATABASE_URL="postgresql+asyncpg://nomos_app:password@localhost:5432/nomos" alembic upgrade head
```

### Rollback Migrations

```bash
alembic downgrade -1
```

## Rollback Procedure

### Using Deployment Script

```bash
./scripts/deploy.sh rollback
```

### Manual Rollback

```bash
# List revisions
gcloud run revisions list \
  --service=staging-nomos-backend \
  --region=us-central1

# Rollback to specific revision
gcloud run services update-traffic staging-nomos-backend \
  --region=us-central1 \
  --to-revisions=REVISION_NAME=100
```

## Environment Variables

### Required Variables

- `ENVIRONMENT`: staging/prod
- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection string
- `FIRESTORE_PROJECT_ID`: GCP project ID
- `GCP_PROJECT_ID`: GCP project ID
- `VERTEX_AI_LOCATION`: Vertex AI region
- `SECRET_KEY`: JWT signing secret

### Optional Variables

- `ANTHROPIC_API_KEY`: Anthropic API key
- `OPENAI_API_KEY`: OpenAI API key
- `RETRIEVAL_V2_JURISDICTIONS`: Comma-separated jurisdiction IDs for v2 retrieval

## Monitoring & Logging

### View Logs

```bash
# Cloud Run logs
gcloud logs tail /projects/your-project-id/logs/run.googleapis.com%2Frequests

# Application logs
gcloud logging tails "resource.type=cloud_run_revision AND resource.labels.service_name=staging-nomos-backend"
```

### Health Checks

```bash
# Get service URL
SERVICE_URL=$(gcloud run services describe staging-nomos-backend \
  --region=us-central1 \
  --format="value(status.url)")

# Health check
curl $SERVICE_URL/health

# Readiness check
curl $SERVICE_URL/ready

# Liveness check
curl $SERVICE_URL/live
```

## Cost Optimization

### Cloud Run

- Set appropriate min/max instances
- Enable CPU throttling for staging
- Use appropriate memory/CPU allocation

### Cloud SQL

- Use appropriate instance tier
- Enable automated backups
- Consider connection pooling

### Redis

- Use appropriate memory size
- Enable persistence for production
- Consider using Basic tier for staging

## Security

### Secret Management

```bash
# Create secret
echo "your-secret-value" | gcloud secrets create staging-nomos-backend-jwt-secret --data-file=-

# Access secret in Cloud Run
gcloud secrets versions access latest --secret=staging-nomos-backend-jwt-secret
```

### IAM Roles

Ensure the Cloud Run service account has:
- `roles/cloudsql.client`
- `roles/redis.user`
- `roles/datastore.user`
- `roles/secretmanager.secretAccessor`
- `roles/aiplatform.user`

## Troubleshooting

### Common Issues

1. **Database connection failed**
   - Check Cloud SQL instance is running
   - Verify service account has correct IAM roles
   - Check VPC peering if using private IP

2. **Redis connection failed**
   - Verify Memorystore instance is running
   - Check network connectivity
   - Verify service account permissions

3. **Deployment timeout**
   - Increase timeout in Cloud Build
   - Check image size
   - Verify build logs

4. **Health check failing**
   - Check application logs
   - Verify environment variables
   - Check database connectivity
