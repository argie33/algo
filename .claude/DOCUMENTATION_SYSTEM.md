# Documentation System Guide (For Claude)

This file explains how to use the project's documentation. Read this if you're confused about where to find things.

## The Structure (Ultra-Lean by Design)

### Tier 1: CLAUDE.md (20 lines, ~70 tokens)
**What:** Navigation index ONLY. Read this first for every conversation.
**Contents:** Master deploy command + 10-item navigation table + constraints summary
**When loaded:** Every conversation automatically
**Action:** Use it to route to the right reference file

### Tier 2: Quick Reference Files (One-page lookups)
Load these when the user asks specific questions:

| File | What to Ask | Content |
|------|-------------|---------|
| **STATUS.md** | "Is the system healthy?" | Deployment state, health checks, recent commits, alerts |
| **DECISION_MATRIX.md** | "I want to change X" | Lookup table: change → file → deploy method |
| **.claude/cost-tracker.json** | "Are costs high?" | Current costs, breakdown, optimization roadmap |

### Tier 3: Detailed Reference Files (Complete guides)
Load these when user needs procedural steps or detailed explanations:

| File | What to Ask | Content |
|------|-------------|---------|
| **deployment-reference.md** | "How do I deploy?" | 6 templates, 23 workflows, manual steps, troubleshooting |
| **development-workflows.md** | "How do I develop/test locally?" | Local setup, running tests, making changes, debugging |
| **troubleshooting-guide.md** | "Something is broken" | Common failures, diagnosis steps, fixes with code |
| **tools-and-access.md** | "How do I access AWS/GitHub?" | AWS CLI patterns, commands, authentication, Git workflows |
| **algo-tech-stack.md** | "What is this system?" | 165 modules, tech choices, architecture, entry points |
| **quick-decision-tree.md** | "I'm not sure where to start" | Decision trees for every common scenario |

### Tier 4: Memory Files (Auto-loaded for relevance)
These are in `.claude/projects/*/memory/` and auto-load based on conversation context:
- Architectural principles
- Deployment state snapshots
- Production blockers
- Feature status
- Known issues
- Etc.

**Don't read these manually.** The system loads them automatically when relevant.

---

## How to Use (Decision Tree)

### When User Asks a Question

1. **Is it a quick status check?**
   - "Is everything deployed?" → Read STATUS.md (81 lines, ~150 tokens)
   - "Are costs high?" → Read .claude/cost-tracker.json (~200 tokens)
   - "What changed recently?" → Read git log or STATUS.md

2. **Is it "I want to change X"?**
   - "How do I deploy?" → Read DECISION_MATRIX.md then deployment-reference.md
   - "I want to fix the algo" → Read DECISION_MATRIX.md (find which file) then development-workflows.md
   - "I need to add a loader" → Read DECISION_MATRIX.md (data loader → fix existing only)

3. **Is it a problem/troubleshooting?**
   - "Algo isn't trading" → Read troubleshooting-guide.md (Lambda & Trading Issues)
   - "RDS won't connect" → Read troubleshooting-guide.md (Database Issues)
   - "Deployment failed" → Read troubleshooting-guide.md (Deployment Issues)

4. **Do they need to understand the system?**
   - "What is this project?" → Read algo-tech-stack.md (120 lines)
   - "How does the architecture work?" → Memory/architectural_principles.md (auto-loaded)
   - "Where do I start?" → Read quick-decision-tree.md (Learning Path section)

5. **Is it AWS/GitHub/tool access?**
   - "How do I use AWS CLI?" → Read tools-and-access.md (Essential AWS CLI Commands)
   - "How do I run a workflow?" → Read tools-and-access.md (GitHub CLI section)
   - "How do I connect to RDS?" → Read tools-and-access.md (Accessing Bastion Host)

---

## File Completeness Checklist

✅ **CLAUDE.md** (20 lines)
- Master deploy command
- Navigation table (10 items)
- Critical constraints
- System one-liner

