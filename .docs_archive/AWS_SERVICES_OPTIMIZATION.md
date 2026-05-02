# AWS Services Optimization & Limits Workarounds

**Goal:** Use AWS services creatively to overcome rate limits, compute limits, and maximize performance while optimizing cost and security.

---

## Problem Statement

### API Rate Limits
- Yahoo Finance: ~2,000 requests/hour per IP
- FRED API: 120 calls/minute
- Other providers: Variable limits
- **Current approach:** 5 sequential workers hit limits quickly
- **Current bottleneck:** Can't scale beyond 5-10 concurrent workers

### Compute Limits  
- ECS task memory: 2GB per task
- ECS task CPU: 0.5-4 vCPU limits
- Lambda: 15-minute timeout, 3GB memory
- EC2: Instance type limits and pricing
- **Current approach:** Single task per loader
- **Current bottleneck:** Can't handle very large datasets

### Cost Optimization
- RDS: Always-on database ($150-200/month baseline)
- ECS: Per-minute billing (expensive for long tasks)
- Data transfer: $0.09/GB out (expensive for large datasets)
- **Target:** 50% cost reduction while maintaining performance

### Security Concerns
- API keys in environment variables (leakage risk)
- Database credentials in task definitions
- No audit trail of data access
- No encryption of sensitive columns
- **Target:** Zero-trust architecture

---

## AWS Services Arsenal

### 1. AWS SQS (Simple Queue Service)
**Use Case:** Distribute work across workers, overcome rate limits

```
Architecture:
┌─────────────────┐
│  Symbol Queue   │ ← 10,000 symbols to fetch
└────────┬────────┘
         ↓
    [Consumer Pool]  ← 20 ECS tasks, each fetches 1 symbol/message
         ↓
    [Rate Limited]   ← Each task waits respects API limits
         ↓
      [RDS]          ← All inserts to same database
```

**Benefits:**
- Decouple symbol distribution from rate-limiting
- Auto-scale: 20 tasks processing 20 symbols = 20 parallel API calls
- Rate limiting per task (2-3 req/min each = no 429 errors)
- Automatic retry with exponential backoff
- Cost: Only pay for actual message processing

**Expected Improvement:** 5-10x throughput

### 2. AWS Lambda + EventBridge
**Use Case:** Lightweight parallel processing for small operations

```
Architecture:
EventBridge Schedule
    ↓
  Lambda Function (light processing)
    ↓
  Batch Job/SQS
    ↓
  RDS (batch insert)
```

**Benefits:**
- No container overhead (0.1-1 second startup)
- Pay only for execution milliseconds
- Auto-scaling to 1,000s of concurrent executions
- Excellent for symbol lookups, light transformations
- Cost: $0.20 per 1M requests vs ECS continuous billing

**Expected Improvement:** 3-5x cost savings on light operations

### 3. AWS Batch
**Use Case:** Handle massive parallel data processing jobs

```
Architecture:
┌──────────────────────────┐
│   AWS Batch Job Queue    │
│   (100+ parallel tasks)   │
└───────────┬──────────────┘
            ↓
    [Container Images]
            ↓
    [EC2 Compute Environment]
     (Spot instances - 90% cheaper)
            ↓
      [RDS Database]
```

**Benefits:**
- Automatic scaling of compute
- Spot instances (90% cheaper than On-Demand)
- Job scheduling and retry logic built-in
- Better than ECS for batch workloads
- Can handle 100+ parallel tasks

**Cost Comparison:**
- ECS: $0.025/hour continuous = $18/month minimum
- Batch on Spot: $0.003/hour when running = $2-3/month actual
- **Savings: 85-90%**

**Expected Improvement:** 3x cost reduction

### 4. AWS S3 + S3 Select
**Use Case:** Stage and transform data, avoid direct API rate limits

```
Architecture:
[API Data] → [S3 Bucket] → [S3 Select] → [Lambda] → [RDS]
```

**Benefits:**
- Decouple API fetching from database loading
- S3 Select: SQL queries directly on S3 data (no full load)
- Versioning: Track all data changes
- Archival: Move old data to Glacier (cheap storage)
- Parallel upload: 100 parts = 100x throughput

**Expected Improvement:** 5x throughput on large files

### 5. AWS Secrets Manager + Parameter Store
**Use Case:** Secure credential management, overcome rate limits via rotation

```
Architecture:
┌──────────────────────┐
│  Secrets Manager     │
│  - RDS password      │
│  - API keys          │
│  - FRED key          │
└──────┬───────────────┘
       ↓
   [Auto-rotation]  ← Every 30 days
       ↓
   [Audit log]      ← Who accessed what and when
       ↓
   [Encryption]     ← KMS-encrypted at rest
```

**Benefits:**
- No plaintext credentials in code
- Automatic rotation
- Audit trail for compliance
- Access control per credential
- Encryption with customer keys

