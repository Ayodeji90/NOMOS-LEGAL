# NOMOS v2 - Week 15 Cost Report

**Date**: 2026-09-12
**Role**: Platform Lead (E1)
**Week**: Week 15 of 15-Week Implementation Plan

## Executive Summary

This report documents the cost structure of the NOMOS v2 backend prototype for South Africa (ZA) and Nigeria (NG) jurisdictions, focusing on production-ready infrastructure costs and scale risks for GA planning.

## Cost Breakdown by Service

### Vertex AI Costs

#### Generation Costs by Role
| Role | Model | Requests/Month | Cost/1K Tokens | Monthly Cost |
|------|-------|----------------|----------------|--------------|
| Writer | Gemini Pro | 50,000 | $0.00025 | $12,500 |
| Understanding | Gemini Flash | 100,000 | $0.000075 | $7,500 |
| Rerank | Gemini Flash | 200,000 | $0.000075 | $15,000 |
| NLI | Gemini Flash | 150,000 | $0.000075 | $11,250 |
| Embedding | text-embedding-005 | 500,000 | $0.00002 | $10,000 |
| **Total Vertex AI** | | | | **$56,250** |

#### Notes
- Costs based on estimated query volume of 50,000 searches/month
- Writer dominates cost due to longer responses
- Rerank cost significant due to batch processing of top-50 results
- Embedding cost includes initial corpus embedding + re-embeds for updates

### Cloud SQL Costs

#### Instance Costs
| Component | Tier | vCPU | Memory | Monthly Cost |
|-----------|------|----- |--------|--------------|
| Primary Instance | db-custom-4-15360 | 4 | 15 GB | $400 |
| Read Replica | db-custom-2-7680 | 2 | 7.5 GB | $200 |
| **Total Instance** | | | | **$600** |

#### Storage Costs
| Component | Size | Cost/GB | Monthly Cost |
|-----------|------|---------|--------------|
| Data Storage | 500 GB | $0.10 | $50 |
| Backup Storage | 350 GB | $0.10 | $35 |
| Vector Index Memory | 100 GB | $0.10 | $10 |
| **Total Storage** | | | **$95** |

#### Network Costs
| Component | Egress GB | Cost/GB | Monthly Cost |
|-----------|-----------|---------|--------------|
| Database Egress | 100 GB | $0.12 | $12 |
| **Total Network** | | | **$12** |

**Total Cloud SQL: $707/month**

### Memorystore Redis Costs

| Component | Tier | Memory | Monthly Cost |
|-----------|------|--------|--------------|
| Redis Instance | Standard | 6 GB | $150 |
| **Total Redis** | | | **$150/month** |

### Firestore Costs

| Component | Operations | Cost | Monthly Cost |
|-----------|------------|------|--------------|
| Storage | 10 GB | $0.18/GB | $1.80 |
| Reads | 1M | $0.06/100K | $0.60 |
| Writes | 500K | $0.18/100K | $0.90 |
| Deletes | 100K | $0.02/100K | $0.02 |
| **Total Firestore** | | | **$3.32/month** |

### Cloud Storage Costs

| Component | Class | Size | Cost/GB | Monthly Cost |
|-----------|-------|------|---------|--------------|
| Corpus Storage | Standard | 200 GB | $0.020 | $4.00 |
| Archive Storage | Nearline | 500 GB | $0.010 | $5.00 |
| Class A Operations | | 10M | $0.005/1K | $50.00 |
| Class B Operations | | 50M | $0.0005/1K | $25.00 |
| **Total GCS** | | | | **$84.00/month** |

### Cloud Run Costs

| Component | vCPU | Memory | Requests | Monthly Cost |
|-----------|----- |--------|----------|--------------|
| API Service | 2 vCPU avg | 4 GB avg | 1M | $300 |
| Ingestion Job | 4 vCPU | 8 GB | 100 runs | $100 |
| **Total Cloud Run** | | | | **$400/month** |

### Cloud Logging Costs

| Component | Ingestion GB | Cost/GB | Monthly Cost |
|-----------|--------------|---------|--------------|
| Log Ingestion | 50 GB | $0.50 | $25.00 |
| **Total Logging** | | | **$25/month** |

### Artifact Registry Costs

| Component | Storage GB | Cost/GB | Monthly Cost |
|-----------|------------|---------|--------------|
| Image Storage | 50 GB | $0.10 | $5.00 |
| **Total Registry** | | | **$5/month** |

## Total Monthly Cost Summary

| Service | Monthly Cost | % of Total |
|---------|--------------|------------|
| Vertex AI | $56,250 | 96.5% |
| Cloud SQL | $707 | 1.2% |
| Cloud Run | $400 | 0.7% |
| GCS | $84 | 0.1% |
| Redis | $150 | 0.3% |
| Firestore | $3 | 0.0% |
| Logging | $25 | 0.0% |
| Registry | $5 | 0.0% |
| **Grand Total** | **$58,624** | **100%** |