✅ **STATUS.md** (81 lines)
- Deployment state (6 stacks)
- Key facts (region, cost, schedule, data, frontend)
- Critical paths (deploy, test, logs, access)
- Known limitations
- Recent commits (5)
- Health check commands
- Troubleshooting routing

✅ **DECISION_MATRIX.md** (106 lines)
- Code changes (10 scenarios)
- Infrastructure changes (9 scenarios)
- Workflow changes (4 scenarios)
- Configuration changes (4 scenarios)
- Documentation changes (5 scenarios)
- Test commands
- Emergency procedures
- Three standard deployment paths

✅ **deployment-reference.md** (228 lines)
- Quick start (master orchestrator)
- Stack dependency chain (visual)
- Manual deploy steps
- 6 CloudFormation templates explained
- 23 GitHub workflows listed
- GitHub secrets required
- Troubleshooting (deployment, RDS, Lambda)
- Manual cleanup procedures

✅ **development-workflows.md** (274 lines)
- Local testing setup (prerequisites, docker-compose)
- How to run algo locally
- Verify everything works
- Making changes (algo, API, frontend, loaders, infrastructure)
- Running tests (unit, lint, integration, backtest)
- Debugging (logs, AWS, database, Alpaca)
- Common dev tasks (add filter, adjust sizing, change hours)
- AWS deployment checklist

✅ **troubleshooting-guide.md** (351 lines)
- Quick health check commands
- Deployment issues (6 common + fixes)
- Database issues (connection, space, stale data)
- Lambda & trading issues (not executing, not trading, not synced)
- Local dev issues (Docker, psql, autocommit)
- Quick reference table (what file to check)

✅ **tools-and-access.md** (356 lines)
- AWS CLI (installation, authentication, syntax patterns)
- Essential AWS CLI commands (CloudFormation, RDS, Lambda, ECS, Secrets, EventBridge)
- Accessing Bastion Host
- GitHub CLI (workflows, PRs, issues)
- Git workflows (standard, hotfix, reverting)
- Environment variables for local dev
- Useful aliases

✅ **algo-tech-stack.md** (120 lines)
- 165 Python modules organized by function (11 categories)
- 18 official data loaders listed
- 6 CloudFormation templates explained
- 23 GitHub workflows summarized
- Tech choices (Python, PostgreSQL, Lambda, Alpaca, yfinance, etc.)
- Key entry points for development
- Database schema (7 tables)
- Cost breakdown ($77/month actual)

✅ **quick-decision-tree.md** (157 lines)
- 18 decision trees ("I want to..." → resource)
- Quick decision for every common task
- Emergency procedures (system broken)
- Learning path (Day 1-3 onboarding)

✅ **Memory files** (16 files, auto-loaded)
- Architectural principles
- Deployment state
- Production blockers
- Feature status
- Data gaps
- Etc.

---

## What NOT to Do

❌ **Don't:** Summarize or paraphrase reference files to user
→ **Do:** Link directly: "See troubleshooting-guide.md → Database Issues"

❌ **Don't:** Add context to CLAUDE.md
→ **Do:** Update the reference file instead

❌ **Don't:** Load all files at once
→ **Do:** Load only what's needed for the question

❌ **Don't:** Ignore memory files
→ **Do:** Let system auto-load them; reference them if relevant

---

## For Future Claudes

This documentation system is designed to be **token-efficient** while **complete**:
- CLAUDE.md is intentionally minimal (navigation only)
- Reference files are detailed but load on-demand
- Memory files auto-load for context
- Total conversation cost: ~1400 tokens instead of ~2000

**If adding new documentation:**
1. Does it fit in an existing file? Add it there.
2. Is it a new topic? Create a new reference file + add to CLAUDE.md navigation.
3. Is it historical/context? Put it in memory/* (not CLAUDE.md).
4. Never add to CLAUDE.md (keep it at 20 lines).

---

**Last Updated:** 2026-05-07
**System Designer:** Claude Code
**Status:** Production-ready, highly optimized for token efficiency
