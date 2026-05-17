# Stock Analytics Platform

**🚀 DEPLOYMENT: GitHub Actions IaC Only — No Manual AWS Work**
- Push to `main` → Auto-deploys via `deploy-all-infrastructure.yml` workflow
- Watch at: https://github.com/argie33/algo/actions
- **Never manually create/modify AWS resources — use Terraform only**

| Need | See |
|------|-----|
| **✅ How to Deploy (START HERE)** | **DEPLOYMENT_GUIDE.md** |
| **Deploy Status** | **STATUS.md** (detailed infrastructure status) |
| **Current Infrastructure** | **STATUS.md → "CURRENT INFRASTRUCTURE STATUS"** |
| Code changes | DECISION_MATRIX.md |
| **Local dev** | **"Local Development (3 STEPS)" below** |
| Local test | Run loaders: `python3 run-all-loaders.py` |
| Troubleshoot | troubleshooting-guide.md |
| Costs | .claude/cost-tracker.json |
| Learn | quick-decision-tree.md |
| AWS/tools | tools-and-access.md |
| Tech | algo-tech-stack.md |
| Memory | memory/* |

**Constraints:** No experimental loaders, **Terraform IaC only (CloudFormation eliminated)**, paper trading, all blockers fixed.

Algo: 165 modules, 7-phase orchestrator, Alpaca paper trading, PostgreSQL, AWS Lambda/ECS, EventBridge 5:30pm ET.

**Infrastructure:** 
- **Local:** PostgreSQL on Windows (localhost:5432). Redis optional for caching.
- **Production:** Terraform IaC only. No CloudFormation. All resources defined in `terraform/` modules

**Local Development (3 STEPS):**

**Step 1: Ensure PostgreSQL is running on Windows**
```
PostgreSQL should be installed and running on localhost:5432
Your .env.local should have the correct DB_PASSWORD
```

**Step 2: Initialize database schema**
```bash
python3 init_database.py
# Creates 132 tables in the 'stocks' database
```

**Step 3: Load data**
```bash
python3 run-all-loaders.py
# Loads all data through 5-tier loader pipeline (~20 minutes)
```

**That's it.** You now have a fully populated local database.

**Testing the system:**
```bash
# Test orchestrator (all 7 phases)
python3 algo_orchestrator.py --mode paper --dry-run

# Check data freshness
python3 -c "
import psycopg2
conn = psycopg2.connect('host=localhost user=postgres password=YOUR_PASSWORD dbname=stocks')
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM stock_symbols')
print(f'Symbols: {cur.fetchone()[0]}')
"
```

**Important:** Use PostgreSQL directly on Windows. No Docker/WSL needed. Docker Desktop doesn't work on this machine.

---

## 🗑️ REMOVED FEATURES (2026-05-10)

The following pages and endpoints were **completely removed** because they had **zero real data sources**:

### Deleted Frontend Pages
- `webapp/frontend/src/pages/EarningsCalendar.jsx` — No earnings data loader exists. Would need external API (Alpha Vantage, FinHub, etc.).
- `webapp/frontend/src/pages/FinancialData.jsx` — No financial statement loader exists. Would need external API.
- `webapp/frontend/src/pages/PortfolioOptimizerNew.jsx` — No portfolio optimizer module exists. Would need mean-variance optimization implementation.
- `webapp/frontend/src/pages/HedgeHelper.jsx` — Called `/api/strategies/covered-calls` endpoint that was never implemented.
- `webapp/frontend/src/components/options/` — Entire directory (CoveredCallOpportunities, GreeksDisplay, OptionsChainViewer). Unused.

### Deleted API Handlers (lambda/api/lambda_function.py)
- `_handle_earnings()` — Returned hardcoded mock earnings data. No database queries.
- `_handle_financial()` — Returned hardcoded Apple financials. No database queries.
- `_handle_optimization()` — Returned fixed portfolio weights. No database queries.
- Removed routing for `/api/earnings/`, `/api/financial/`, `/api/optimization/*` endpoints.

### Cleaned API Handler
- `_handle_research()` — **FIXED, not deleted.** Now queries actual `backtest_results` table instead of returning mock data.

### Why Complete Removal?
**Partial cleanups cause confusion and wasted work.** Future developers would see incomplete code, think "maybe I should finish this", and rebuild features unnecessarily. Complete removal makes the system honest:
- 22 pages with real data = KEEP
- 5 pages with only mock data = DELETE completely
- No lingering partial implementations

### How to Add These Features Back (If Needed)
1. **Earnings Calendar:** Add earnings data API, build loader, implement `/api/earnings/*` handlers
2. **Financial Data:** Add financial data API, build loader, implement `/api/financial/*` handlers  
3. **Portfolio Optimizer:** Implement mean-variance optimization, add `portfolio_optimization` table, implement `/api/optimization/*`
4. **Hedge Helper:** Implement `/api/strategies/covered-calls` with options data loader

All deleted code is in git history. Restore via: `git log --oneline | grep -i "earnings\|financial\|optimizer\|hedge"`

---

## 📊 LOADER STRATEGY (Critical Governance)

**PROBLEM STATEMENT:** Loaders are the foundation of the entire platform. Without clear strategy, they become a mess: duplicates, dead code, inconsistent patterns, orphan files, broken deployments. This section establishes the ONE RIGHT WAY.

### What Are Loaders?

Loaders fetch external data (prices, financials, earnings, etc.) and insert it into PostgreSQL. They are:
- **Scheduled jobs** that run on a cron schedule (daily, weekly, or once)
- **Data pipelines** with dependencies (prices → signals → metrics)
- **Deployed to production** via AWS ECS Fargate tasks (Terraform-managed)
- **Tested locally** on Windows using `python3 run-all-loaders.py`

### Canonical Source of Truth

**TERRAFORM IS AUTHORITATIVE.** The file `terraform/modules/loaders/main.tf` contains the complete list of loaders that exist in production. If a loader isn't there, it doesn't exist in production.

Current state: **40 loaders defined in Terraform.**

### Two Deployment Modes

| Mode | Where | When | Who | How |
|------|-------|------|-----|-----|
| **Local** | Windows laptop, PostgreSQL localhost:5432 | Before pushing to main | Developer | `python3 run-all-loaders.py` |
| **Production** | AWS ECS Fargate | On schedule (daily 4am ET, etc.) | EventBridge / Step Functions | Terraform triggers via `aws ecs run-task` |

**Key rule:** Every loader MUST work identically in both modes. No "local-only" loaders, no "AWS-only" shortcuts.

### The Right Loader Pattern

All loaders MUST:

1. **Inherit from DataLoader base class** (in `utils/optimal_loader.py`)
   - Provides: watermark-based incremental loading, dedup, bulk COPY inserts, error isolation, parallelism
   - Avoids: manual connection management, repetitive boilerplate

2. **Follow this structure:**
   ```python
   class MyDataLoader(DataLoader):
       table_name = "target_table"
       primary_key = ("symbol", "date")
       watermark_field = "date"
       
       def fetch_incremental(self, symbol, since):
           # Fetch data newer than `since`
           # Return list of dicts (rows) or None if no data
           pass
   
   if __name__ == "__main__":
       loader = MyDataLoader()
       stats = loader.run(get_active_symbols())
       loader.close()
   ```

3. **Avoid:**
   - Manual connection/cursor management (DataLoader handles it)
   - Hardcoded SQL inserts (DataLoader uses bulk COPY)
   - Duplicate code across loaders (DataLoader is the abstraction)
   - Per-symbol error handling (DataLoader isolates errors by default)

### Loader Lifecycle Management

**When adding a loader:**
1. Create `loaders/load_yourname.py` using DataLoader pattern
2. Add entry to `terraform/modules/loaders/main.tf` in `loader_file_map`
3. Add cron schedule to `scheduled_loaders` map
4. Test locally: `python3 loaders/load_yourname.py --symbols AAPL,MSFT`
5. Test full pipeline: `python3 run-all-loaders.py`
6. Commit + push; deployment is automatic

**When modifying a loader:**
1. ALWAYS test locally first: `python3 loaders/loadername.py`
2. ALWAYS test full tier: `python3 run-all-loaders.py --tier N`
3. Verify Terraform definition matches code
4. Commit with clear message: "fix(loaders): X because Y"

**When deleting a loader:**
1. Remove from `terraform/modules/loaders/main.tf` completely
2. Delete the .py file from `loaders/`
3. Delete from `run-all-loaders.py` tiers if present
4. Commit: "chore(loaders): delete X (no data source / dead code)"

### Current State vs Ideal State

**Current (MESSY):**
- 40 files on disk + 40 loaders in Terraform (seems fine but...)
- 8 orphan files NOT in Terraform (dead code sitting around)
- 1 loader in Terraform but file doesn't exist
- 4 files with syntax errors (blocking execution)
- Mixed patterns: old manual code + new DataLoader
- No clear governance (anyone can add loaders haphazardly)

**Ideal (CLEAN):**
- Exactly 40 loaders: same files on disk, same definitions in Terraform
- Zero orphan files
- Zero missing files
- Zero syntax errors
- ALL loaders use DataLoader base class
- Clear governance: must go through review before adding

**Plan:** Session by session, convert loaders to DataLoader pattern and delete orphans. When all 40 use the same pattern, the mess is gone.

### Critical Rules (No Exceptions)

1. **Never create a loader without updating Terraform.** If it's not in `terraform/modules/loaders/main.tf`, it's not production.

2. **Never commit a broken loader.** Syntax errors, import errors, logic errors all block local testing and prevent deployment. Fix before pushing.

3. **Never leave dead code.** If a loader isn't needed, delete it completely. Don't leave it "just in case."

4. **Never add "experimental" loaders.** Every loader must load real data from a real source. No mock data, no "coming soon."

5. **Never duplicate functionality.** If two loaders do similar work, consolidate them. Don't let mess grow.

---

## 🔄 CLAUDE MECHANICAL STEERING RULES (Enforced Before Action)

### ⚠️ ABSOLUTE RULE: NO EXTRA DOCS

**Do NOT create new documentation files.** Period. Before creating anything, ask:
1. Is the user explicitly asking me to create a doc? ("document X", "create Y guide")
   - YES → Only if they ask
   - NO → STOP, don't create it

2. Is it session/progress info (setup steps, next steps, blockers)?
   - YES → Put it in STATUS.md, NOT a new file
   - NO → Continue to #3

3. Is it a reusable pattern (pattern, principle, constraint)?
   - YES → Save to memory/, NOT a new file
   - NO → STOP, delete it

4. Is it diagnostic/utility (verify scripts, temp setup helpers)?
   - YES → DELETE it, don't commit
   - NO → OK to create if it's production code

### The Quick Test

If you catch yourself creating:
- ✅ `algo_*.py`, `load*.py`, `lambda/*`, `terraform/*` → Keep (production code)
- ❌ `SETUP*.md`, `READY*.md`, `GUIDE*.md`, `verify*.py` → DELETE (not production)
- ❌ `*TEMP*.md`, `SESSION*.md`, `AUDIT*.md` → DELETE (temp docs)
- ❌ `init*.py` (utility) → DELETE unless truly essential
- ✅ Updates to existing: `STATUS.md`, `CLAUDE.md`, memory files → OK

### Mechanical enforcement:
- Maximum 1 permanent documentation file per session
- All session/progress info → STATUS.md ONLY
- All patterns/learnings → memory/ ONLY
- All diagnostic scripts → DELETE IMMEDIATELY
- All temporary docs → DELETE IMMEDIATELY
- All utility helpers → DELETE IMMEDIATELY unless core functionality

---

## 🔄 CLAUDE BEST PRACTICES (Critical for Effective Collaboration)

### 1. DOCUMENTATION DISCIPLINE
**Most Important:** Don't create documentation sprawl.

**DO:**
- ✅ Update STATUS.md with what's done + next steps (required every session)
- ✅ Write clear commit messages explaining *why* (required)
- ✅ Save permanent patterns to memory/ once (e.g., "Phase 1 pattern")
- ✅ Only create docs when explicitly asked ("Explain X" or "Document Y")

**DON'T:**
- ❌ Generate 6 versions of the same audit (FINDINGS_SUMMARY, EXECUTIVE_SUMMARY, etc.)
- ❌ Create dated docs (ISSUES_2026_05_10.md, STATUS_PHASE_1.md)
- ❌ Create temporary action plans as files (put in STATUS.md instead)
- ❌ Duplicate info across files
- ❌ Generate comprehensive guides "just to be thorough"

**Why:** Each unnecessary doc costs ~2K tokens to re-read. 50 sessions × 5 bad docs = 500K wasted tokens.

**Rule:** If the user didn't ask for it, and it's not permanent, DELETE it.

---

### 2. STATE MANAGEMENT
**Single Source of Truth:**

- **STATUS.md** = Current state (what's working, what's broken, next 3-5 items)
  - Updated every session
  - ~500 tokens, read every time, essential
  - One file, always current

- **memory/** = Permanent learnings (principles, constraints, patterns)
  - Updated only when principle changes
  - Cached, not re-read every session
  - Examples: "No experimental loaders", "Phase 1 pattern", "Loader discipline"

- **git log** = Authoritative history (what changed, when, why)
  - Commit messages are the record
  - Don't duplicate in separate docs
  - Use: `git log --oneline`, `git show <hash>`, `git tag -l`

- **CLAUDE.md** = Navigation + constraints (rarely changes)
  - Read once per session
  - Critical rules, tech stack, how to deploy
  - This file

**Don't create:**
- PHASE_X_STATUS.md files (use STATUS.md)
- Duplicate audit reports (use git log)
- Session transcripts (ephemeral, not useful)

---

### 3. CONSTRAINT CLARITY
**I need explicit bounds:**

✅ **Clear:**
- "Don't create experimental loaders"
- "Terraform only, no CloudFormation"
- "No documentation sprawl"
- "If you generate docs the user didn't ask for, delete them"

❌ **Vague:**
- "Be thoughtful"
- "Use good judgment"
- "Don't over-engineer"

**When in doubt, ask.** Example: "Should I create a test file for this, or update existing tests?"

---

### 4. FEEDBACK & COURSE CORRECTION
**How to tell me I'm going wrong:**

- **Direct correction:** "Don't do X" → I stop doing X immediately
- **Pattern feedback:** "I notice you always Y; stop that" → I change behavior
- **Question:** "Should I be doing Z?" → I wait for answer before proceeding
- **If you see me creating doc sprawl:** "Stop, delete those docs, use STATUS.md instead" → I immediately comply

**I need this feedback to improve.** Don't wait for perfection.

---

### 5. DECISION DOCUMENTATION
**When I make a choice, I should document:**

Instead of: "I'll use approach X"
Write commit or STATUS note: "Using approach X because Y constraint requires it" or "tried Z but failed because..."

Examples:
- "Moved schema to init_database.py as AUTHORITATIVE source because manual SQL maintenance was error-prone"
- "Deleted Dockerfile.* because Terraform ECS is current deployment"
- "Added Phase 1 to loadstockscores first because it blocks 80% of null metrics"

**Why:** Next session or next Claude understands the reasoning.

---

### 6. GIT DISCIPLINE
**Good commit standards:**

✅ DO:
```
fix: Consolidate database schema initialization to init_database.py

- Move AUTHORITATIVE schema from init_db.sql (legacy) to utils/init_database.py (canonical)
- Update CI workflows to use init_database.py for database setup
- Delete init_db.sql (manual SQL maintenance was error-prone and duplicated init_database.py)
- Why: Single source of truth reduces schema drift between dev/test/prod
```

❌ DON'T:
```
fixed stuff
updated things
changes
```

**Why:** `git log` becomes the audit trail. Future me (or you) can understand what happened without separate docs.

---

### 7. TOKEN AWARENESS
**I should remember I'm expensive:**

- Reading 100 unnecessary docs = 100K wasted tokens
- Creating "comprehensive guides" = ~5K tokens each
- Duplicating info = ~2K tokens per duplicate

**Mindset:** "Is this creation worth the tokens future sessions will spend reading it?"

If no → Delete it.

---

### 8. SCOPE BOUNDARIES
**What I should do:**
- ✅ Fix bugs
- ✅ Refactor code
- ✅ Add features
- ✅ Update infrastructure
- ✅ Write tests
- ✅ Make thoughtful architectural decisions
- ✅ Update STATUS.md

**What I should NOT do without asking:**
- ❌ Create large new systems (ask first)
- ❌ Delete code I'm not 100% sure is dead (ask first)
- ❌ Change architecture patterns (ask first)
- ❌ Make breaking API changes (ask first)
- ❌ Reorganize the codebase (ask first)

**If unsure, ask in the commit message or STATUS.md.**

---

### 9. MEMORY MANAGEMENT
**What goes in memory/:**

✅ SAVE:
- Architectural principles ("Why we chose Terraform")
- Constraints ("No experimental loaders")
- Patterns ("Phase 1 validation pattern")
- User preferences ("User hates doc sprawl")
- Lessons ("We learned X costs Y")

❌ DON'T SAVE:
- Session logs
- Temporary findings
- Step-by-step what we did
- Audit report transcripts
- Dated status snapshots

**Rule:** Only save if future sessions need to know it.

---

### 10. CLEAR COMMUNICATION
**Format:**

When I propose something:
```
I'm proposing: [what]
Reason: [why]
Risk: [if any]
Ask: [do you agree?]
```

When I finish work:
```
Done:
- [x] Thing 1
- [x] Thing 2

Updated:
- STATUS.md
- [if relevant] memory/

Commits: [hash1, hash2]

Next: [3 items or blocked waiting for]
```

**Why:** Clear, scannable, you know exactly where we are.

---

### 11. PERMISSION MODEL
**I assume I CAN:**
- Read any file
- Run tests
- Make commits
- Update STATUS.md
- Ask questions

**I assume I CANNOT without explicit permission:**
- Delete files (ask first unless in cleanup)
- Change architecture patterns (ask first)
- Rewrite major systems (ask first)
- Force push to git (never)
- Make breaking changes (ask first)

**When in doubt: Ask or flag in STATUS.md for user decision.**

---

### 12. QUALITY OVER SPEED
**I should:**
- ✅ Understand the problem deeply before coding
- ✅ Write good commit messages (takes 2 mins, saves 2 hours later)
- ✅ Test changes before declaring done
- ✅ Check for side effects
- ✅ Ask questions if context is unclear

**I should NOT:**
- ❌ Rush to "finish" with low-quality work
- ❌ Skip commit message clarity for speed
- ❌ Assume I understand context
- ❌ Leave TODOs or half-finished work

---

## ✋ RED FLAGS (Stop and Ask)

If I'm about to:
- [ ] Create >2 documents in one session → Stop, ask if this is necessary
- [ ] Delete >20 files without explicit request → Stop, ask if sure
- [ ] Refactor large system sections → Stop, ask about approach first
- [ ] Make breaking API changes → Stop, ask about versioning strategy
- [ ] Add new external dependencies → Stop, ask about why
- [ ] Change git history (rebase, force push) → Stop, never do this

---

## 🎯 SUCCESS CRITERIA FOR CLAUDE IN THIS REPO

- [ ] Code is always clean and tested
- [ ] Commit messages are clear and explain why
- [ ] STATUS.md is updated after every session
- [ ] No documentation sprawl (1-2 docs max per session)
- [ ] Memory/ contains only reusable learnings
- [ ] When I'm confused, I ask instead of guessing
- [ ] I remember constraints and follow them
- [ ] Users don't have to correct my behavior twice

---

## 🛡️ PREVENTING PARTIAL IMPLEMENTATIONS

**Problem:** Code gets added but never completed. Months later, new developers see incomplete code and waste time rebuilding it.

**Solution:** The 3-Step Completion Rule

When implementing a feature, ALL THREE must be done:
1. ✅ **Code works** — Queries real data, not hardcoded values
2. ✅ **Integration complete** — Wired into routing, navigation, exported properly
3. ✅ **Documented** — STATUS.md updated, purpose/constraints clear

If ANY step can't be done → **DELETE it immediately**. Don't leave 90% done.

**Examples:**
- ❌ **Don't:** Add page with mock data intending to "add real data later"
  - **Do:** Delete the page until you have a real data source ready

- ❌ **Don't:** Add API endpoint that returns placeholder data
  - **Do:** Don't add endpoint until database table exists and is being populated

- ❌ **Don't:** Add navigation menu item to feature that doesn't work yet
  - **Do:** Wait until feature is 100% working to add to menu

**Commit Message Red Flag Test:**
If your commit message has "WIP", "TODO", "will add later", "placeholder", "mock data" → **Stop. Delete and wait.**

---

## 💡 IF YOU SEE ME DOING SOMETHING WRONG

Tell me directly. Examples:
- "Stop creating doc sprawl"
- "Don't do that anymore"
- "Ask me before deleting large code sections"
- "That's redundant, delete it"
- "Don't add mock endpoints—delete them immediately"
- "If something isn't complete, remove it completely"

**I will immediately stop and adjust.** I'd rather be corrected than keep making the same mistake.
