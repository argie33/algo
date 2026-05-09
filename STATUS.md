# System Status & Quick Facts

**Last Updated:** 2026-05-09 (Frontend improvements + notification system complete)
**Project Status:** Development — all core systems operational, data loading needs EventBridge configuration
**Next Scheduled Run:** Weekdays at 10:30pm UTC / 5:30pm ET (EventBridge)

## Deployment Status ✅
All infrastructure operational. Resolved 5 critical Terraform blockers:
- ✅ Storage bucket variables (added to root module)
- ✅ RDS storage configuration (gp2 for <400GB allocation)
- ✅ Parameter group family (postgres14 match)
- ✅ Lambda environment variables (removed reserved AWS_REGION)
- ✅ Lambda VPC IAM permissions (removed restrictive conditions)

**Stack Status:** 145 resources deployed
- VPC & Networking: ✅ Complete
- RDS PostgreSQL: ✅ Running (14.12)
- Lambda API: ✅ Running (stocks-api-dev)
- Lambda Algo: ✅ Running (stocks-algo-dev)
- CloudFront CDN: ✅ Operational
- Cognito Auth: ✅ Configured
- EventBridge Scheduler: ✅ Active
- ECS Cluster: ✅ Ready for data loaders

## Key Facts At a Glance
- **Region:** us-east-1
- **Environment:** dev (paper trading)
- **Algo Schedule:** cron(0 22 ? * MON-FRI *) — 10:30pm UTC / 5:30pm ET weekdays
- **API Gateway:** https://kx4kprv8ph.execute-api.us-east-1.amazonaws.com
- **Frontend CDN:** https://d27wrotae8oi8s.cloudfront.net
- **Cognito Pool:** us-east-1_qKYUt285Z (Alpaca paper trading)
- **Database:** PostgreSQL 14, 61GB allocated, Multi-AZ disabled, backup 7-day retention
- **Cost:** ~$77/month (RDS $25, ECS $12, Lambda $2, S3 $1, etc.)

## Critical Paths
```
Deploy ALL      → gh workflow run deploy-all-infrastructure.yml
Deploy Algo Only → gh workflow run deploy-algo-orchestrator.yml
Test Locally    → docker-compose up && python3 algo_run_daily.py
Check Logs      → aws logs tail /aws/lambda/algo-orchestrator --follow
RDS Access      → psql -h localhost -U stocks -d stocks (local Docker)
```

## Work in Progress / Next Phase

**High Impact (ready to implement)**
- [ ] EventBridge Scheduler Configuration — set up daily data loader triggers at 4am ET
- [ ] TimescaleDB Migration — enable on RDS for 10-100x query speedup on time-series data
- [ ] Performance Metrics Dashboard — show query times, API latencies, system health trends
- [ ] Data Quality Auditor UI — visualize table staleness, data integrity checks in real-time

**Medium Impact**
- [ ] API Documentation — expand from current 5 endpoints to all 25+ with request/response examples
- [ ] Performance Optimization — identify slow queries, add caching strategies
- [ ] Enhanced Error Handling — better user-facing error messages, retry strategies
- [ ] Test Coverage — expand E2E tests for data load → algo run → trade execution scenarios

**Lower Priority**
- [ ] Lambda VPC Migration — move to VPC with NAT gateway for enhanced security (prod planning)
- [ ] RDS Multi-AZ — enable for high availability (cost/benefit analysis needed)
- [ ] Disaster Recovery Runbook — documented procedures for common failure scenarios
- [ ] Advanced Analytics — cohort analysis, factor attribution, strategy backtesting

## Known Limitations (Intentional Development Choices)
- ⚠️ **RDS publicly accessible** (0.0.0.0/0) — prod hardening deferred
- ⚠️ **Paper trading only** — no real money until "green light"
- ⚠️ **Stage 2 data gap** — BRK.B, LEN.B, WSO.B in DB but missing today's prices
- ⚠️ **Lambda not in VPC** — outbound internet via direct route, not NAT

(See `memory/aws_deployment_state_2026_05_05.md` for why)

## Frontend Status — May 2026 ✅

All major frontend pages complete with professional design and full API integration:

