# Incident Runbook

Week 15 E6: Incident runbook (retrieval down, Vertex quota, DB failover).

## Overview

This runbook provides procedures for handling common incidents that may affect the NOMOS backend availability and performance.

## Incident Severity Levels

| Severity | Description | Response Time | Escalation |
|----------|-------------|---------------|------------|
| P0 | Critical - service completely down | 15 minutes | Executive |
| P1 | Major - significant degradation | 1 hour | Engineering Manager |
| P2 | Minor - partial degradation | 4 hours | Team Lead |
| P3 | Low - cosmetic issues | 1 business day | No escalation |

## Incident 1: Retrieval Service Down

### Symptoms
- Search requests failing with 500 errors
- High latency on search endpoints
- Retrieval service returning empty results
- Error logs showing database connection failures

### Impact
- Users cannot search legal documents
- All search functionality unavailable
- API returning errors

### Triage Steps
1. Check Cloud Run service health
   ```bash
   gcloud run services describe nomos-backend --region=REGION
   ```

2. Check database connectivity
   ```bash
   gcloud sql instances describe nomos-backend --region=REGION
   ```

3. Check application logs
   ```bash
   gcloud logging read "resource.type=cloud_run_revision" \
       --project=PROJECT_ID \
       --limit=50 \
       --freshness=5m
   ```

4. Check database logs
   ```bash
   gcloud logging read "resource.type=cloudsql_database" \
       --project=PROJECT_ID \
       --limit=50 \
       --freshness=5m
   ```

### Resolution Steps

#### Scenario A: Database Connection Pool Exhausted
1. Increase connection pool size in configuration
2. Restart Cloud Run service
   ```bash
   gcloud run services update nomos-backend \
       --region=REGION \
       --set-env-vars=DB_POOL_SIZE=30
   ```

#### Scenario B: Database Instance Unhealthy
1. Check instance status
   ```bash
   gcloud sql instances describe nomos-backend --region=REGION
   ```

2. If instance is unhealthy, restart it
   ```bash
   gcloud sql instances restart nomos-backend --region=REGION
   ```

3. Monitor recovery
   ```bash
   gcloud sql instances describe nomos-backend --region=REGION
   ```

#### Scenario C: Vector Index Corrupted
1. Disable hybrid retrieval (fallback to lexical)
   ```bash
   gcloud run services update nomos-backend \
       --region=REGION \
       --set-env-vars=USE_HYBRID_RETRIEVAL=false
   ```

2. Rebuild vector index
   ```sql
   -- Connect to database
   DROP INDEX IF EXISTS chunks_embedding_idx;
   CREATE INDEX chunks_embedding_idx ON chunks
   USING ivfflat (embedding vector_cosine_ops)
   WITH (lists = 100);
   ```

3. Re-enable hybrid retrieval
   ```bash
   gcloud run services update nomos-backend \
       --region=REGION \
       --set-env-vars=USE_HYBRID_RETRIEVAL=true
   ```

#### Scenario D: Read Replica Lag
1. Check replication lag
   ```sql
   SELECT * FROM pg_stat_replication;
   ```

2. If lag > 10s, consider:
   - Redirecting read traffic to primary
   - Restarting replica
   - Increasing replica resources

### Verification
1. Run smoke tests
   ```bash
   curl https://api.nomos.ai/health
   curl -X POST https://api.nomos.ai/api/v1/search \
       -H "Content-Type: application/json" \
       -d '{"query":"test","jurisdiction":"za"}'
   ```

2. Monitor error rate
   ```bash
   gcloud logging read "resource.type=cloud_run_revision AND severity>=ERROR" \
       --project=PROJECT_ID \
       --limit=10 \
       --freshness=5m
   ```

3. Verify latency
   ```bash
   gcloud monitoring time-series-list \
       --metric-type=run.googleapis.com/container/instance/response_latencies
   ```

## Incident 2: Vertex AI Quota Exceeded

### Symptoms
- Search requests failing with 429 errors
- Vertex AI API returning quota errors
- Writer/understanding calls failing
- Error logs showing quota exceeded

### Impact
- Users cannot get AI-generated responses
- Partial functionality available (retrieval works, generation fails)
- Degraded user experience

