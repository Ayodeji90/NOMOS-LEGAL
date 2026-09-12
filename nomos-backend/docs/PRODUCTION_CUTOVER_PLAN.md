# Production Cutover Plan

Week 11 E1: Production cutover plan with per-jurisdiction flags, corpus snapshot pinning, and instant rollback.

## Overview

This document outlines the production cutover plan for NOMOS v2 backend, focusing on ZA and NG jurisdictions only.

## Pre-Cutover Checklist

### Infrastructure
- [ ] Cloud Run services deployed (staging, production)
- [ ] Cloud SQL instance configured with pgvector
- [ ] Memorystore Redis instance configured
- [ ] Firestore database configured
- [ ] GCS buckets created for corpus storage
- [ ] Secret Manager secrets configured
- [ ] Artifact Registry configured

### Data
- [ ] ZA corpus ingested and verified
- [ ] NG corpus ingested and verified
- [ ] Corpus snapshot IDs recorded
- [ ] Database migrations applied
- [ ] Vector indexes built and verified

### Configuration
- [ ] Feature flags configured (NOMOS_RETRIEVAL_V2)
- [ ] Canary percentage set to 0%
- [ ] Rollback mode disabled
- [ ] Latency budgets configured
- [ ] Rate limits configured
- [ ] Quotas configured

### Monitoring
- [ ] Cloud Logging configured
- [ ] Cloud Monitoring dashboards created
- [ ] Error reporting configured
- [ ] SLO alerts configured
- [ ] Latency budget alerts configured

## Cutover Strategy

### Phase 1: Canary (10%)
- Set `CANARY_PERCENTAGE=10` for ZA
- Monitor SLOs for 24 hours
- Check metrics:
  - p95 latency < 8s
  - 5xx rate < 0.5%
  - Refusal rate shift < 10%
- If SLOs breached: trigger rollback (set `ROLLBACK_MODE=true`)

### Phase 2: Canary (50%)
- If Phase 1 successful: set `CANARY_PERCENTAGE=50` for ZA
- Monitor SLOs for 24 hours
- Check same metrics as Phase 1
- If SLOs breached: trigger rollback

### Phase 3: Full Rollout (100%)
- If Phase 2 successful: set `CANARY_PERCENTAGE=100` for ZA
- Monitor SLOs for 48 hours
- Check same metrics as Phase 1
- If SLOs breached: trigger rollback

### Phase 4: NG Rollout
- Repeat Phases 1-3 for NG jurisdiction
- Use same SLO thresholds

## Rollback Procedure

### Instant Rollback
1. Set `ROLLBACK_MODE=true` via Secret Manager
2. Wait 30 seconds for configuration propagation
3. Verify all users receiving v1 (stable)
4. Investigate root cause
5. Fix issue
6. Set `ROLLBACK_MODE=false`
7. Resume canary from Phase 1

### Rollback Triggers
- p95 latency > 10s for 5 minutes
- 5xx rate > 1% for 5 minutes
- Refusal rate shift > 20% for 5 minutes
- Manual trigger via admin endpoint
- Critical error in logs

## Autoscale Configuration

### Cloud Run Autoscaling
```yaml
# Recommended settings for production
min_instances: 2
max_instances: 100
target_cpu_utilization: 0.6
target_memory_utilization: 0.7
concurrency: 80
timeout: 300s
```

### Database Connection Pool
```python
# Recommended settings
pool_size: 20
max_overflow: 10
pool_timeout: 30
pool_recycle: 3600
```

### Redis Connection Pool
```python
# Recommended settings
max_connections: 50
socket_timeout: 5
socket_connect_timeout: 5
retry_on_timeout: true
```

## Feature Flags

### Jurisdiction-Level Flags
- `NOMOS_RETRIEVAL_V2_ZA`: Enable v2 retrieval for ZA
- `NOMOS_RETRIEVAL_V2_NG`: Enable v2 retrieval for NG
- `NOMOS_VERIFICATION_BLOCKING`: Enable blocking verification
- `NOMOS_AGENT_LOOP`: Enable agent loop

### Canary Flags
- `CANARY_PERCENTAGE`: 0-100 (default 0)
- `ROLLBACK_MODE`: true/false (default false)

### Corpus Snapshot Pinning
- `CORPUS_SNAPSHOT_ID_ZA`: e.g., "za-2024-01-15"
- `CORPUS_SNAPSHOT_ID_NG`: e.g., "ng-2024-01-15"

## Monitoring and Alerts

### SLO Dashboards
1. **Latency Dashboard**
   - p50, p95, p99 latency per step
   - Total search runtime
   - Cold start latency

2. **Error Dashboard**
   - 5xx rate
   - 4xx rate
   - Error rate by endpoint
   - Error rate by jurisdiction

3. **Quality Dashboard**
   - Refusal rate
   - Refusal rate shift vs baseline
   - Citation validity rate
   - Invented section rate

### Alert Thresholds
- **Critical**: p95 latency > 10s, 5xx rate > 1%, refusal shift > 20%
- **Warning**: p95 latency > 8s, 5xx rate > 0.5%, refusal shift > 10%
- **Info**: p95 latency > 6s, 5xx rate > 0.3%, refusal shift > 5%

## Post-Cutover Verification

### Functional Verification
- [ ] Search endpoints returning results
- [ ] Jurisdiction filtering working
- [ ] Rate limits enforced
- [ ] Sessions persisting
- [ ] Firestore working
- [ ] Redis working

### Performance Verification
- [ ] p95 latency < 8s
- [ ] p50 latency < 4s
- [ ] 5xx rate < 0.5%
- [ ] Cold start < 10s

### Quality Verification
- [ ] Refusal rate stable
- [ ] Citation validity 100%
- [ ] No invented sections
- [ ] Entailment rate >= 95%

## Emergency Contacts

- Platform Lead: [CONTACT]
- On-Call Engineer: [CONTACT]
- Engineering Manager: [CONTACT]

## Appendix: Commands

### Set Canary Percentage
```bash
# Via Secret Manager
gcloud secrets versions add canary-config --data-file=<(echo '{"CANARY_PERCENTAGE": 10}')
```

### Trigger Rollback
```bash
# Via Secret Manager
gcloud secrets versions add canary-config --data-file=<(echo '{"ROLLBACK_MODE": true}')
```

### Pin Corpus Snapshot
```bash
# Via Secret Manager
gcloud secrets versions add corpus-config --data-file=<(echo '{"CORPUS_SNAPSHOT_ID_ZA": "za-2024-01-15"}')
```

### Check Canary Status
```bash
curl https://api.nomos.ai/api/v1/admin/canary/status
```

### Check SLO Compliance
```bash
curl https://api.nomos.ai/api/v1/admin/latency/slo
```
