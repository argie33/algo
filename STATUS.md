# System Status & Quick Facts

**Last Updated:** 2026-05-08 (Deployment blockers resolved)
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

## Known Limitations (Intentional Development Choices)
- ⚠️ **RDS publicly accessible** (0.0.0.0/0) — prod hardening deferred
- ⚠️ **Paper trading only** — no real money until "green light"
- ⚠️ **Stage 2 data gap** — BRK.B, LEN.B, WSO.B in DB but missing today's prices
- ⚠️ **Lambda not in VPC** — outbound internet via direct route, not NAT

(See `memory/aws_deployment_state_2026_05_05.md` for why)

## Recent Changes (Last 5 Commits)
1. f147d5a3a — iac: Fix Terraform deployment blockers and verify infrastructure
2. 768929395 — workflows: Add data population + integration testing + schema init
3. cf4cdbf7a — iac: Complete IaC-first implementation plan + local dev setup
4. a4d9bb404 — schema: Create comprehensive 60+ table database schema
5. 649aa93a6 — Fix: Terraform configuration errors and deploy infrastructure

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