### Triage Steps
1. Check Vertex AI quota usage
   ```bash
   gcloud ai endpoints list --region=REGION
   gcloud monitoring time-series-list \
       --metric-type=aiplatform.googleapis.com/prediction/online/request_count
   ```

2. Check quota limits
   ```bash
   gcloud quotas list --service=aiplatform.googleapis.com --filter="limit:vertex"
   ```

3. Check error logs
   ```bash
   gcloud logging read "resource.type=cloud_run_revision AND quota" \
       --project=PROJECT_ID \
       --limit=50 \
       --freshness=5m
   ```

### Resolution Steps

#### Scenario A: Daily Quota Exceeded
1. Request quota increase
   ```bash
   gcloud ai endpoints request-quota-increase \
       --endpoint=ENDPOINT_ID \
       --region=REGION \
       --requested-quota=1000
   ```

2. Implement caching to reduce API calls
   - Enable result caching
   - Increase cache TTL
   - Cache common queries

3. Implement rate limiting
   - Reduce request rate
   - Queue requests
   - Implement backoff

#### Scenario B: Concurrent Request Limit Exceeded
1. Implement request queuing
   - Add queue to handle bursts
   - Process requests sequentially
   - Implement exponential backoff

2. Reduce concurrent requests
   - Limit concurrent requests per user
   - Implement request throttling
   - Use batch processing

#### Scenario C: Model-Specific Quota Exceeded
1. Switch to smaller model for understanding
   ```bash
   gcloud run services update nomos-backend \
       --region=REGION \
       --set-env-vars=UNDERSTANDING_MODEL=gemini-flash
   ```

2. Implement model fallback
   - Try Flash first, fall back to Pro if needed
   - Use different models for different tasks
   - Implement model routing

### Mitigation Strategies
1. **Result Caching**
   - Cache search results for 1-24 hours
   - Use Redis for caching
   - Implement cache warming

2. **Request Batching**
   - Batch multiple queries
   - Reduce API call overhead
   - Implement async processing

3. **Model Optimization**
   - Use smaller models where possible
   - Implement prompt optimization
   - Reduce token usage

### Verification
1. Test Vertex AI connectivity
   ```bash
   curl -X POST https://REGION-aiplatform.googleapis.com/v1/projects/PROJECT_ID/locations/REGION/publishers/google/models/gemini-pro:predict
   ```

2. Monitor quota usage
   ```bash
   gcloud monitoring time-series-list \
       --metric-type=aiplatform.googleapis.com/prediction/online/request_count
   ```

3. Check error rate
   ```bash
   gcloud logging read "resource.type=cloud_run_revision AND quota" \
       --project=PROJECT_ID \
       --limit=10 \
       --freshness=5m
   ```

## Incident 3: Database Failover

### Symptoms
- Database connection failures
- High latency on database queries
- Read replica not syncing
- Primary instance unavailable

### Impact
- All database-dependent functionality unavailable
- Search, auth, sessions all affected
- Complete service outage

### Triage Steps
1. Check primary instance status
   ```bash
   gcloud sql instances describe nomos-backend --region=REGION
   ```

2. Check read replica status
   ```bash
   gcloud sql instances describe nomos-backend-replica --region=REGION
   ```

3. Check replication status
   ```sql
   SELECT * FROM pg_stat_replication;
   ```

4. Check connection logs
   ```bash
   gcloud logging read "resource.type=cloudsql_database" \
       --project=PROJECT_ID \
       --limit=50 \
       --freshness=5m
   ```

### Resolution Steps

#### Scenario A: Primary Instance Down
1. Promote read replica to primary
   ```bash
   gcloud sql instances promote nomos-backend-replica --region=REGION
   ```

2. Update application configuration
   ```bash
   gcloud run services update nomos-backend \
       --region=REGION \
       --set-env-vars=DB_HOST=new-primary-host
   ```

3. Create new read replica
   ```bash
   gcloud sql instances create nomos-backend-replica-new \
       --region=REGION \
       --master-instance-name=nomos-backend-replica \
       --tier=db-custom-2-7680
   ```

#### Scenario B: Replication Lag
1. Check lag
   ```sql
   SELECT * FROM pg_stat_replication;
   ```

2. If lag > 30s:
   - Redirect read traffic to primary temporarily
   - Restart replica
   - Increase replica resources

3. Monitor recovery
   ```bash
   gcloud sql instances describe nomos-backend-replica --region=REGION
   ```