**Creative Use:** Multiple API keys rotated automatically
- Maintain 3 FRED API keys
- Rotate which key is used
- Effectively 3x rate limit capacity
- Same with other providers

**Expected Improvement:** Overcome rate limit blockers

### 6. AWS RDS Read Replicas
**Use Case:** Separate read-heavy analytics from write-heavy loading

```
Architecture:
┌─────────────────────────────────────┐
│          RDS Primary                 │
│   (All writes from loaders)          │
├─────────────────────────────────────┤
│  Replica 1          │  Replica 2     │
│  (Analytics)        │  (Reporting)   │
└─────────────────────────────────────┘
```

**Benefits:**
- Loaders write to primary (no replication delay)
- Analytics/dashboards read from replica
- No performance impact on loading
- Read replica is separate billing (cheaper than second instance)

**Cost:** Read replica = $150/month, saves dashboard from blocking loaders

**Expected Improvement:** Prevent lock contention during heavy loading

### 7. AWS CloudFront + API Gateway
**Use Case:** Cache API responses, reduce external API calls

```
Architecture:
[Loader] → [CloudFront] → [Cache Hit] (no external call)
         ↓
    [Cache Miss] → [Real API] → [CloudFront] → [Cache]
```

**Benefits:**
- Cache responses from public APIs
- Dramatically reduce rate-limit hits
- Lower latency (cached responses)
- Cost: No charge for CloudFront in VPC (free!)

**Example:** Cache FRED data for 1 hour
- Fetch once at 9:00 AM
- Use cached version for 59 minutes
- 60x reduction in API calls for same data

**Expected Improvement:** 10-60x reduction in rate-limited API calls

### 8. AWS Kinesis Data Streams
**Use Case:** Real-time data ingestion and processing pipeline

```
Architecture:
[API Data] → [Kinesis Stream] → [Lambda] → [Batch] → [RDS]
             (buffering, ordering, replay)
```

**Benefits:**
- Built-in buffering and ordering
- Replay data if processing fails
- Auto-scales to 1000s of records/second
- Cost: Pay per shard ($0.033/hour = $24/month)
- Throughput: 1,000 records/sec per shard

**Expected Improvement:** Reliable data pipeline with retry

### 9. AWS EventBridge + SNS/SQS
**Use Case:** Event-driven architecture for complex workflows

```
Architecture:
GitHub Actions
    ↓
EventBridge Rule → [Phase 2 Loaders Queue]
    ↓
SNS Notifications → [Slack/Email on completion]
    ↓
Automatic Trigger → [Phase 3 loaders when Phase 2 done]
```

**Benefits:**
- Decouple components
- Sequential phase execution (Phase 2 starts when Phase 1 done)
- Notifications on completion/failure
- Cost: Very cheap ($3.50 per 1M events)

**Expected Improvement:** Automated pipeline with feedback

### 10. AWS Cost Optimization Services
**Use Case:** Achieve target cost savings (50% reduction)

| Service | Current Cost | Optimized Cost | Savings |
|---------|-------------|----------------|---------|
| RDS | $180/month | $150/month (reserved) | 17% |
| ECS | $200/month (always on) | $30/month (Batch spot) | 85% |
| Data Transfer | $50/month | $10/month (S3 caching) | 80% |
| Lambda | $0/month (not used) | -$10 (savings) | - |
| **TOTAL** | **$430/month** | **$180/month** | **58%** |

**Implementation:** 
- Switch from ECS to Batch
- Use Spot instances
- Reserved RDS capacity (1 year = 25% discount)
- S3 caching reduces external API calls

---

## Comprehensive Multi-Service Architecture

### The Optimal Data Loading Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                    GITHUB ACTIONS TRIGGER                       │
└──────────────────────────┬──────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│                    PHASE ORCHESTRATION                           │
│           (EventBridge scheduling Phase 1 → 2 → 3)              │
└──────────────────────────┬──────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│                    SYMBOL DISTRIBUTION                           │
│         (SQS Queue with 5,000 symbols for Phase 2)              │
└──────────┬──────────────────────────────────────────────────────┘
           ↓
     [100 Parallel Tasks]
           ↓
    ┌──────┴──────┐
    │             │
  [Fetch]      [API Caching]
    │             │
    └──────┬──────┘
           ↓
    [CloudFront Cache]
           ↓
    [Secrets Manager]
  (Rate limit via key rotation)
           ↓
    [S3 Staging] (optional)
           ↓
    [Batch Inserts via Lambda]
           ↓
    ┌──────────────────────┐
    │   RDS Primary        │
    │   (Write optimized)   │
    │                      │
    │  Read Replicas       │
    │  (For analytics)     │
    └──────────────────────┘
           ↓
    [SNS Notification]
    (Slack/Email)
           ↓
    [CloudWatch Metrics]
    (Performance tracking)
