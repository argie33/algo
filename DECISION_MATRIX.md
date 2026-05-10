# Decision Matrix — "I want to change X, which file do I edit?"

Quick reference for "where does this change go?"

## Code Changes

| What You Want | File(s) to Edit | Then... | Deploy With |
|---------------|-----------------|---------|-------------|
| **Change algo entry/exit logic** | `algo_exit_engine.py`, `algo_trade_executor.py` | Test: `python3 algo_run_daily.py` | Auto (push to main) |
| **Change signal filters** | `algo_filter_pipeline.py`, `algo_advanced_filters.py` | Test locally | Auto |
| **Change position sizing/risk** | `algo_governance.py`, `algo_circuit_breaker.py` | Test locally | Auto |
| **Change data quality checks** | `algo_data_freshness.py`, `algo_data_patrol.py` | Test locally | Auto |
| **Add alert/monitoring** | `algo_alerts.py`, `algo_audit_log.py` | Test locally | Auto |
| **Change REST API endpoint** | `webapp/lambda/routes/stocks.js` | Test: `npm run dev` | `gh workflow run deploy-webapp.yml` |
| **Change frontend UI** | `webapp/frontend/src/pages/*.jsx` | Test: `npm run dev` | `gh workflow run deploy-webapp.yml` |
| **Fix data loader** | `load<NAME>.py` (e.g., `loadpricedaily.py`) | Test: run loader locally | Auto (ECS task updates on next run) |
| **Add market calendar rule** | `algo_market_calendar.py` | Test locally | Auto |
| **Add database audit field** | `algo_orchestrator.py` (Phase 7) or `init_db.sql` | Test locally | Auto (Lambda init on first run) |

## Infrastructure Changes

| What You Want | Template to Edit | Then... | Deploy With |
|---------------|------------------|---------|-------------|
| **Change VPC/networking** | `template-core.yml` | Validate: `aws cloudformation validate-template --template-body file://template-core.yml` | Auto (workflow triggers) |
| **Change RDS config** | `template-app-stocks.yml` | Validate | Auto |
| **Change ECS cluster** | `template-app-stocks.yml` | Validate | Auto |
| **Add/remove loader tasks** | `template-app-ecs-tasks.yml` | Validate | Auto |
| **Change Lambda timeout/memory** | `template-webapp-lambda.yml` or `template-algo-orchestrator.yml` | Validate | Auto |
| **Change EventBridge schedule** | `template-algo-orchestrator.yml` | Validate | Auto |
| **Add S3 bucket** | `template-core.yml` | Validate | Auto |
| **Add Secrets Manager secret** | `template-app-stocks.yml` | Validate | Auto |
| **Change IAM permissions** | Appropriate `template-*.yml` | Validate | Auto |

## Workflow Changes

| What You Want | File(s) to Edit | Then... | Deploy With |
|---------------|------------------|---------|-------------|
| **Change deploy steps** | `.github/workflows/deploy-*.yml` | Dry-run: `gh workflow run deploy-X.yml --dry-run` | Manually trigger: `gh workflow run deploy-X.yml` |
| **Add CI test** | `.github/workflows/ci-*.yml` | Test locally first | Auto (on push to main) |
| **Change notification alert** | `.github/workflows/deploy-*.yml` | Test | Manual trigger |
| **Add cleanup job** | `.github/workflows/cleanup-*.yml` | Test | Manual trigger |

## Configuration Changes

| What You Want | File to Edit | Then... |
|---------------|--------------|---------|
| **Change algo config (thresholds, limits)** | `algo_config.py` | Test: `python3 algo_run_daily.py` |
| **Change environment variables** | `.env.local` (local) or Secrets Manager (AWS) | Restart Lambda |
| **Change database credentials** | `.env.local` (local) or `template-app-stocks.yml` (AWS) | Restart service |
| **Change Alpaca config** | `algo_config.py` or Secrets Manager | Restart Lambda |

## Documentation Changes

| What You Want | File to Edit | Impact |
|---------------|--------------|--------|
| **Update deployment instructions** | `deployment-reference.md` | No deploy needed |
| **Update local setup** | `development-workflows.md` | No deploy needed |
| **Update troubleshooting** | `troubleshooting-guide.md` | No deploy needed |
| **Update AWS CLI reference** | `tools-and-access.md` | No deploy needed |
| **Update architecture overview** | `algo-tech-stack.md` | No deploy needed |
| **Update CLAUDE.md navigation** | `CLAUDE.md` | No deploy needed |

## Test Command Reference

| Scenario | Command |
|----------|---------|
| **Local algo full run** | `python3 algo_run_daily.py` |
| **Local unit tests** | `pytest tests/ -v` |
| **Local linting** | `black . && flake8 .` |
| **Local API server** | `cd webapp && npm run dev` |
| **Check syntax of template** | `aws cloudformation validate-template --template-body file://template-NAME.yml --region us-east-1` |
| **Dry-run workflow** | `gh workflow run deploy-NAME.yml --dry-run` |

## Emergency/One-Off

| What You Want | How |
|---------------|-----|
| **Manually trigger algo** | `aws lambda invoke --function-name algo-orchestrator --region us-east-1 /tmp/out.json` |
| **Manually trigger loaders** | `aws ecs run-task --cluster stocks-data-cluster --task-definition stocks-loaders:1 --region us-east-1` |
| **Manually trigger loaders (local)** | Run `docker-compose up` then `python3 loadpricedaily.py` |
| **Check latest logs** | `aws logs tail /aws/lambda/algo-orchestrator --follow --region us-east-1` |
| **Clean up bad deploy** | `gh workflow run cleanup-orphaned-resources.yml` |
| **Full system nuke** | `gh workflow run cleanup-all-stacks.yml` (keeps RDS backups) |

---

## The Three Standard Deployment Paths

### Path 1: Algo Logic Change
```
Edit algo_*.py → Test locally (1 min) → git push → Tests run (5 min) → Auto deploy (2 min)
```

### Path 2: Infrastructure Change
```
Edit template-*.yml → Validate (30 sec) → git push → Workflow triggers → Stack updates (5-10 min)
```

### Path 3: Frontend/API Change
```
Edit webapp/*.jsx or webapp/lambda/*.js → Test locally (1 min) → git push → Tests run (5 min) → Manual trigger deploy-webapp.yml
```

---

**Still unsure?** See `quick-decision-tree.md` for more context.
