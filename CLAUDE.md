# Stock Analytics Platform

**🚀 DEPLOYMENT: GitHub Actions IaC Only — No Manual AWS Work**
- Push to `main` → Auto-deploys via `deploy-all-infrastructure.yml` workflow
- Watch at: https://github.com/argie33/algo/actions

| Need | See |
|------|-----|
| **Deploy guide** | **DEPLOYMENT_GUIDE.md** |
| **Status/next steps** | **STATUS.md** |
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

## 🔐 CREDENTIAL MANAGEMENT

- ✅ `.env.local` = Dev credentials (LOCAL ONLY, gitignored)
- ❌ NEVER delete `.env.local` (breaks local dev)
- ❌ NEVER commit `.env.local` (in .gitignore anyway)
- 🔒 Production: AWS Secrets Manager only
- See: CREDENTIAL_SETUP.md

---

## 💻 LOCAL DEVELOPMENT (3 STEPS)

**Step 1:** PostgreSQL running on localhost:5432

**Step 2:** Initialize database
```bash
python3 init_database.py
```

**Step 3:** Load data
```bash
python3 run-all-loaders.py
```

That's it — fully populated local database.

**Test orchestrator:**
```bash
python3 algo/algo_orchestrator.py --mode paper --dry-run
```

---

## 📚 REFERENCE

- **Rules & Constraints:** See memory/ (referenced in git commits)
- **Code Governance:** [[code-governance-rules]]
- **Enforcement:** [[claude-enforcement-checklist]] (I run this before every change)
- **Token Strategy:** [[token-optimization-2026-05-17]]
- **Infrastructure:** Terraform IaC only, no CloudFormation
- **Tests:** 309+ passing

---

## ⚠️ IF YOU SEE A PROBLEM

Tell me directly:
- "This is bloat, delete it"
- "Stop, run the checklist"
- "You're violating rule #3"

I will immediately stop and fix it. Don't wait for me to notice.
