# AWS Deployment Guide — Complete Checklist

This guide provides step-by-step instructions to deploy the algo system to AWS and validate it works with full production data.

## Pre-Deployment Validation

Before pushing to AWS, run the production readiness check locally:

```bash
python -c "
import sys
sys.path.insert(0, '.')
from utils.production_readiness_check import ProductionReadinessCheck
checker = ProductionReadinessCheck()
result = checker.run_all_checks()
"
```

Expected result: **5+ checks passing, 0-2 warnings, 0 failures** for production deployment.

---

## Phase 1: AWS Infrastructure Setup

### 1.1 Database (RDS PostgreSQL)
- [ ] RDS instance created (db.t4g.small, 2GB RAM recommended)
- [ ] Database schema applied: `python lambda/db-init/init_db.py`
- [ ] Connection pool: 100 max connections, statement_timeout 15m
- [ ] Verify connectivity: `python -c "from utils.database_context import DatabaseContext; DatabaseContext('read').__enter__()"`

### 1.2 AWS Secrets Manager
- [ ] algo/database: DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
- [ ] algo/alpaca: APCA_API_KEY_ID, APCA_API_SECRET_KEY (paper mode by default)
- [ ] algo/fred: FRED_API_KEY
- [ ] Rotation schedule: Quarterly (first Monday)

### 1.3 DynamoDB
- [ ] Table `algo_orchestrator_state` created
  - [ ] Partition key: `key` (String)
  - [ ] TTL: enabled on `TTL` attribute (600s default)
- [ ] Verify connectivity: `python -c "from utils.dynamodb_health_check import DynamoDBHealthCheck; DynamoDBHealthCheck().check_dynamodb_connectivity()"`

### 1.4 Lambda Functions
- [ ] `algo-orchestrator` Lambda (512MB, 600s timeout)
  - [ ] Environment variables: AWS_REGION, HALT_FLAG_TABLE, DATA_FRESHNESS_MAX_HOURS
  - [ ] IAM role: RDS proxy access, DynamoDB read/write, CloudWatch logs
- [ ] `algo-api` Lambda (256MB, 28s timeout, 1 provisioned concurrency)
  - [ ] Environment variables: COGNITO_CLIENT_ID, COGNITO_USER_POOL_ID, COGNITO_REGION
  - [ ] VPC endpoints configured for RDS proxy

### 1.5 Cognito User Pool
- [ ] User pool created with admin and trader groups
- [ ] App client created (record CLIENT_ID)
- [ ] Environment variable: `COGNITO_CLIENT_ID=<your-client-id>`
- [ ] Environment variable: `COGNITO_USER_POOL_ID=<your-pool-id>`
- [ ] Verify: Run `/api/health/cognito` endpoint → should return validation result

### 1.6 EventBridge Scheduler Rules
- [ ] `algo-morning-pipeline`: 2:00 AM ET Mon-Fri (Step Functions)
- [ ] `algo-afternoon-update`: 12:50 PM ET Mon-Fri (ECS task)
- [ ] `algo-preclose-update`: 2:50 PM ET Mon-Fri (ECS task)
- [ ] `algo-eod-pipeline`: 4:05 PM ET Mon-Fri (Step Functions)
- [ ] `algo-orchestrator` schedules: 9:30 AM, 1 PM, 3 PM, 5:30 PM ET Mon-Fri

### 1.7 ECS Cluster & Task Definitions
- [ ] ECS Fargate cluster `algo-cluster` created
- [ ] Task definitions for all loaders (load_prices, load_technical_data, load_swing_scores, etc.)
- [ ] Environment variables:
  - [ ] LOADER_INTERVALS: "1d,1wk,1mo"
  - [ ] LOADER_ASSET_CLASSES: "stock,etf"
  - [ ] LOADER_PARALLELISM: start with 2, scale based on RDS load
  - [ ] INTRADAY_MODE: "false" for morning prep, "true" for afternoon/preclose updates

### 1.8 CloudWatch Monitoring
- [ ] Log groups created: `/ecs/algo-orchestrator`, `/ecs/algo-api`, `/ecs/algo-loaders`
- [ ] Alarms configured:
  - [ ] RDS connection pool >80% (DatabaseConnections metric)
  - [ ] Lambda orchestrator >10 min execution time
  - [ ] SLA violations (Phase 1 after 9:30 AM, pre-close after 3:15 PM)
  - [ ] Loader failures (3+ consecutive failures)

---

## Phase 2: Data Validation

### 2.1 Load Initial Data
```bash
# Load historical prices (1 week)
python loaders/load_prices.py --days 7

# Load technical indicators
python loaders/load_technical_data_daily_vectorized.py --limit 500

# Load swing trader scores
python loaders/load_swing_trader_scores_vectorized.py --limit 500
```