```

---

## Phase 2 Implementation with AWS Services

### Approach 1: Conservative (Minimal AWS Services)
```
Current ECS approach
+ Add SQS for symbol distribution
+ Add batch insert optimization
Expected: 3-4x improvement, $100/month savings
```

### Approach 2: Advanced (AWS Batch)
```
Switch from ECS to AWS Batch
+ Use Spot instances
+ Add SQS queuing
+ Add Secrets Manager rotation
Expected: 5x improvement, $250/month savings
```

### Approach 3: Aggressive (Full Multi-Service)
```
All services:
+ SQS for queueing
+ AWS Batch for compute
+ Spot instances (90% savings)
+ S3 caching layer
+ CloudFront for API caching
+ Secrets Manager with key rotation
+ EventBridge for orchestration
+ SNS for notifications
Expected: 10x improvement, $300/month savings
```

### Recommendation: Approach 2 (Advanced)
**Rationale:**
- 5x improvement is solid (better than our 7.5x goal)
- $250/month savings is significant
- Complexity is manageable
- Still uses proven ECS infrastructure base
- Can evolve to Approach 3 later if needed

---

## Security Implementation

### Zero-Trust Model
```
1. Credentials: All in Secrets Manager, none in code
2. Access: IAM roles with minimal permissions
3. Encryption: All data encrypted at rest and in transit
4. Audit: CloudTrail logs all API access
5. Network: VPC isolated, no public access to RDS
```

### Compliance Checklist
- [ ] No hardcoded credentials
- [ ] All API access logged
- [ ] Database encryption enabled
- [ ] VPC isolation configured
- [ ] IAM roles follow least privilege
- [ ] Secrets rotated automatically
- [ ] Backups encrypted
- [ ] Disaster recovery plan documented

---

## Cost Breakdown: Current vs Optimized

### Current Architecture (Monthly)
```
ECS Fargate:        $200  (always-on tasks)
RDS PostgreSQL:     $180  (on-demand pricing)
Data Transfer:      $50   (external API calls)
Secrets Manager:    $0
Lambda:             $0
S3:                 $10
Miscellaneous:      $20   (CloudFormation, logs)
─────────────────────────
TOTAL:              $460/month
```

### Optimized Architecture (Monthly)
```
AWS Batch Spot:     $30   (90% cheaper than ECS)
RDS PostgreSQL:     $135  (reserved capacity)
Data Transfer:      $5    (S3 + CloudFront caching)
Secrets Manager:    $1    (auto-rotation)
Lambda:             $5    (SQS processing)
S3:                 $15   (data staging + caching)
Miscellaneous:      $10   (monitoring, logs)
─────────────────────────
TOTAL:              $201/month
─────────────────────────
SAVINGS:            $259/month (56% reduction)
```

---

## Implementation Sequence

### Week 1: SQS + Batch Inserts
- [ ] Create SQS queue for symbols
- [ ] Implement batch insert in loaders
- [ ] Update Phase 2 loaders
- Expected: 3x improvement

### Week 2: AWS Batch Migration
- [ ] Set up Batch job queue
- [ ] Create Spot instance compute environment  
- [ ] Migrate Phase 2 loaders to Batch
- Expected: Additional 1.5x improvement

### Week 3: Secrets + Caching
- [ ] Secrets Manager auto-rotation
- [ ] CloudFront cache for API responses
- [ ] S3 staging layer
- Expected: Additional 1.5x improvement

### Week 4: Monitoring & Tuning
- [ ] CloudWatch dashboards
- [ ] Cost optimization
- [ ] Performance tuning
- Final result: 5-6x improvement, 56% cost savings

---

## Decision Matrix: Which Service to Use?

| Problem | Service | Benefit | Cost |
|---------|---------|---------|------|
| Rate Limits | SQS Queuing | 3-5x throughput | $1/month |
| High Compute | Batch + Spot | 5x speedup, 90% savings | $30/month |
| API Caching | CloudFront | 10x fewer API calls | Free in VPC |
| Credentials | Secrets Mgr | Security + audit | $1/month |
| Notifications | SNS | Real-time feedback | $0.50/month |
| Monitoring | CloudWatch | Metrics + alerting | $5/month |

---

## Conclusion

**Recommended approach:** Use AWS services strategically to:
1. **Overcome limits** via SQS queuing and key rotation
2. **Optimize compute** via Batch + Spot instances
3. **Reduce costs** by 56% while improving performance 5x
4. **Improve security** via Secrets Manager + IAM + VPC
5. **Add observability** via CloudWatch + SNS

**Timeline:** 4 weeks to full optimization  
**Cost Savings:** $259/month (56% reduction)  
**Performance:** 5-6x improvement  
**Risk:** Low (proven AWS services)  

---

*Architecture Document v1.0*  
*Prepared for Phase 2-4 Implementation*  
*Ready for approval and execution*  
