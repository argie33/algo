# System Status & Quick Facts

**Last Updated:** 2026-05-07
**Next Scheduled Run:** Daily at 5:30pm ET (EventBridge)

## Deployment Status ✅
```
stocks-bootstrap        CREATE_COMPLETE  (one-time, skip)
stocks-core             CREATE_COMPLETE  (VPC, networking, ECR, S3)
stocks-app-stocks       CREATE_COMPLETE  (RDS, ECS, Secrets)
stocks-app-ecs-tasks    CREATE_COMPLETE  (39 loader task defs)
stocks-webapp-lambda    CREATE_COMPLETE  (REST API)
stocks-algo-orchestrator CREATE_COMPLETE  (Trading engine, EventBridge)
```

## Key Facts At a Glance
- **Region:** us-east-1
- **Cost:** ~$77/month (RDS $25, ECS $12, Lambda $2, S3 $1, etc.)
- **Algo:** Runs weekdays 5:30pm ET (post-market)
- **Latest Trades:** See `algo_trades` table (50+ executed, synced to Alpaca)
- **Data:** 21M+ price rows, 800k+ signals, updated daily
- **Frontend:** React + Vite, CloudFront CDN, Cognito auth

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
1. c685e9384 — Refactor: Optimize CLAUDE.md for token efficiency
2. a0d9bb57d — Fix: VPC check logic in deploy-core workflow
3. 9d0599711 — Verification: End-to-end test with real Alpaca integration complete
4. 47e952e5e — Fix: Ensure critical import and Alpaca client fixes are applied
5. 1894ad581 — Fix: AWS CLI syntax and comprehensive tool documentation

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
