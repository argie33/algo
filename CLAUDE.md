# Stock Analytics Platform

**🚀 DEPLOYMENT: GitHub Actions IaC Only — No Manual AWS Work**
- Push to `main` → Auto-deploys via `deploy-all-infrastructure.yml` workflow
- Watch at: https://github.com/argie33/algo/actions

| Need | See |
|------|-----|
| **Deploy guide** | **DEPLOYMENT_GUIDE.md** |
| **Status/next steps** | **memory/status_current.md** (rotated weekly) |
| **Local dev** | **See "Local Development" below** |
| Test loaders | `python3 run-all-loaders.py` |
| Troubleshoot | troubleshooting-guide.md |
| Architecture | algo-tech-stack.md |

---

## 🚫 ABSOLUTE RULES (Non-Negotiable)

**These are enforced on every change — I will block violations:**

1. **ONE-LOADER-PER-DATA-SOURCE** — Each external data source (Alpaca, SEC, etc.) has exactly ONE loader, integrated into `run-all-loaders.py`, or it's DELETED
2. **NO ONE-TIME SCRIPTS** — Backfill scripts, diagnostics, utilities → DELETED immediately
3. **NO UNINTEGRATED CODE** — If it's not in main orchestration (routing, run-all-loaders.py, etc.), it doesn't exist
4. **DEPENDENCIES MUST BE USED** — Show me WHERE it's imported and WHY before adding. No bloat packages.
5. **TESTS MUST HAVE EXPIRATION DATES** — `@pytest.mark.skip(reason="... (2026-06-15)")`. If expired → deleted.
6. **NO MOCK ENDPOINTS** — Real data flow or DELETE the endpoint/page completely.

**See:** [[claude-enforcement-checklist]] (enforced before every code change)

---

## 📋 LOADER DISCIPLINE

- Loaders run in tier order (Tier 0→4) via `run-all-loaders.py`
- Each loader uses `OptimalLoader` base class
- When adding: wire into run-all-loaders.py or DELETE immediately
- No experimental/alternative loaders

---

## 🔐 CREDENTIAL MANAGEMENT (ABSOLUTE RULE #7)

**THIS IS NON-NEGOTIABLE:**

- ❌ **NO .env files** — will cause code to fail (security violation)
- ❌ **NO .env.local** — will be rejected by pre-commit hook
- ❌ **NO hardcoded credentials** — will be rejected by pre-commit hook
- ✅ **USE AWS Secrets Manager** — same for local dev + production (see LOCAL_CRED_SETUP.md)
- ✅ **Environment variables** — only for CI/GitHub Actions (not local dev)

**For local development:**
See **LOCAL_CRED_SETUP.md** (5-minute one-time setup with AWS Secrets Manager)

**Why this matters:**
- .env files can be accidentally committed (human error)
- AWS Secrets Manager = credentials never touch git
- Same system for local dev + production = no surprises

---

## 💻 LOCAL DEVELOPMENT (4 STEPS)

**Step 1:** PostgreSQL running on localhost:5432

**Step 2:** Set environment variables (in your terminal):
- For database: host, port, user, name, password
- For trading: Alpaca API key and secret
- See credential_helper.py for full list of variables

**Step 3:** Initialize database
```bash
python3 init_database.py
```

**Step 4:** Load data (all 40 loaders, ~20 minutes)
```bash
python3 run-all-loaders.py
```

That's it — fully populated database with 1.5M+ price records.

**Test orchestrator (all 7 phases):**
```bash
python3 algo/algo_orchestrator.py --mode paper --dry-run
```

---

## 💾 MEMORY & CONTEXT RULES

**Token waste prevention (ENFORCED):**
- Memory files: max 150 lines per file (if larger → split or archive)
- Root .md files: **NO session-specific docs EVER** — will be rejected by git hooks
  - ❌ AWS_TROUBLESHOOTING_*.md, AWS_LOADER_*.md
  - ❌ EXECUTION_*.md, BLOCKERS_*.md, RUN_*.md, LOADED_*.md
  - ❌ *_STATUS.md, *_SUMMARY.md, *_REPORT.md (except STATUS_CHECKLIST.md if referenced in CLAUDE.md)
- Status info: Goes to memory/status_current.md (rotated, not root)
- CLAUDE.md: max 150 lines (this file is kept lean)

**Why:** 10K tokens per session = $0.01-0.02/session. Fix: lean context.

---

## 📚 REFERENCE

- **Enforcement Rules:** See memory/enforcement_rules.md
- **Infrastructure:** Terraform IaC only, no CloudFormation
- **Tests:** 309+ passing

---

## ⚠️ IF YOU SEE A PROBLEM

Tell me directly:
- "This is bloat, delete it"
- "Stop, run the checklist"
- "You're violating rule #3"

I will immediately stop and fix it. Don't wait for me to notice.
