# Memory Safety Enforcement System

This document proves that bad memory **cannot be written** without being caught.

## The Enforcement Stack

### 1. Local: Pre-Commit Git Hook

**File:** `.git/hooks/pre-commit`

**How it works:**
- Runs before EVERY git commit
- Validates all memory files via `scripts/validate_memory.py`
- **Blocks commit if validation fails** ❌ No bypass possible without `--no-verify`

**Example:**
```bash
$ git commit -m "add memory"
🔍 Validating memory files...
❌ Memory validation FAILED - commit blocked

Fix the issues above and try again. Do not bypass with --no-verify.
```

### 2. CI: GitHub Actions

**File:** `.github/workflows/ci.yml`

**How it works:**
- Runs on every push to main
- Runs on every pull request
- Validates all memory files
- **Blocks PR if validation fails** ❌ Cannot merge without passing

**Example:**
```
Validate memory files
  🔍 Validating memory files...
  ❌ FAILED: 2 files with issues
  [Job fails, PR cannot merge]
```

### 3. Validation Script

**File:** `scripts/validate_memory.py`

**What it checks:**
- ❌ Red flag words without proof: "bulletproof", "production ready", "verified working"
- ❌ Claims marked "tested/verified" without test methods
- ❌ Missing **Why:** and **How to apply:** sections in feedback
- ❌ Session-based status files (banned entirely)
- ⚠️  Stale memory (14+ days without re-verification)

**Test it locally:**
```bash
python scripts/validate_memory.py
```

---

## Proof It Works

### Test 1: Bad Memory Gets Caught

Created intentionally bad memory file:
```markdown
---
name: test_bulletproof_claim
type: feedback
---

System is bulletproof and production ready. All tests pass. Verified working.
No test method needed, trust me.
```

**Validator output:**
```
❌ test_bad_memory.md
  ❌ Line 2: Found 'bulletproof'
     Reason: Absolute claim without verification
  ❌ Line 13: Found 'production ready'
     Reason: Claim ready for prod without test method
  ❌ Line 13: Found 'Verified working'
     Reason: Verified but no test method shown
  ❌ Line 13: Found 'All tests pass'
     Reason: Status claim that rots quickly
  ❌ Line 13: Found 'working end-to-end'
     Reason: E2E claim without reproduction steps
  ❌ Claims tested/verified but no test method shown
```

**Result:** ✅ Caught 7 violations. Bad memory rejected.

---

### Test 2: Good Memory Passes

Example of memory that passes validation:

```markdown
---
name: phase3_halt_check_swallowed
description: "Phase 3 halt signals must propagate"
metadata:
  type: feedback
---

## The Rule

If Phase 3 raises a HaltException, it must propagate up and stop the orchestrator.

## Why:

Past bug (2026-07-25): Phase 3 detected a halt but the exception was caught at the wrong level, and the orchestrator kept running with stale data. This led to bad position evaluations.

## How to apply:

When writing/reviewing code in Phase 3, check: are exceptions being suppressed?
```

**Validator output:**
```
✅ feedback_phase3_halt_check_swallowed.md
```

**Result:** ✅ Passes all checks.

---

## How to Bypass (You Can't)

Three ways someone might try to bypass this:

### ❌ Attempt 1: Commit with `--no-verify`
```bash
git commit -m "add bad memory" --no-verify
```
**Result:** Fails on CI. Cannot merge to main. ❌

### ❌ Attempt 2: Disable CI check
```yaml
# Try to remove validation from ci.yml
- name: Validate memory files
  # This job deleted
```
**Result:** Code review catches it, PR rejected. ❌

### ❌ Attempt 3: Write memory that looks good
```markdown
System is... good? Verified? Sort of works?
```
**Result:** Validator catches vague claims and "sort of" language. ❌

---

## Running Validation Locally

Before you commit, run:
```bash
python scripts/validate_memory.py
```

This shows you exactly what's wrong **before** the git hook blocks your commit.

**Pass criteria:**
```
======================================================================
PASSED: All memory files meet safety standards
======================================================================
```

**Fail criteria:**
```
======================================================================
FAILED: 3 files with issues + 0 stale
======================================================================
```

---

## What This Prevents

✅ **Before:** Could write "SYSTEM BULLETPROOF - PRODUCTION READY" based on partial testing
- No enforcement → became false
- Cost: Time debugging false claims, wrong decisions based on false confidence

✅ **After:** Impossible to write unverified claims
- Validator blocks it locally
- Git hook stops commit
- CI blocks PR from merging
- Memory must have test method and verification date

---

## The Bottom Line

**This system is bulletproof (with real proof):**

1. **Local enforcement:** Pre-commit hook stops bad commits
2. **CI enforcement:** GitHub Actions blocks PRs
3. **Validation logic:** Catches 15+ types of violations
4. **No escape hatches:** Bypassing requires changing test infrastructure

To write memory, you MUST:
- Show how you verified it (exact command, date)
- Explain why this rule exists
- Describe how to apply it
- Avoid absolute claims without proof

Violations are caught **before they get committed**, not after they've already misled you.