#### Scenario C: Connection Pool Exhausted
1. Increase pool size
   ```bash
   gcloud run services update nomos-backend \
       --region=REGION \
       --set-env-vars=DB_POOL_SIZE=30
   ```

2. Restart application
   ```bash
   gcloud run services update nomos-backend --region=REGION
   ```

3. Monitor connections
   ```sql
   SELECT count(*) FROM pg_stat_activity;
   ```

### Failover Procedure

#### Planned Failover
1. **Preparation**
   - Notify stakeholders
   - Schedule maintenance window
   - Backup current configuration

2. **Execution**
   - Promote replica to primary
   - Update application configuration
   - Verify connectivity
   - Monitor performance

3. **Verification**
   - Run smoke tests
   - Monitor error rates
   - Check replication status
   - Verify data integrity

#### Emergency Failover
1. **Immediate Action**
   - Promote replica to primary
   - Update application configuration
   - Notify stakeholders

2. **Recovery**
   - Fix original primary
   - Rebuild replica
   - Restore normal configuration

3. **Post-Incident**
   - Document incident
   - Review root cause
   - Update procedures

### Verification
1. Test database connectivity
   ```bash
   gcloud sql connect nomos-backend --region=REGION
   ```

2. Run health check
   ```bash
   curl https://api.nomos.ai/health
   ```

3. Monitor replication
   ```sql
   SELECT * FROM pg_stat_replication;
   ```

## General Incident Response Procedure

### 1. Detection
- Monitor alerts
- Check dashboards
- Review logs
- User reports

### 2. Triage
- Assess severity
- Determine impact
- Identify affected components
- Estimate recovery time

### 3. Mitigation
- Implement temporary fixes
- Reduce impact
- Communicate with stakeholders
- Document actions

### 4. Resolution
- Implement permanent fix
- Verify recovery
- Monitor for recurrence
- Update documentation

### 5. Post-Incident
- Conduct post-mortem
- Identify root cause
- Implement preventive measures
- Update runbook

## Communication

### Internal Communication
- Engineering team: Slack #incidents
- Management: Email + Slack
- Support team: Zendesk + Slack

### External Communication
- Users: Status page
- Customers: Email notification
- Public: Twitter/X (if major)

### Status Updates
- Initial: Incident detected, investigating
- Update: Working on resolution, ETA
- Resolution: Issue resolved, monitoring
- Post-mortem: Root cause analysis available

## Escalation Matrix

| Severity | First Responder | Escalation Time | Escalate To |
|----------|----------------|-----------------|-------------|
| P0 | On-call engineer | 15 min | Engineering Manager, CTO |
| P1 | On-call engineer | 1 hour | Engineering Manager |
| P2 | Team member | 4 hours | Team Lead |
| P3 | Team member | 1 business day | No escalation |

## Contact Information

### On-Call
- Primary: [CONTACT]
- Secondary: [CONTACT]

### Engineering
- Engineering Manager: [CONTACT]
- Team Lead: [CONTACT]
- Platform Lead: [CONTACT]

### Management
- CTO: [CONTACT]
- VP Engineering: [CONTACT]

## Appendix: Useful Commands

### Health Checks
```bash
# Application health
curl https://api.nomos.ai/health
curl https://api.nomos.ai/live
curl https://api.nomos.ai/ready

# Database health
gcloud sql instances describe nomos-backend --region=REGION

# Redis health
gcloud redis instances describe nomos-redis --region=REGION
```

### Log Queries
```bash
# Recent errors
gcloud logging read "resource.type=cloud_run_revision AND severity>=ERROR" \
    --project=PROJECT_ID \
    --limit=50 \
    --freshness=5m

# Database errors
gcloud logging read "resource.type=cloudsql_database AND severity>=ERROR" \
    --project=PROJECT_ID \
    --limit=50 \
    --freshness=5m
```

### Metrics
```bash
# Request rate
gcloud monitoring time-series-list \
    --metric-type=run.googleapis.com/container/instance/request_count

# Latency
gcloud monitoring time-series-list \
    --metric-type=run.googleapis.com/container/instance/response_latencies

# Error rate
gcloud monitoring time-series-list \
    --metric-type=run.googleapis.com/container/instance/response_count_by_status_code
```