Expected: 
- [ ] No errors in CloudWatch logs
- [ ] Rows inserted into price_daily, technical_data_daily, swing_trader_scores
- [ ] Duration <10 minutes for 500 symbols

### 2.2 Verify Data Freshness
```bash
python -c "
from utils.sla_monitor import SLAMonitor
sla = SLAMonitor.get_current_sla_window()
print('SLA Window:', sla['name'] if sla else 'None')
"
```

Expected: System identifies current pipeline window (morning_prep, afternoon_update, etc.)

### 2.3 Check Loader Health
```bash
python -c "
from utils.loader_conflict_detector import LoaderConflictDetector
detector = LoaderConflictDetector()
status = detector.check_intraday_pipeline_readiness()
print('Morning Complete:', status['morning_pipeline_done'])
print('Ready for Afternoon:', status['ready_for_afternoon_update'])
"
```

Expected: 
- [ ] morning_pipeline_done = True
- [ ] ready_for_afternoon_update = True

---

## Phase 3: Full Data Load (5000+ Symbols)

### 3.1 Load Full Symbol Count
```bash
# Morning prep: full 5000+ symbols (expect 5-5.5 hours)
python loaders/load_prices.py  # Will auto-fetch all active symbols

# Verify SLA: should complete before 9:30 AM ET
# Check CloudWatch logs for: "[PHASE 1] PASS [SLA OK: Xm buffer until 9:30 AM]"
```

Expected:
- [ ] Completes by 9:30 AM (7.5h from 2:00 AM start)
- [ ] 5000+ symbols loaded into price_daily
- [ ] 75%+ coverage vs prior day
- [ ] RDS connection pool <80% utilized during load

### 3.2 Test Intraday Updates
```bash
# Afternoon update (12:50 PM): fast intraday mode
python loaders/load_swing_trader_scores_vectorized.py --intraday

# Must complete by 1:05 PM (15 minute SLA)
```

Expected:
- [ ] Completes in 5-15 minutes
- [ ] SLA buffer: [SLA OK: Xm buffer]
- [ ] 1 PM orchestrator uses fresh scores

### 3.3 Test Pre-Close Update
```bash
# Pre-close update (2:50 PM): fast intraday mode
python loaders/load_technical_data_daily_vectorized.py --intraday

# Must complete by 3:15 PM (25 minute SLA)  
```

Expected:
- [ ] Completes in <15 minutes
- [ ] SLA buffer: [SLA OK: Xm buffer]
- [ ] 3 PM orchestrator uses fresh technical data

### 3.4 Test EOD Pipeline
```bash
# EOD pipeline (4:05 PM): full daily load for overnight processing
# Runs automatically via Step Functions at 4:05 PM
```

Expected:
- [ ] Completes by 5:30 PM (85 minute SLA)
- [ ] All 5000+ symbols loaded for next day
- [ ] RDS connection pool <80% during peak load

---

## Phase 4: Orchestrator Validation

### 4.1 Test Morning Orchestrator (9:30 AM)
```
Expected execution:
- Phase 1: Data freshness check → PASS (all tables <1d old)
- Phase 2: Circuit breakers → all clear
- Phase 3: Position monitor → PASS
- Phase 4: Execute exits → processes open positions
- Phase 5: Signal generation → generates buy/sell signals
- Phase 6: Trade entries → executes new trades (dry-run mode)
- Phase 7: Reconciliation → updates P&L and metrics
```

Success criteria:
- [ ] All 7 phases complete in <60 seconds
- [ ] No errors in orchestrator logs
- [ ] Signal quality scores updated
- [ ] Positions table updated

### 4.2 Test Afternoon Orchestrator (1 PM)
```
Expected execution:
- Phase 1: Data freshness (uses fresh intraday scores from 12:50 PM update)
- Phase 2-7: Same as morning, but with updated market data
```

Success criteria:
- [ ] Orchestrator uses 12:50 PM score update (not 2 AM scores)
- [ ] Technical data reflects 1 PM market state
- [ ] All phases complete <60s

### 4.3 Test Pre-Close Orchestrator (3 PM)
```
Expected execution:
- Phase 1: Data freshness (uses fresh technical data from 2:50 PM update)
- Phase 4: Execute exits (closes losing positions before 4 PM close)
- Phase 5-6: Generate/execute signals with updated data
```

Success criteria:
- [ ] Phase 1 passes SLA check (3:15 PM deadline not exceeded)
- [ ] Exits execute for any losing positions
- [ ] All phases complete <60s

---

## Phase 5: Circuit Breaker Validation

### 5.1 Validate Thresholds Match Risk Tolerance
```bash
python -c "
from algo.algo_circuit_breaker import CircuitBreaker
from algo.algo_config import get_config
config = get_config()
cb = CircuitBreaker(config)
print('Drawdown threshold:', config.get('halt_drawdown_pct', 20), '%')
print('Daily loss:', config.get('max_daily_loss_pct', 2), '%')
print('Max consecutive losses:', config.get('max_consecutive_losses', 3))
"
```

