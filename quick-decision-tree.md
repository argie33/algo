# Quick Decision Tree — "What Should I Do?"

When you're not sure where to start, follow this decision tree to find the right action.

---

## 🎯 I want to...

### ...understand what this project is
→ Read `CLAUDE.md` (start here, 2 min)
→ Then `algo-tech-stack.md` (overview of 165 Python modules)
→ Then `memory/architectural_principles.md` (core design philosophy)

### ...deploy infrastructure
→ Is this your first time?
  - YES: Run `gh workflow run deploy-all-infrastructure.yml --repo argie33/algo` (master orchestrator)
  - NO: See `deployment-reference.md` for manual steps

### ...test the algo locally
→ Follow SETUP_LOCAL.md (3 steps, ~30 min):
  1. `python3 init_database.py` (create schema)
  2. `python3 run-all-loaders.py` (load data)
  3. `python3 algo_orchestrator.py --mode paper --dry-run` (test)
→ Still broken? See `SETUP_LOCAL.md` → "Troubleshooting"

### ...make changes to the code
→ What are you changing?
  - **Algo logic** (entry, exit, signals): Edit `algo_*.py` → Test locally → Commit → Deploys automatically
  - **API/frontend**: Edit `webapp/` → Test locally → Commit → Run `gh workflow run deploy-webapp.yml`
  - **Data loading**: Fix the official loader, NOT create a populate script (see `memory/loader_discipline.md`)
  - **Infrastructure**: Edit `template-*.yml` → Validate → Commit → Workflow auto-triggers
  - **Workflows themselves**: Edit `.github/workflows/` → Commit → Manually re-run: `gh workflow run deploy-STACK.yml`

### ...debug a problem
→ What's the symptom?
  - **Algo not trading:** `troubleshooting-guide.md` → "Algo Lambda Not Executing"
  - **Trades executing but not in Alpaca:** `troubleshooting-guide.md` → "Trade Not Synced"
  - **Data stale:** `troubleshooting-guide.md` → "Data Stale (No Price Updates)"
  - **Deployment failed:** `troubleshooting-guide.md` → "Workflow Hung/Failed"
  - **RDS can't connect:** `troubleshooting-guide.md` → "RDS Connection Failed"
  - **Something else:** Check `troubleshooting-guide.md` "Quick Reference" table

### ...access AWS resources
→ What do you need?
  - **List stacks/instances/RDS:** See `tools-and-access.md` → "Essential AWS CLI Commands"
  - **Connect to RDS database:** See `tools-and-access.md` → "Accessing Bastion Host"
  - **Check Lambda logs:** `aws logs tail /aws/lambda/algo-orchestrator --follow --region us-east-1`
  - **Trigger ECS loaders:** See `development-workflows.md` → "Running Data Loaders"
  - **Don't know the syntax?** See `tools-and-access.md` → "AWS CLI Syntax Patterns"

### ...understand the system architecture
→ See memory/architectural_principles.md (5 min read)
→ Then `algo-tech-stack.md` for tech stack details
→ Then `memory/aws_deployment_state_2026_05_05.md` for current infrastructure

### ...see what's deployed right now
→ Check `memory/aws_deployment_state_2026_05_05.md` (current state snapshot)
→ Run health check: `gh workflow run check-stack-status.yml`
→ Or manually: `aws cloudformation list-stacks --region us-east-1 --query 'StackSummaries[?StackStatus==\`CREATE_COMPLETE\`]'`

### ...optimize the system (make it faster/cheaper)
→ See `memory/optimal_architecture_plan.md` (roadmap of 30 optimizations)
→ Top 5 to do first: TimescaleDB, Alpaca+EDGAR loaders, watermark incremental loading, AWS Batch, Docker Compose local dev

### ...check if everything is working
→ Run health check workflow: `gh workflow run check-stack-status.yml`
→ Or manually verify:
  1. All stacks deployed: `aws cloudformation list-stacks --region us-east-1`
  2. RDS is up: `aws rds describe-db-instances --region us-east-1`
  3. Lambda is accessible: `aws lambda invoke --function-name algo-orchestrator /tmp/out.json`
  4. Data is fresh: `psql -h localhost -U stocks -d stocks -c "SELECT MAX(date) FROM price_daily;"`

