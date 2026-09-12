# Canary Checklist - Week 4 E5 Deliverable

**Purpose**: Checklist for ZA canary rollout to production with instant rollback capability.

**Target**: 10% ZA traffic to v2 hybrid retrieval path.

**Rollback**: Instant rollback via feature flag.

---

## Pre-Canary Checklist

### Infrastructure
- [ ] Cloud Run service deployed to production
- [ ] Database migrations applied (002_chunk_retrieval_indexes)
- [ ] Redis Memorystore available
- [ ] Firestore available
- [ ] Secret Manager secrets configured
- [ ] Artifact Registry image pushed
- [ ] Health check endpoints responding (`/health`, `/live`, `/ready`)

### Data
- [ ] ZA corpus ingested (BCEA + Companies Act)
- [ ] Embeddings generated for all chunks
- [ ] HNSW index built and verified
- [ ] tsvector + GIN indexes built and verified
- [ ] Synonym dictionary loaded (za_synonyms.json)
- [ ] Retrieval tuning config loaded (retrieval_tuning.json)

### Configuration
- [ ] Feature flag `RETRIEVAL_V2_JURISDICTIONS` set to empty string (disabled)
- [ ] Environment variable `ENVIRONMENT` set to `production`
- [ ] GCP project ID configured
- [ ] Vertex AI credentials configured
- [ ] Redis connection configured
- [ ] Database connection pool configured

### Monitoring
- [ ] Cloud Logging configured
- [ ] Cloud Monitoring dashboards created
- [ ] Error reporting configured
- [ ] Latency SLOs defined (p95 < 8s total)
- [ ] Alerting rules configured (5xx rate, latency, error rate)

### Eval
- [ ] Golden set eval runs successfully in staging
- [ ] Recall@10 meets target
- [ ] MRR meets target
- [ ] Leakage = 0 on golden set
- [ ] Refusal correctness = 100% on golden set
- [ ] Citation validity = 100% on golden set

---

## Canary Rollout Steps

### 1. Deploy v2 to Production (0% traffic)
- [ ] Deploy new Cloud Run revision
- [ ] Verify health checks pass
- [ ] Run smoke tests against production
- [ ] Check logs for errors
- [ ] Verify feature flag is disabled (0% traffic)

### 2. Enable Canary (10% ZA traffic)
- [ ] Set feature flag `RETRIEVAL_V2_JURISDICTIONS` to `za`
- [ ] Monitor Cloud Logging for errors
- [ ] Monitor Cloud Monitoring for latency
- [ ] Monitor error rate (5xx)
- [ ] Monitor refusal rate shift

### 3. 30-Minute Observation Period
- [ ] Check error rate < 1%
- [ ] Check p95 latency < 8s
- [ ] Check refusal rate within expected range
- [ ] Check for leakage (wrong-jurisdiction answers)
- [ ] Check for hallucinations (invented sections)
- [ ] Review sample queries and answers

### 4. Metrics Validation
- [ ] Recall@10 within 10% of staging baseline
- [ ] MRR within 10% of staging baseline
- [ ] Leakage = 0
- [ ] Refusal correctness > 95%
- [ ] Citation validity > 95%
- [ ] User feedback positive

---

## Rollback Triggers

**Immediate Rollback** (instant):
- Error rate > 5%
- p95 latency > 15s
- Leakage detected (wrong-jurisdiction answers)
- Hallucinations detected (invented sections)
- Database connection failures
- Redis connection failures
- Vertex API failures

**Investigate Then Rollback**:
- Error rate 1-5%
- p95 latency 8-15s
- Refusal rate shift > 20%
- Recall@10 drop > 20%
- MRR drop > 20%
- User feedback negative

---

## Rollback Procedure

### Instant Rollback (Feature Flag)
```bash
# Set feature flag to empty string (disable v2)
gcloud secrets versions add latest --data-file=<(echo '{"RETRIEVAL_V2_JURISDICTIONS":""}') nomos-secrets
```

### Full Rollback (Cloud Run Revision)
```bash
# Rollback to previous revision
gcloud run services rollback nomos-backend --region=REGION
```

### Verification After Rollback
- [ ] Feature flag confirmed disabled
- [ ] Traffic reverted to old path
- [ ] Error rate returns to baseline
- [ ] Latency returns to baseline
- [ ] User complaints stop

---

## Post-Canary Checklist

### If Canary Successful
- [ ] Document metrics (recall, MRR, latency, error rate)
- [ ] Document user feedback
- [ ] Plan gradual increase to 100% (25% → 50% → 100%)
- [ ] Schedule next canary increase
- [ ] Update cost snapshot

### If Canary Failed
- [ ] Document failure reason
- [ ] Document rollback time
- [ ] Document impact on users
- [ ] Create fix plan
- [ ] Schedule re-canary after fix

---

## Canary Success Criteria

**Must Pass**:
- Error rate < 1%
- p95 latency < 8s
- Leakage = 0
- Refusal correctness > 95%
- Citation validity > 95%

**Should Pass**:
- Recall@10 within 10% of staging
- MRR within 10% of staging
- User feedback positive
- Cost within budget

---

## Contact Information

**On-Call**: [TBD]
**Engineering Lead**: E1
**Retrieval Lead**: E2
**AI Lead**: E3
**Quality Lead**: E5

---

## Appendix: SLO Definitions

### Latency SLO
- p95 total query latency < 8s
- Breakdown:
  - Query understanding: ~300ms
  - Retrieval + rerank: < 1.5s
  - Writer: < 4s
  - Verifier: < 1.5s

### Error Rate SLO
- 5xx error rate < 1%
- 4xx error rate < 5%

### Refusal Rate SLO
- Refusal rate within 10-20% (depends on query mix)
- No shift > 20% from baseline

### Leakage SLO
- Wrong-jurisdiction answers = 0
- Cross-Act leakage = 0

---

**Last Updated**: 2026-09-12
**Version**: 1.0