## Scale Risks

### Query Volume Scaling
- **Current**: 50,000 searches/month
- **10x Scale**: 500,000 searches/month → Vertex AI cost: ~$562,500/month
- **100x Scale**: 5M searches/month → Vertex AI cost: ~$5.6M/month

**Mitigation**:
- Implement result caching to reduce LLM calls
- Use smaller models for understanding/rerank where quality permits
- Consider open-weight models for high-volume, lower-quality requirements
- Implement query deduplication

### Corpus Size Scaling
- **Current**: 500 GB (ZA + NG)
- **Additional Jurisdictions**: Each new jurisdiction adds ~100-200 GB
- **Vector Index Memory**: Grows linearly with corpus size

**Mitigation**:
- Use tiered storage (hot/cold) for older versions
- Implement corpus pruning for repealed sections
- Consider partitioning by jurisdiction for larger deployments

### Embedding Costs
- **Initial Embedding**: One-time cost per corpus
- **Re-embedding**: Required for model updates or corpus changes
- **Cost Impact**: $10,000 per full re-embed of current corpus

**Mitigation**:
- Batch re-embeds during off-peak hours
- Use incremental re-embedding for partial updates
- Cache embeddings to avoid recomputation

## Cost Optimization Opportunities

### Short-term (Prototype Phase)
1. **Result Caching**: Cache common queries for 1-24 hours → 20-30% reduction in Vertex AI costs
2. **Query Deduplication**: Identify and cache duplicate queries → 5-10% reduction
3. **Tiered Models**: Use Flash for understanding, Pro only for writer → Already implemented
4. **Batch Processing**: Batch rerank requests → Already implemented

### Medium-term (GA Phase)
1. **Open-Weight Models**: Evaluate local models for understanding/rerank → 40-60% cost reduction
2. **Vector Index Optimization**: Tune HNSW parameters for memory efficiency → 10-20% DB cost reduction
3. **Read Replica Scaling**: Scale replicas based on read load → Optimize Cloud SQL costs
4. **Log Sampling**: Sample logs instead of full ingestion → 50% logging cost reduction

### Long-term (Scale Phase)
1. **Model Distillation**: Distill Pro to smaller custom model → 50-70% writer cost reduction
2. **Edge Caching**: Cache results at edge locations → Reduce latency and compute
3. **Multi-tenant Architecture**: Share infrastructure across customers → Economies of scale
4. **Reserved Instances**: Use reserved compute for predictable workloads → 30-50% Cloud Run cost reduction

## GA Backlog

### High Priority
1. **Cost Monitoring Dashboard**: Real-time cost tracking by service and jurisdiction
2. **Budget Alerts**: Automated alerts when costs exceed thresholds
3. **Cost Attribution**: Per-customer cost tracking for billing
4. **Optimization Pipeline**: Automated cost optimization recommendations

### Medium Priority
1. **Open-Weight Model Evaluation**: Test local models for cost reduction
2. **Caching Strategy**: Implement multi-level caching (Redis, CDN, edge)
3. **Storage Tiering**: Implement hot/cold storage for corpus data
4. **Reserved Capacity**: Evaluate reserved instances for production

### Low Priority
1. **Model Distillation**: Distill Pro to smaller custom model
2. **Edge Deployment**: Deploy to edge locations for latency reduction
3. **Multi-tenant Architecture**: Design for shared infrastructure
4. **Custom Hardware**: Evaluate GPU instances for embedding/rerank

## Recommendations

### For Prototype Acceptance
1. **Acceptable Cost**: $58,624/month is acceptable for prototype phase
2. **Monitor Closely**: Track actual costs vs estimates
3. **Implement Caching**: Add result caching to reduce Vertex AI costs
4. **Plan for Scale**: Document scale risks and mitigation strategies

### For GA Planning
1. **Cost Model**: Develop detailed cost model based on actual usage
2. **Pricing Strategy**: Determine pricing based on cost structure
3. **Optimization Roadmap**: Prioritize cost optimization initiatives
4. **Scale Testing**: Load test at 10x scale to validate cost projections

## Appendix: Cost Tracking Commands

### Monitor Vertex AI Costs
```bash
gcloud billing budgets describe --billing-account-id=BILLING_ACCOUNT_ID
```

### Monitor Cloud SQL Costs
```bash
gcloud sql instances describe nomos-backend --format="value(cost)"
```

### Monitor Cloud Run Costs
```bash
gcloud monitoring time-series-list \
    --metric-type=run.googleapis.com/container/instance/cpu/utilization
```

### Generate Cost Report
```bash
python scripts/cost_snapshot.py --project PROJECT_ID --environment prod
```
