# NOMOS Backend - GCP Infrastructure
# Terraform configuration for Cloud Run, Cloud SQL, Redis, Firestore, Secret Manager, Artifact Registry

terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
  backend "gcs" {
    bucket = "nomos-terraform-state"
    prefix = "nomos-backend"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Variables
variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP Region"
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Environment (staging/prod)"
  type        = string
  default     = "staging"
}

# locals
locals {
  name_prefix = "${var.environment}-nomos-backend"
}

# Artifact Registry
resource "google_artifact_registry_repository" "backend" {
  location      = var.region
  repository_id = "${local.name_prefix}-repo"
  description   = "Docker repository for NOMOS backend"
  format        = "DOCKER"
}

# Cloud SQL PostgreSQL with pgvector
resource "google_sql_database_instance" "postgres" {
  name             = "${local.name_prefix}-postgres"
  database_version = "POSTGRES_16"
  region           = var.region
  
  settings {
    tier              = var.environment == "prod" ? "db-custom-4-16384" : "db-custom-2-8192"
    disk_autoresize   = true
    disk_size         = var.environment == "prod" ? 100 : 20
    disk_type         = "PD_SSD"
    availability_type = var.environment == "prod" ? "REGIONAL" : "ZONAL"
    
    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = var.environment == "prod"
      backup_retention_settings {
        retained_backups = 7
        retention_unit   = "COUNT"
      }
    }
    
    database_flags {
      name  = "cloudsql.enable_pgvector"
      value = "on"
    }
    
    ip_configuration {
      ipv4_enabled    = true
      private_network = var.environment == "prod" ? google_compute_network.vpc[0].id : null
      require_ssl     = var.environment == "prod"
    }
  }
  
  deletion_protection = var.environment == "prod"
}

resource "google_sql_database" "nomos" {
  name     = "nomos"
  instance = google_sql_database_instance.postgres.name
}

resource "google_sql_user" "app" {
  name     = "nomos_app"
  instance = google_sql_database_instance.postgres.name
  password = random_password.db_password.result
}

# Memorystore Redis
resource "google_redis_instance" "cache" {
  name           = "${local.name_prefix}-redis"
  tier           = var.environment == "prod" ? "STANDARD_HA" : "BASIC"
  memory_size_gb = var.environment == "prod" ? 4 : 1
  region         = var.region
  
  redis_version     = "7"
  display_name      = "${local.name_prefix}-redis"
  authorized_network = var.environment == "prod" ? google_compute_network.vpc[0].id : null
  
  maintenance_policy {
    weekly_maintenance_window {
      day = "SUNDAY"
      start_hour = 3
    }
  }
  
  persistence_config {
    persistence_mode_id = "RDB"
    rdb_snapshot_period = "ONE_HOUR"
  }
}

# Firestore (Native mode)
resource "google_firestore_database" "default" {
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"
  
  deletion_policy = "DELETE"
}

# Secret Manager
resource "google_secret_manager_secret" "jwt_secret" {
  secret_id = "${local.name_prefix}-jwt-secret"
  
  replication {
    automatic = true
  }
  
  depends_on = [google_project_service.secret_manager]
}

resource "google_secret_manager_secret_version" "jwt_secret" {
  secret      = google_secret_manager_secret.jwt_secret.id
  secret_data = random_password.jwt_secret.result
}

resource "google_secret_manager_secret" "anthropic_api_key" {
  secret_id = "${local.name_prefix}-anthropic-api-key"
  
  replication {
    automatic = true
  }
  
  depends_on = [google_project_service.secret_manager]
}

resource "google_secret_manager_secret" "openai_api_key" {
  secret_id = "${local.name_prefix}-openai-api-key"
  
  replication {
    automatic = true
  }
  
  depends_on = [google_project_service.secret_manager]
}