### ...see what happened recently
→ Check `memory/end_to_end_verification_2026_05_07.md` (latest full system test)
→ Check `memory/aws_deployment_state_2026_05_05.md` (latest deployment fixes)
→ Check Git log: `git log --oneline -20`

### ...understand the data flow
→ `algo-tech-stack.md` → "Key Entry Points" section
→ Then `algo_orchestrator.py` (master workflow, 7 phases)
→ Then individual modules (algo_filter_pipeline, algo_trade_executor, etc.)

### ...see what loaders are available
→ `algo-tech-stack.md` → "Data Loaders" section
→ All 18 official loaders listed (use ONLY these, no custom populate scripts)

### ...understand the trading rules
→ `memory/architectural_principles.md` (core rules)
→ `algo_circuit_breaker.py` (kill switches)
→ `algo_filter_pipeline.py` (5-tier signal filter)
→ `algo_governance.py` (position sizing, kelly criterion)

### ...see what trades have been executed
→ Local: `psql -h localhost -U stocks -d stocks -c "SELECT * FROM algo_trades ORDER BY created_at DESC LIMIT 10;"`
→ AWS: Use Bastion to SSH (see `tools-and-access.md`)

### ...see what's in the audit log (decisions made)
→ `psql -h localhost -U stocks -d stocks -c "SELECT phase, message FROM algo_audit_log WHERE created_at > NOW() - INTERVAL '1 day' ORDER BY created_at DESC;"`

### ...check deployment costs
→ See `algo-tech-stack.md` → "Cost Breakdown"
→ Current estimate: $65-90/month
→ If higher, see `troubleshooting-guide.md` → "Deployment Cost Spike"

### ...see what production blockers were fixed
→ `memory/production_blockers_fixed.md` (11 critical safety fixes with details)

### ...understand the current deployment state
→ `memory/aws_deployment_state_2026_05_05.md` (what's deployed, what's deferred, known limitations)

---

## 🚨 Emergency: The System is Broken

1. **Is it a deployment issue?** → See `troubleshooting-guide.md` "Deployment Issues"
2. **Is algo not trading?** → See `troubleshooting-guide.md` "Lambda & Trading Issues"
3. **Is the database down?** → See `troubleshooting-guide.md` "Database Issues"
4. **Is the API down?** → Check CloudWatch: `aws logs tail /aws/lambda/rest-api --follow`
5. **Still stuck?** → Run health check: `gh workflow run check-stack-status.yml` and check CloudFormation events

---

## 📋 Before You Commit & Push

1. ✅ Test locally (if you changed Python/Node code): `python3 algo_run_daily.py` or `npm run dev`
2. ✅ Run linting: `black . && flake8 .`
3. ✅ Run tests: `pytest tests/ -v`
4. ✅ Check Git status: `git status`
5. ✅ Write clear commit message
6. ✅ Push: `git push origin main` (or to your feature branch)
7. ✅ Watch GitHub Actions for tests to pass
8. ✅ Merge when green

---

## 🎓 Learning Path (If New to This Project)

**Day 1:**
1. Read `CLAUDE.md` (5 min)
2. Read `algo-tech-stack.md` (15 min)
3. Read `memory/architectural_principles.md` (5 min)
4. Run local setup: `docker-compose up && python3 algo_run_daily.py` (10 min)

**Day 2:**
1. Read `development-workflows.md` (20 min)
2. Read `deployment-reference.md` (15 min)
3. Make a small code change locally and test
4. Read `tools-and-access.md` (15 min)

**Day 3:**
1. Read `troubleshooting-guide.md` (20 min)
2. Read `memory/aws_deployment_state_2026_05_05.md` (10 min)
3. Review `memory/production_blockers_fixed.md` (10 min)
4. You're now ready to make changes and deploy

---

**Last Updated:** 2026-05-07
