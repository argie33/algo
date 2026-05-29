# Steering & Memory Maintenance System

Keep documentation current and prevent it from rotting.

## Rules (Pre-Commit Enforced)

### 1. Code Change → Steering Doc Update (Same Commit)
**Rule:** If you modify system behavior, architecture, or procedures → update `steering/algo.md` in the same commit

**Examples that require steering update:**
- Add new loader or change loader behavior → update SYSTEM MAP and loader schedule
- Change how credentials work → update CREDENTIAL FLOW section
- Modify orchestrator phases → update Phase descriptions
- Change deployment procedure → update relevant section

**Examples that DON'T require update:**
- Bug fixes that don't change documented behavior
- Internal refactoring with no external impact
- Dependency upgrades

**Enforcement:** Pre-commit hook checks if code changed but steering didn't

### 2. Decisions → Memory Files (Immediate)
**Rule:** When you fix something or learn something important → save to memory

**When to save:**
- Fixed a bug → what was wrong, what you changed, why
- Discovered a pattern → how to avoid similar issues
- Completed a task → what worked, what didn't
- Had a realization → the insight and how to apply it

**When NOT to save:**
- Routine progress (in-progress status)
- Things already documented in steering
- Ephemeral state (current date, run status)

### 3. Memory Lifecycle
**Created:** Include timestamp (2026-05-29), context, and why it matters
**Updated:** Refresh when facts change or you have more info
**Expired:** Delete when knowledge becomes stale or obsolete

## Maintenance Schedule

### Weekly (Friday EOD)
1. Review memory index (MEMORY.md)
2. Delete or update expired memories (stale dates, disproven facts)
3. Link related memories together

### Monthly (First Monday)
1. Audit steering doc vs actual code
   - Are loader counts accurate?
   - Are procedures still valid?
   - Have commands changed?
2. Update any section that diverged from reality
3. Commit: "docs: Audit steering doc - verify accuracy with codebase"

### Quarterly (With credential rotation)
1. Full audit: does every section in steering match the system?
2. Check: are credentials documented correctly?
3. Check: are all components listed?
4. Update memory files: consolidate learnings from last 3 months

## What Goes Where

| Content | Location | Why |
|---------|----------|-----|
| How systems work, procedures, architecture | steering/algo.md | Single source of truth, versioned with code |
| Decisions made, bugs fixed, patterns learned | memory/*.md | Context for future work, not code-version-dependent |
| Current operational state, metrics, status | GitHub Actions logs, AWS console | Real-time, changes constantly, not versioned |
| Git history, who changed what, when | `git log` | Permanent record, not duplicated |

## Validation Commands

**Check if steering is accurate:**
```bash
# Count loaders
ls -1 loaders/load_*.py | wc -l
# (should match steering doc claim of "33 loaders")

# Check orchestrator phases
grep -c "def " algo/orchestrator/phase*.py
# (should match steering phases count)

# Verify credentials sections
grep -c "algo/" terraform/modules/secrets/main.tf
# (should match steering credential flow)
```

**Audit memory for staleness:**
```bash
# Find memories older than 30 days
find .claude/projects/*/memory -name "*.md" -mtime +30 -ls

# Review them: are they still accurate?
# If not: update or delete
```

## Example: Good Steering Update

**Code change:** Add new loader for earnings data
**Steering updates required:**
1. SYSTEM MAP → add to loader list (49 scripts: X essential + Y supporting)
2. Loaders section → add earnings_data entry
3. Schedule section → add when it runs (cron time)
4. If it's critical → update Step Functions DAG

**Commit message:**
```
feat: Add earnings data loader

- New loader: loaders/load_earnings_data.py
- Scheduled: Daily 4:15am ET via EventBridge
- Added to SYSTEM MAP and schedule documentation

Updates steering/algo.md to reflect new loader
```

## Example: Good Memory Save

**Situation:** Fixed a bug where Step Functions pipeline was failing because credentials expired

**Memory saved:**
```markdown
---
name: step_functions_credential_expiration
description: Step Functions pipeline fails silently when local AWS credentials expire
metadata:
  type: feedback
---

**Problem:** Step Functions pipeline couldn't run ECS tasks when developer's local ~/.aws/credentials were stale, but failure was silent (task just didn't run)

**Why:** Step Functions doesn't use IAM roles for ECS task execution in this config - it uses developer's local boto3 credentials to invoke RunTask API

**Solution:** Implemented credential_process to auto-refresh credentials on-demand

**How to apply:** When auth fails in ECS/Lambda, check if it's using local credentials file vs IAM roles. IAM roles should always work; local credentials need auto-refresh mechanism.
```

## Red Flags (Fix Immediately)

- ❌ Steering says "X loaders" but filesystem has Y
- ❌ Steering says "run at 4:05 PM ET" but code has different cron
- ❌ Memory says "fixed in commit X" but that commit doesn't exist
- ❌ Memory older than 60 days with no update timestamp
- ❌ Code changed but steering wasn't updated
- ❌ Steering describes OLD architecture ("delete this" or "no longer used")

## Tools & Automation

**Pre-commit hook:** Checks if code changed without steering update
```bash
git diff --name-only | grep -qE "^(algo|terraform|lambda|loaders)/" && \
git diff --name-only | grep -q "steering/" || \
echo "WARNING: Code changed but steering doc unchanged"
```

**Monthly audit script:** Find stale sections in steering
```bash
# Find sections with "TODO", "FIXME", or "deprecated"
grep -n "TODO\|FIXME\|DEPRECATED\|outdated" steering/algo.md
```

**Memory staleness check:**
```bash
# Find memories not updated in 30+ days
find .claude/projects/*/memory -name "*.md" \
  -mtime +30 \
  -exec sh -c 'echo "Stale: $1"; grep "^---" "$1" | head -5' _ {} \;
```

## Success Criteria

- ✅ Steering doc matches codebase (verified monthly)
- ✅ Memory files have recent dates (within 30 days of last use)
- ✅ No broken references (memories link to valid files)
- ✅ Code changes include steering updates (checked by pre-commit)
- ✅ You can onboard a new developer and they learn from steering + memory
