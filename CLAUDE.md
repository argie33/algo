# Stock Analytics Platform

Master deploy: `gh workflow run deploy-all-infrastructure.yml --repo argie33/algo`

| Need | See |
|------|-----|
| Status | STATUS.md |
| Deploy | deployment-reference.md |
| Code changes | DECISION_MATRIX.md |
| Local test | memory/local_testing_setup.md |
| Troubleshoot | troubleshooting-guide.md |
| Costs | .claude/cost-tracker.json |
| Learn | quick-decision-tree.md |
| AWS/tools | tools-and-access.md |
| Tech | algo-tech-stack.md |
| Memory | memory/* |

**Constraints:** No experimental loaders, IaC only, paper trading, 11 blockers fixed.

Algo: 165 modules, 7-phase orchestrator, Alpaca paper trading, PostgreSQL, AWS Lambda/ECS, EventBridge 5:30pm ET.
