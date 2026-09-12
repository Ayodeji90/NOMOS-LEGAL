# Secret Rotation Guide

Week 14 E1: Secret Manager rotation drill for production security.

## Overview

This document covers secret rotation procedures for NOMOS backend secrets stored in Google Secret Manager.

## Secrets Inventory

### Database Secrets
- `nomos-db-primary-url`: Primary database connection string
- `nomos-db-replica-url`: Read replica database connection string

### Redis Secrets
- `nomos-redis-url`: Redis connection string

### Firestore Secrets
- `nomos-firestore-project-id`: Firestore project ID
- `nomos-firestore-credentials`: Firestore service account credentials

### API Keys
- `vertex-api-key`: Vertex AI API key
- `google-cloud-credentials`: Google Cloud service account credentials

### Application Secrets
- `nomos-secret-key`: FastAPI secret key for JWT signing
- `nomos-session-secret`: Session cookie secret

## Rotation Procedure

### Pre-Rotation Checklist
- [ ] Schedule maintenance window
- [ ] Notify stakeholders
- [ ] Document current secret versions
- [ ] Prepare rollback plan
- [ ] Test rotation in staging

### Rotation Steps

#### 1. Create New Secret Version
```bash
# Generate new secret
NEW_SECRET=$(openssl rand -base64 32)

# Add new version to Secret Manager
gcloud secrets versions add nomos-secret-key \
    --project=PROJECT_ID \
    --data-file=<(echo "$NEW_SECRET")
```

#### 2. Deploy New Version
```bash
# Update Cloud Run to use new version
gcloud run services update nomos-backend \
    --project=PROJECT_ID \
    --region=REGION \
    --set-secrets="NOMOS_SECRET_KEY=nomos-secret-key:latest"
```

#### 3. Verify Application Health
```bash
# Check health endpoint
curl https://api.nomos.ai/health

# Check logs for errors
gcloud logging read "resource.type=cloud_run_revision" \
    --project=PROJECT_ID \
    --limit=50 \
    --freshness=5m
```

#### 4. Monitor for Issues
- Check error rates
- Monitor latency
- Review authentication failures
- Verify database connectivity

#### 5. Disable Old Version (after verification)
```bash
# Wait 24-48 hours for verification
# Then disable old version
OLD_VERSION_ID=1
gcloud secrets versions disable $OLD_VERSION_ID \
    --secret=nomos-secret-key \
    --project=PROJECT_ID
```

### Rotation Frequency

| Secret Type | Rotation Frequency | Notes |
|-------------|-------------------|-------|
| Database passwords | Quarterly | Coordinate with DB team |
| API keys | As needed | When compromised or expired |
| Application secrets | Quarterly | Regular security practice |
| Service account keys | Annually | Follow Google best practices |

## Automated Rotation

### Using Secret Manager Rotation

Google Secret Manager supports automatic rotation for some secret types.

```bash
# Enable automatic rotation (90-day period)
gcloud secrets update nomos-secret-key \
    --project=PROJECT_ID \
    --rotation-period="7776000s" \
    --rotation-next="2024-04-15T00:00:00Z"
```

### Custom Rotation Script

```python
#!/usr/bin/env python3
"""
Automated secret rotation script.
"""
import subprocess
import logging
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SECRETS_TO_ROTATE = [
    "nomos-secret-key",
    "nomos-session-secret",
]

def rotate_secret(secret_name: str):
    """Rotate a single secret."""
    logger.info(f"Rotating secret: {secret_name}")

    # Generate new secret
    new_secret = subprocess.check_output(
        ["openssl", "rand", "-base64", "32"]
    ).decode().strip()

    # Add new version
    subprocess.run(
        [
            "gcloud", "secrets", "versions", "add", secret_name,
            "--project=PROJECT_ID",
            "--data-file=/dev/stdin"
        ],
        input=new_secret.encode(),
        check=True
    )

    logger.info(f"Secret rotated: {secret_name}")

def main():
    for secret in SECRETS_TO_ROTATE:
        try:
            rotate_secret(secret)
        except Exception as e:
            logger.error(f"Failed to rotate {secret}: {e}")

if __name__ == "__main__":
    main()
```

## Emergency Rotation

### Compromised Secret

If a secret is compromised:

1. **Immediate Action**
   ```bash
   # Rotate immediately
   gcloud secrets versions add nomos-secret-key \
       --project=PROJECT_ID \
       --data-file=<(openssl rand -base64 32)
   ```

2. **Deploy to Production**
   ```bash
   gcloud run services update nomos-backend \
       --project=PROJECT_ID \
       --region=REGION \
       --set-secrets="NOMOS_SECRET_KEY=nomos-secret-key:latest"
   ```

3. **Investigate**
   - Review access logs
   - Check for unauthorized access
   - Document incident

4. **Post-Incident**
   - Rotate all related secrets
   - Update security policies
   - Conduct security review

## Rollback Procedure

If rotation causes issues:

1. **Revert to Previous Version**
   ```bash
   # Enable old version
   gcloud secrets versions enable OLD_VERSION_ID \
       --secret=nomos-secret-key \
       --project=PROJECT_ID

   # Update Cloud Run to use specific version
   gcloud run services update nomos-backend \
       --project=PROJECT_ID \
       --region=REGION \
       --set-secrets="NOMOS_SECRET_KEY=nomos-secret-key:OLD_VERSION_ID"
   ```

2. **Verify Recovery**
   - Check application health
   - Monitor error rates
   - Verify functionality

3. **Investigate Issue**
   - Review logs
   - Test secret format
   - Check configuration

## Monitoring and Alerts

### Secret Access Monitoring

```bash
# View secret access logs
gcloud logging read "resource.type=secret_manager" \
    --project=PROJECT_ID \
    --limit=100 \
    --freshness=1h
```

### Alert Configuration

Set up alerts for:
- Failed secret access attempts
- Unusual access patterns
- Secret version changes
- Rotation failures

## Best Practices

1. **Never log secrets**
2. **Use environment variables for secret injection**
3. **Rotate secrets regularly**
4. **Use strong random secrets**
5. **Limit secret access with IAM**
6. **Document rotation procedures**
7. **Test rotation in staging first**
8. **Have rollback plan ready**

## Appendix: IAM Permissions

### Required Permissions for Rotation

- `secretmanager.versions.enable`
- `secretmanager.versions.disable`
- `secretmanager.versions.add`
- `secretmanager.versions.destroy`
- `secretmanager.secrets.get`
- `secretmanager.secrets.list`

### Service Account Permissions

```bash
# Grant service account secret access
gcloud secrets add-iam-policy-binding nomos-secret-key \
    --project=PROJECT_ID \
    --member="serviceAccount:nomos-backend@PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
```
