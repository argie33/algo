# Stock Analytics Platform — Quick Reference

Enterprise algorithmic trading system: 165 Python modules, 7-phase orchestrator, Alpaca paper trading, PostgreSQL, AWS Lambda/ECS, real-time signal generation.

## Master Deploy Command
```bash
gh workflow run deploy-all-infrastructure.yml --repo argie33/algo
```

## Critical Facts
- **Region:** us-east-1 | **Cost:** $65-90/month | **Deployment:** 20-30 minutes
- **Local Testing:** Docker Compose + WSL2 — see `LOCAL_TESTING_SETUP.md` in memory
- **Principles:** See `architectural_principles.md` in memory
- **Current State:** See `aws_deployment_state_2026_05_05.md` in memory

## Navigate By Task

| Task | Resource |
|------|----------|
| **System status snapshot** | STATUS.md |
| **I want to change X** | DECISION_MATRIX.md |
| **Check costs** | .claude/cost-tracker.json |
| **Understand the system** | memory/architectural_principles.md |
| **Deploy infrastructure** | deployment-reference.md |
| **Test locally** | memory/local_testing_setup.md |
| **Make code changes** | development-workflows.md |
| **Access AWS/tools/credentials** | tools-and-access.md |
| **Fix production issues** | troubleshooting-guide.md → memory/* |
| **Quick decision: what should I do?** | quick-decision-tree.md |
| **Tech stack overview** | algo-tech-stack.md |

## Critical Constraints
- ✅ **No experimental loaders** — use official pipeline only (see memory/loader_discipline.md)
- ✅ **All infrastructure as code** — 6 templates, 23 workflows, zero manual AWS changes
- ✅ **Paper trading only** until market condition signals green light
- ✅ **11 production blockers implemented** (see memory/production_blockers_fixed.md)

## Key Deployed Stacks
```
stocks-core (VPC, networking, ECR, S3)
    ↓
stocks-app-stocks (RDS, ECS cluster, Secrets)
    ├─→ stocks-app-ecs-tasks (39 data loaders)
    ├─→ stocks-webapp-lambda (REST API)
    └─→ stocks-algo-orchestrator (Daily 5:30pm ET via EventBridge)
```

## Emergency Contacts
- **Deployment hung?** → Check CloudWatch logs or `troubleshooting-guide.md`
- **Data stale?** → Run official loaders via ECS tasks or local Docker
- **Algo not trading?** → Check `end_to_end_verification_2026_05_07.md` (memory)
- **AWS costs high?** → See `aws_deployment_state_2026_05_05.md` deferred hardening section

---
**Last updated:** 2026-05-07 | **Maintained by:** Claude Code
