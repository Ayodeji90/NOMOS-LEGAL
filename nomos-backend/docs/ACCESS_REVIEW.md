# Access Review

Week 15 E6: Access review (allowlist, admin keys, service accounts).

## Overview

This document reviews the access control mechanisms for the NOMOS backend, including allowlists, admin keys, and service accounts.

## Access Control Components

### 1. Allowlist

#### Purpose
Control which users can register for the application during prototype phase.

#### Implementation
- **File**: `app/core/access_gate.py`
- **Configuration**: `ACCESS_ALLOWLIST` environment variable
- **Default**: Empty list (allows all users)

#### Configuration
```bash
# Set allowlist via environment variable
export ACCESS_ALLOWLIST="user1@example.com,user2@example.com"

# Or via Secret Manager
gcloud secrets versions add access-allowlist \
    --data-file=<(echo '["user1@example.com", "user2@example.com"]')
```

#### Admin Endpoints
- `GET /api/v1/admin/access/allowlist` - Get current allowlist
- `POST /api/v1/admin/access/allowlist/add` - Add email to allowlist
- `POST /api/v1/admin/access/allowlist/remove` - Remove email from allowlist
- `GET /api/v1/admin/access/status?email=...` - Check if email is allowed

#### Review Checklist
- [ ] Allowlist is configured for production
- [ ] Admin endpoints are protected with authentication
- [ ] Allowlist changes are audited
- [ ] Allowlist is reviewed quarterly

### 2. Admin Keys

#### Purpose
Provide administrative access to the application without requiring user login.

#### Implementation
- **File**: `app/core/auth.py`
- **Configuration**: `ADMIN_API_KEYS` environment variable
- **Storage**: Database (APIKey table)

#### Key Management
```python
# Generate admin API key
raw_key, key_hash = auth_manager.generate_api_key()

# Store in database
api_key = APIKey(
    user_id=admin_user_id,
    key_hash=key_hash,
    key_prefix=raw_key[:12],
    name="Admin Key",
    is_active=True,
)
```

#### Security Considerations
- Keys are hashed using scrypt before storage
- Only key prefix (first 12 chars) is visible in UI
- Keys can be revoked by setting `is_active=False`
- Keys have optional expiration dates

#### Review Checklist
- [ ] Admin keys are rotated quarterly
- [ ] Admin keys are stored securely in database
- [ ] Admin key usage is logged
- [ ] Admin keys have least-privilege access
- [ ] Admin keys are revoked when personnel leave

### 3. Service Accounts

#### Purpose
Allow automated services to access the API without user authentication.

#### Implementation
- **Configuration**: Google Cloud service accounts
- **Authentication**: OAuth2 / JWT
- **Authorization**: IAM roles

#### Service Account Types

##### Cloud Run Service Account
- **Name**: `nomos-backend@PROJECT_ID.iam.gserviceaccount.com`
- **Purpose**: Run the Cloud Run service
- **Permissions**:
  - `roles/cloudsql.client` - Access Cloud SQL
  - `roles/secretmanager.secretAccessor` - Access secrets
  - `roles/firebasedatabase.user` - Access Firestore
  - `roles/redis.user` - Access Memorystore

##### Ingestion Service Account
- **Name**: `nomos-ingestion@PROJECT_ID.iam.gserviceaccount.com`
- **Purpose**: Run ingestion Cloud Run jobs
- **Permissions**:
  - `roles/storage.objectViewer` - Read from GCS
  - `roles/cloudsql.client` - Access Cloud SQL
  - `roles/secretmanager.secretAccessor` - Access secrets

##### Monitoring Service Account
- **Name**: `nomos-monitoring@PROJECT_ID.iam.gserviceaccount.com`
- **Purpose**: Access monitoring and logging
- **Permissions**:
  - `roles/monitoring.viewer` - View metrics
  - `roles/logging.viewer` - View logs
  - `roles/cloudsql.viewer` - View Cloud SQL status

#### Service Account Management
```bash
# List service accounts
gcloud iam service-accounts list --project=PROJECT_ID

# Create service account
gcloud iam service-accounts create nomos-backend \
    --project=PROJECT_ID \
    --display-name="NOMOS Backend Service Account"

# Grant roles
gcloud projects add-iam-policy-binding PROJECT_ID \
    --member="serviceAccount:nomos-backend@PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/cloudsql.client"

# Create key (store securely!)
gcloud iam service-accounts keys create key.json \
    --iam-account=nomos-backend@PROJECT_ID.iam.gserviceaccount.com
```

#### Review Checklist
- [ ] Service accounts have least-privilege access
- [ ] Service account keys are rotated annually
- [ ] Service account keys are stored in Secret Manager
- [ ] Service account usage is monitored
- [ ] Service accounts are disabled when not in use

## Access Audit Procedure

### Monthly Audit
1. Review allowlist for stale entries
2. Review active admin API keys
3. Review service account usage logs
4. Verify service account permissions are still needed
5. Review failed authentication attempts

### Quarterly Audit
1. Rotate all admin API keys
2. Rotate service account keys
3. Review and update allowlist
4. Conduct access review with stakeholders
5. Update access documentation

### Annual Audit
1. Full access control review
2. Compliance audit (if applicable)
3. Security assessment
4. Update access policies
5. Training refresh for administrators

## Incident Response

### Compromised Admin Key
1. Immediately revoke the key in database
2. Rotate all other admin keys
3. Review access logs for suspicious activity
4. Notify security team
5. Document incident

### Compromised Service Account Key
1. Immediately disable service account
2. Delete compromised key
3. Generate new key
4. Update application configuration
5. Review access logs

### Unauthorized Access Attempt
1. Block IP address if repeated attempts
2. Review allowlist configuration
3. Notify user if legitimate
4. Monitor for follow-up attempts
5. Update security policies

## Best Practices

### Allowlist
- Keep allowlist as small as possible
- Review allowlist regularly
- Use email domains instead of individual emails where possible
- Document allowlist changes with justification

### Admin Keys
- Use unique keys for each administrator
- Set expiration dates on keys
- Rotate keys regularly
- Revoke keys immediately when personnel leave
- Never log or transmit raw keys

### Service Accounts
- Use separate service accounts for different services
- Grant least-privilege permissions
- Rotate keys regularly
- Disable unused service accounts
- Monitor service account usage

## Configuration Reference

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| ACCESS_ALLOWLIST | Comma-separated list of allowed emails | "" | No |
| WAITLIST_ENABLED | Enable waitlist mode | false | No |
| ADMIN_API_KEYS | Comma-separated list of admin key prefixes | "" | No |

### Secret Manager Secrets

| Secret | Description | Rotation |
|--------|-------------|----------|
| nomos-admin-keys | Admin API key hashes | Quarterly |
| nomos-service-account-keys | Service account keys | Annually |
| nomos-db-credentials | Database credentials | Quarterly |
| nomos-redis-credentials | Redis credentials | Quarterly |

## Access Control Matrix

| Role | Allowlist | API Key | Service Account | Permissions |
|------|-----------|---------|-----------------|-------------|
| User | Required | Optional | No | Read/write own data |
| Admin | Not required | Required | No | Full access |
| Service | Not required | Required | Yes | Limited access |
| Public | Not required | No | No | Read-only public data |

## Conclusion

The NOMOS backend implements a comprehensive access control system with:
- ✅ Allowlist for user registration control
- ✅ Admin API keys for administrative access
- ✅ Service accounts for automated access
- ✅ Regular audit procedures
- ✅ Incident response procedures
- ✅ Security best practices

Regular reviews and audits ensure that access controls remain effective and secure.
