# Deploy Checklist

## DECISION TREE: Which workflow to use?

### Code Changes Only (no infra/secrets/terraform)
**Example:** Bug fix, new signal, feature update, tests, docs.

1. Run tests locally: `python3 -m pytest tests/`
2. Verify no `.env`, `pdb`, `print()` in lib code
3. `git push main` → auto-triggers `deploy-code.yml`
4. Monitor: https://github.com/argie33/algo/actions
5. ✅ Done. Code live in 3–5 min.

---

### Infrastructure / Terraform / Secrets / Lambda Layers
**Example:** DB schema change, new Lambda layer, RDS config, AWS Secrets Manager update, terraform apply.

**⚠️ CRITICAL: Never mix code + infra in one push.**

1. Make infra changes (terraform, secrets, layer updates)
2. `git push main` → code builds, but **do not merge/deploy yet**
3. Go to GitHub Actions → manually trigger `deploy-all-infrastructure.yml`
4. Watch AWS console for: Terraform apply → Lambda updates → ECS task registration
5. After infra settles (5–10 min), code deploy will follow
6. Check: RDS is up, Lambda env vars set, ECS tasks registered
7. ✅ Done. Test manually: `test-orchestrator.yml` or `manual-invoke-loaders.yml`

---

### Immediate Invoke (no code deploy, just run a task now)
**Example:** Test orchestrator, queue a specific loader, debug live data.

1. `test-orchestrator.yml` → invoke algo-algo-dev Lambda immediately
2. OR `manual-invoke-loaders.yml` → queue specific ECS loader tasks
3. Monitor CloudWatch logs in AWS console
4. Check RDS data: `SELECT COUNT(*) FROM technical_data_daily`
5. ✅ Done. No code push needed.

---

## Pre-Deploy Audit Checklist

| Check | Command | Pass/Fail |
|-------|---------|-----------|
| Tests pass | `python3 -m pytest tests/ -v` | ☐ |
| No .env files | `git status \| grep .env` (empty = good) | ☐ |
| No pdb/breakpoint in lib | `grep -r "pdb\|breakpoint" algo/ loaders/ lambda/ --exclude-dir=tests` (empty = good) | ☐ |
| No print() in lib | `grep -rn "print(" algo/ loaders/ lambda/ --exclude-dir=tests` (empty = good) | ☐ |
| Credentials in profile, not code | Spot-check: no DB_HOST, API_KEY in .py files | ☐ |
| AWS creds valid | `aws sts get-caller-identity` (returns account) | ☐ |

---

## Common Mistakes → Prevention

| Mistake | Why Fails | Prevention |
|---------|-----------|------------|
| Push code + infra together | Code deploys before infra ready; Lambda env vars missing | Use decision tree: code-only push first, then manual infra workflow |
| Forget to manually trigger `deploy-all-infrastructure.yml` | Code lives but infra (terraform, RDS changes) never apply | After infra push, check Actions page; manually trigger workflow |
| Rerun all loaders to test | Costs $$$$ (24 ECS tasks × full data fetch) | Use `manual-invoke-loaders.yml` with 1 specific loader first |
| Use `ALPACA_PAPER_TRADING=true` then forget to flip to `false` for live trading | Paper trades only; real money never deployed | Add to pre-push: confirm `ALPACA_PAPER_TRADING` set correctly in PowerShell profile |
| Commit `.env` file | Secrets leak to git history; rotation required immediately | Pre-commit hook blocks this. If it happens, rotate keys instantly. |

