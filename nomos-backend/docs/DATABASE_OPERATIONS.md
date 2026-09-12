# Database Operations Guide

Week 13 E1: Read-replica, connection-pool review, backup + PITR drill, rollback drill.

## Overview

This document covers database operations for Cloud SQL PostgreSQL with pgvector, including read-replica configuration, connection pooling, backup procedures, and disaster recovery.

## Read-Replica Configuration

### Purpose
- Offload read queries from primary instance
- Improve read scalability
- Provide failover capability
- Support analytical queries without impacting primary

### Configuration Steps

#### 1. Create Read Replica
```bash
# Via gcloud CLI
gcloud sql instances create nomos-backend-replica \
    --project=PROJECT_ID \
    --region=REGION \
    --master-instance-name=nomos-backend \
    --tier=db-custom-2-3840 \
    --database-version=POSTGRES_15 \
    --replica-type=READ
```

#### 2. Configure Application for Read Replica
```python
# In app/db/session.py
import asyncpg
from sqlalchemy.ext.asyncio import create_async_engine

# Primary connection string
PRIMARY_DB_URL = "postgresql+asyncpg://user:pass@primary-host:5432/nomos"

# Read replica connection string
REPLICA_DB_URL = "postgresql+asyncpg://user:pass@replica-host:5432/nomos"

# Create engines
primary_engine = create_async_engine(PRIMARY_DB_URL, pool_size=20, max_overflow=10)
replica_engine = create_async_engine(REPLICA_DB_URL, pool_size=20, max_overflow=10)

# Use replica for read operations, primary for writes
async def get_read_session():
    async with replica_engine.begin() as session:
        yield session

async def get_write_session():
    async with primary_engine.begin() as session:
        yield session
```

#### 3. Routing Strategy
- **Read queries**: Use replica (SELECT, search, retrieval)
- **Write queries**: Use primary (INSERT, UPDATE, DELETE)
- **Transactional reads**: Use primary (require consistency)

## Connection Pool Configuration

### Recommended Settings

```python
# Primary instance
pool_size = 20
max_overflow = 10
pool_timeout = 30
pool_recycle = 3600
pool_pre_ping = True

# Read replica
pool_size = 20
max_overflow = 10
pool_timeout = 30
pool_recycle = 3600
pool_pre_ping = True
```

### Monitoring
- Track active connections
- Monitor pool exhaustion
- Check connection wait times
- Review pool efficiency

```python
# Check pool status
from sqlalchemy import inspect

def check_pool_status(engine):
    inspector = inspect(engine)
    pool = engine.pool
    return {
        "size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
        "invalid": pool.invalid(),
    }
```

## Backup and PITR (Point-in-Time Recovery)

### Automated Backups

Cloud SQL provides automated backups. Configure:

```bash
# Enable automated backups
gcloud sql instances patch nomos-backend \
    --project=PROJECT_ID \
    --backup-start-time=03:00 \
    --backup-retention=7  # Keep 7 days of backups
```

### Manual Backup

```bash
# Create on-demand backup
gcloud sql backups create nomos-backup-$(date +%Y%m%d) \
    --instance=nomos-backend \
    --project=PROJECT_ID \
    --description="Manual backup before deployment"
```

### Point-in-Time Recovery

PITR allows recovery to any point within the retention window.

```bash
# Restore to specific point in time
gcloud sql instances create nomos-backend-restored \
    --project=PROJECT_ID \
    --source-instance=nomos-backend \
    --restore-backup-run=BACKUP_RUN_ID \
    --restore-time="2024-01-15T14:30:00Z"
```

### PITR Drill Procedure

1. **Preparation**
   - Document current time
   - Note expected data state
   - Notify stakeholders

2. **Execution**
   ```bash
   # Create test instance from backup
   gcloud sql instances create nomos-backend-pitr-test \
       --project=PROJECT_ID \
       --source-instance=nomos-backend \
       --restore-time="2024-01-15T14:30:00Z"
   ```

3. **Verification**
   - Connect to restored instance
   - Verify data at restore point
   - Run smoke tests
   - Document results

4. **Cleanup**
   ```bash
   # Delete test instance
   gcloud sql instances delete nomos-backend-pitr-test \
       --project=PROJECT_ID
   ```

## Rollback Drill

### Scenario: Deployment Failure

1. **Identify Failure**
   - Monitor error rates
   - Check SLO breaches
   - Review logs

2. **Trigger Rollback**
   - Set `ROLLBACK_MODE=true` via Secret Manager
   - Wait 30 seconds for propagation
   - Verify rollback active

3. **Database Rollback (if needed)**
   ```bash
   # Rollback to previous migration
   alembic downgrade -1

   # Or restore from backup
   gcloud sql instances create nomos-backend-rollback \
       --project=PROJECT_ID \
       --source-instance=nomos-backend \
       --restore-backup-run=PREVIOUS_BACKUP_ID
   ```

4. **Verification**
   - Check application health
   - Verify data integrity
   - Run smoke tests
   - Monitor metrics

5. **Post-Rollback**
   - Document incident
   - Analyze root cause
   - Implement fixes
   - Plan redeployment

### Scenario: Data Corruption

1. **Identify Corruption**
   - Data validation failures
   - Inconsistent query results
   - Error reports

2. **PITR Recovery**
   ```bash
   # Restore to point before corruption
   gcloud sql instances create nomos-backend-recovered \
       --project=PROJECT_ID \
       --source-instance=nomos-backend \
       --restore-time="2024-01-15T13:00:00Z"
   ```

3. **Switch to Recovered Instance**
   - Update connection strings
   - Verify application connectivity
   - Run smoke tests

4. **Cleanup**
   - Delete corrupted instance (after verification)
   - Update DNS if needed

## Connection Failover

### Automatic Failover

Cloud SQL provides automatic failover for high availability.

```bash
# Enable high availability
gcloud sql instances patch nomos-backend \
    --project=PROJECT_ID \
    --availability-type=REGIONAL
```

### Application Failover Handling

```python
import asyncpg
from asyncpg.exceptions import ConnectionError

async def execute_with_retry(query, max_retries=3):
    for attempt in range(max_retries):
        try:
            async with pool.acquire() as conn:
                return await conn.execute(query)
        except ConnectionError as e:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
```

## Monitoring and Alerts

### Key Metrics
- **Connection pool utilization**
- **Query latency**
- **Replication lag**
- **Backup success rate**
- **Storage usage**

### Alert Thresholds
- Pool utilization > 80%
- Replication lag > 5s
- Backup failure
- Storage > 80% capacity

## Appendix: Commands

### Check Replication Status
```sql
-- On primary
SELECT * FROM pg_stat_replication;

-- On replica
SELECT * FROM pg_stat_wal_receiver;
```

### Check Connection Pool
```sql
SELECT count(*) FROM pg_stat_activity;
```

### Check Database Size
```sql
SELECT pg_size_pretty(pg_database_size('nomos'));
```

### Check Table Sizes
```sql
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

### Check Vector Index Size
```sql
SELECT
    indexname,
    pg_size_pretty(pg_relation_size(indexrelid)) AS size
FROM pg_indexes
WHERE indexname LIKE '%vector%';
```