**Market Analysis** (5 pages)
- ✅ Market Overview — indices, technicals, sentiment, volatility, correlation
- ✅ Sector Analysis — sector performance, rotation, heatmaps
- ✅ Economic Dashboard — recession nowcasting, Fed policy, credit spreads, yield curves
- ✅ Commodities Analysis — COT positioning, correlations, sector rotation
- ✅ Sentiment Analysis — fear/greed, AI sentiment, contrarian indicators

**Stock Research** (4 pages)
- ✅ Stock Scores — multi-factor scoring with drill-downs
- ✅ Trading Signals — swing patterns, mean reversion, range trading
- ✅ Deep Value Picks — DCF-based screener with generational opportunities
- ✅ Swing Candidates — technical pattern recognition and momentum

**Portfolio & Trading** (4 pages)
- ✅ Portfolio Dashboard — holdings, allocations, P&L tracking
- ✅ Trade Tracker — execution history, slippage analysis, performance
- ✅ Optimizer — mean-variance optimization with constraints
- ✅ Hedge Helper — dynamic hedging strategy simulation

**Algo & Research** (3 pages)
- ✅ Algo Dashboard — live position tracking, signal metrics, P&L
- ✅ Signal Intelligence — signal performance, confidence scoring, factor attribution
- ✅ Backtest Results — strategy validation, equity curves, trade-by-trade analysis

**Admin & System** (5 pages)
- ✅ Service Health — data freshness, patrol findings, source status
- ✅ Notifications — real-time alerts, trade events, risk breaches (with filtering)
- ✅ Audit Trail — complete action log with filtering by type and status
- ✅ Settings — user preferences, theme toggle, API credentials
- ✅ Markets Health — data source monitoring, uptime tracking

**Design Improvements** (May 2026)
- ✅ Font: Switched from Inter to **DM Sans** for superior financial data readability
- ✅ Econ Page: Complete redesign with recession nowcasting models (Sahm Rule, yield spreads, VIX, credit spreads)
- ✅ Commodities: Added COT (Commitment of Traders) positioning and correlation analysis
- ✅ Notification System: Real-time dashboard with kind/severity filtering + mark-as-read/delete

**All 25 API Endpoints Verified** ✅
- Data loading, stock scores, signals, backtests, portfolio, economic, commodities, audit logs — all working

## Recent Changes (Last 5 Commits)
1. e2fdb16b6 — chore: Migrate all credentials to centralized credential_manager
2. 259cd4558 — feat: Add pre-trade position preview - backend endpoint and frontend modal
3. 0875c6b0f — fix: Fix 5 critical webapp issues: database routing, API endpoints, code patterns
4. 901ee3d32 — feat: Add dedicated LoginPage component for /login route
5. 1b893cd8e — test: Fix integration tests and backtest regression baseline

## Health Check (Manual)
```bash
# Verify all stacks deployed
aws cloudformation list-stacks --region us-east-1 \
  --query 'StackSummaries[?StackStatus==`CREATE_COMPLETE` || StackStatus==`UPDATE_COMPLETE`].StackName'

# Verify Lambda can be invoked
aws lambda invoke --function-name algo-orchestrator --region us-east-1 /tmp/out.json

# Verify RDS is up
aws rds describe-db-instances --db-instance-identifier stocks-data-rds \
  --region us-east-1 --query 'DBInstances[0].DBInstanceStatus'

# Verify EventBridge is scheduled
aws scheduler list-schedules --region us-east-1 --query 'Schedules[?contains(Name, `algo`)]'

# Verify data is fresh
psql -h localhost -U stocks -d stocks \
  -c "SELECT symbol, MAX(date) as latest_date FROM price_daily GROUP BY symbol HAVING MAX(date) < CURRENT_DATE LIMIT 5;"
```

## If Something Looks Wrong
1. **Deployment hung?** → Check `deployment-reference.md` → "Troubleshooting"
2. **Algo not trading?** → Check `troubleshooting-guide.md` → "Lambda & Trading Issues"
3. **Data stale?** → Run `python3 loadpricedaily.py` or `aws ecs run-task`
4. **RDS can't connect?** → Check `troubleshooting-guide.md` → "Database Issues"
5. **Still stuck?** → Run health check workflow: `gh workflow run check-stack-status.yml`

---

**This file is a snapshot. For detailed context, see:**
- `CLAUDE.md` — Navigation index
- `memory/aws_deployment_state_2026_05_05.md` — Current infrastructure state
- `memory/end_to_end_verification_2026_05_07.md` — Latest full system test