# Cloud Run Service
resource "google_cloud_run_v2_service" "backend" {
  name     = local.name_prefix
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"
  
  template {
    service_account = google_service_account.backend.email
    
    containers {
      image = "us-central1-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.backend.name}/${local.name_prefix}:latest"
      
      ports {
        container_port = 8080
      }
      
      env {
        name  = "ENVIRONMENT"
        value = var.environment
      }
      
      env {
        name  = "DATABASE_URL"
        value = "postgresql+asyncpg://${google_sql_user.app.name}:${random_password.db_password.result}@${google_sql_database_instance.postgres.connection_name}/nomos?sslmode=require"
      }
      
      env {
        name  = "REDIS_URL"
        value = "redis://${google_redis_instance.cache.host}:${google_redis_instance.cache.port}/0"
      }
      
      env {
        name  = "FIRESTORE_PROJECT_ID"
        value = var.project_id
      }
      
      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      
      env {
        name  = "VERTEX_AI_LOCATION"
        value = var.region
      }
      
      env {
        name  = "SECRET_NAME_JWT"
        value = google_secret_manager_secret.jwt_secret.secret_id
      }
      
      env {
        name  = "SECRET_NAME_ANTHROPIC"
        value = google_secret_manager_secret.anthropic_api_key.secret_id
      }
      
      env {
        name  = "SECRET_NAME_OPENAI"
        value = google_secret_manager_secret.openai_api_key.secret_id
      }
      
      resources {
        limits = {
          cpu    = var.environment == "prod" ? "4" : "1"
          memory = var.environment == "prod" ? "4Gi" : "512Mi"
        }
        cpu_idle = var.environment == "prod" ? false : true
      }
      
      startup_probe {
        initial_delay_seconds = 10
        timeout_seconds      = 5
        period_seconds       = 10
        failure_threshold    = 3
        http_get {
          path = "/health"
        }
      }
      
      liveness_probe {
        http_get {
          path = "/live"
        }
        initial_delay_seconds = 30
        period_seconds        = 10
      }
      
      readiness_probe {
        http_get {
          path = "/ready"
        }
        initial_delay_seconds = 10
        period_seconds        = 5
      }
    }
    
    scaling {
      min_instances = var.environment == "prod" ? 2 : 0
      max_instances = var.environment == "prod" ? 100 : 10
    }
    
    timeout_seconds = 300
  }
  
  traffic {
    percent = 100
  }
}

# IAM
resource "google_service_account" "backend" {
  account_id   = "${local.name_prefix}-sa"
  display_name = "${local.name_prefix} Service Account"
}

resource "google_project_iam_member" "backend_roles" {
  for_each = toset([
    "roles/cloudsql.client",
    "roles/redis.user",
    "roles/datastore.user",
    "roles/secretmanager.secretAccessor",
    "roles/aiplatform.user",
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/cloudtrace.agent",
  ])
  
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.backend.email}"
}

resource "google_cloud_run_v2_service_iam_member" "public" {
  location = google_cloud_run_v2_service.backend.location
  name     = google_cloud_run_v2_service.backend.name
  member   = "allUsers"
  role     = "roles/run.invoker"
}

# VPC (for production)
resource "google_compute_network" "vpc" {
  count = var.environment == "prod" ? 1 : 0
  
  name                    = "${local.name_prefix}-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "private" {
  count = var.environment == "prod" ? 1 : 0
  
  name          = "${local.name_prefix}-private"
  ip_cidr_range = "10.0.0.0/24"
  region        = var.region
  network       = google_compute_network.vpc[0].id
  
  private_ip_google_access = true
}

# Enable APIs
resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "sqladmin.googleapis.com",
    "redis.googleapis.com",
    "firestore.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "aiplatform.googleapis.com",
    "cloudbuild.googleapis.com",
  ])
  
  project = var.project_id
  service = each.value
  
  disable_on_destroy = false
}

resource "google_project_service" "secret_manager" {
  project = var.project_id
  service = "secretmanager.googleapis.com"
}

# Random passwords
resource "random_password" "db_password" {
  length  = 32
  special = false
}

resource "random_password" "jwt_secret" {
  length  = 64
  special = false
}

# Outputs
output "cloud_run_url" {
  value = google_cloud_run_v2_service.backend.uri
}

output "sql_connection_name" {
  value = google_sql_database_instance.postgres.connection_name
}

output "redis_host" {
  value = google_redis_instance.cache.host
}

output "artifact_registry_url" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.backend.name}"
}