Verify:
- [ ] Drawdown ≥20% (adjust if needed for risk profile)
- [ ] Daily loss ≥2% (adjust if needed)
- [ ] Consecutive losses ≥3 (adjust if needed)
- [ ] VIX threshold ≥35
- [ ] Win rate floor ≥40%

---

## Phase 6: API Validation

### 6.1 Test Health Endpoints
```bash
# Basic health check (no auth required)
curl https://<your-api>/api/health

# Expected: 200 OK with connection pool, freshness, route status

# Cognito validation (deployment blocker if fails)
curl https://<your-api>/api/health/cognito

# Expected: 200 OK, client ID matches Cognito user pool
```

### 6.2 Test Data Endpoints  
```bash
# Get current scores (requires auth)
curl -H "Authorization: Bearer <jwt-token>" \
  https://<your-api>/api/scores

# Expected: 200 OK, returns 50-150 signals with quality scores
```

---

## Phase 7: Production Go-Live Checklist

Before switching to live trading:

- [ ] All 6 SLA windows consistently met (morning prep, afternoon, preclose, EOD)
- [ ] RDS connection pool never exceeds 80% utilization
- [ ] No loader conflicts or stuck processes (monitor via CloudWatch)
- [ ] Circuit breakers tested with realistic portfolio swings
- [ ] API rate limiting handled gracefully (yfinance, IEX, FRED)
- [ ] Cognito authentication verified for all protected endpoints
- [ ] DynamoDB halt flag and state management working reliably
- [ ] CloudWatch alarms firing correctly for all critical metrics
- [ ] Daily P&L reconciliation matches Alpaca data
- [ ] Position tracking accurate for entries and exits

### Switch to Live Trading
```bash
# Change from paper to live trading
terraform apply -var="alpaca_paper_trading=false"

# Verify live mode
python -c "
import os
print('Paper trading:', os.getenv('ALPACA_PAPER_TRADING', 'Not set'))
"
```

---

## Troubleshooting

### SLA Violation: "Phase 1 after 9:30 AM"
```
Cause: Morning prep pipeline didn't complete by 9:30 AM
Fix: 
1. Check CloudWatch logs for slow loaders
2. Reduce LOADER_PARALLELISM if RDS >80%
3. Increase morning prep start time (move from 2:00 AM to 1:30 AM)
```

### RDS Connection Pool Saturation
```
Cause: Parallel loaders exceed connection limits
Fix:
1. Reduce LOADER_PARALLELISM in ECS task definition
2. Check for slow queries: use RDS Performance Insights
3. Increase RDS instance size (t4g.medium has 200 connections)
```

### yfinance Rate Limiting
```
Cause: Too many concurrent API calls to yfinance
Fix:
1. Batch size auto-reduces on 429 errors
2. Check load_prices.py logs for rate limit messages
3. Manual fallback: reduce LOADER_PARALLELISM to 1
```

### Cognito Validation Fails
```
Cause: COGNITO_CLIENT_ID doesn't match user pool
Fix:
1. Get actual client ID: AWS Cognito console → App clients
2. Update Lambda environment variable
3. Run /api/health/cognito to verify
```

---

## Monitoring Dashboard

After deployment, create CloudWatch dashboard with:

1. **SLA Compliance**
   - Morning prep completion time (target: before 9:30 AM)
   - Afternoon update completion time (target: before 1:05 PM)
   - Pre-close update completion time (target: before 3:15 PM)
   - EOD pipeline completion time (target: before 5:30 PM)

2. **RDS Health**
   - Active connections (alarm if >80)
   - Statement timeout count
   - Database CPU/memory utilization

3. **Orchestrator**
   - Execution time per phase
   - Circuit breaker status
   - Halt flag state

4. **API**
   - Request count
   - Error rate
   - P99 latency

5. **Data Freshness**
   - Price data age
   - Technical indicators age
   - Signal scores age

---

## Success Criteria

System is ready for production when:

✅ All 6 SLA windows consistently met (5+ days of successful runs)  
✅ RDS pool utilization never exceeds 80%  
✅ No loader conflicts or stuck processes  
✅ API endpoints respond <500ms (p99)  
✅ All circuit breakers tested and validated  
✅ Cognito authentication working for all protected endpoints  
✅ DynamoDB state management reliable  
✅ Daily P&L reconciliation accurate  
✅ 30+ days of backtesting shows positive P&L  

---

For more details, see:
- `steering/algo.md` - System architecture and constraints
- `REMAINING_ISSUES.md` - Outstanding issues and workarounds
- CloudWatch logs - Real-time system state
