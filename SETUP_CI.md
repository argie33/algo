# Setting Up Robust CI to Catch Import Errors

## Current State

✅ **CI validation script is ready**: `scripts/ci_validation.py`  
✅ **Pre-commit configuration defined**: `.pre-commit-config.yaml`  
✅ **GitHub Actions workflow ready**: `.github/workflows/ci-validation.yml`  
❌ **Pre-commit framework not installed** (optional but recommended)  
❌ **Dashboard is currently BROKEN** (signals.py, trades.py, positions.py are empty)

## Installation Steps

### Step 1: Install Pre-Commit Framework (Recommended)
```bash
pip install pre-commit
pre-commit install
```

After installation, the CI validation will **automatically run before every commit** and **block commits with broken imports**.

### Step 2: Run CI Validation Manually (Anytime)
```bash
# Test all imports
python scripts/ci_validation.py

# This will show you exactly what's broken
```

### Step 3: Fix Broken Dashboard Code

The current dashboard is broken. You must do ONE of these:

**Option A: Restore missing functions** (recommended)
```bash
# Get signals.py from git history
git show 471d5020e^:tools/dashboard/panels/signals.py > tools/dashboard/panels/signals.py

# Get trades.py
git show 471d5020e^:tools/dashboard/panels/trades.py > tools/dashboard/panels/trades.py

# Get positions.py  
git show 471d5020e^:tools/dashboard/panels/positions.py > tools/dashboard/panels/positions.py
```

**Option B: Remove broken imports**
Edit `tools/dashboard/panels/__init__.py` and comment out lines 57-66:
```python
# from .signals import (
#     panel_signals_compact,
#     panel_signals_expanded,
# )
# from .trades import (
#     panel_recent_trades,
#     panel_trades_expanded,
# )
```

Then remove from `__all__` on lines 84-87:
```python
#     "panel_signals_compact",
#     "panel_signals_expanded",
```

### Step 4: Verify CI Passes
```bash
python scripts/ci_validation.py
# Should show: Results: 4/4 passed
```

## How CI Catches Issues

### Layer 1: Pre-Commit Hook (Local, Before Commit)
- Automatically runs `scripts/ci_validation.py`
- Tests all Python imports work
- **Blocks commit if validation fails**
- No broken code can be committed

### Layer 2: GitHub Actions (On Every Push/PR)
- `.github/workflows/ci-validation.yml` runs on every push/PR to main
- Same validation script runs
- **Blocks merge if validation fails**
- Catches anything missed locally

### Layer 3: Manual Check
- Run `python scripts/ci_validation.py` anytime
- Shows exactly what's broken

## What Gets Caught

The CI validation tests these critical imports:
1. `tools/dashboard/dashboard.py` - main module
2. `tools/dashboard/fetchers.py` - data fetching
3. `tools/dashboard/panels/__init__.py` - all panel definitions
4. `tools/dashboard/utilities.py` - shared utilities

If ANY of these fail to import, **CI blocks the commit**.

## Current Broken Imports

```
CRITICAL ISSUES:
- signals.py: Missing panel_signals_compact, panel_signals_expanded
- trades.py: Missing panel_recent_trades, panel_trades_expanded  
- positions.py: Missing panel_positions

STATUS: CI validation shows 0/4 passing
ACTION: Must fix by restoring or removing broken imports
```

## Testing the CI

### Test 1: Verify Hook Configuration
```bash
cat .pre-commit-config.yaml | grep -A 5 "ci-validation"
```
Should show the hook is configured.

### Test 2: Run Validation
```bash
python scripts/ci_validation.py
```
Currently shows broken state. After fixing, will show all passing.

### Test 3: Test Broken Imports Are Caught
Temporarily break a module:
```bash
# Break utilities.py
echo "# broken" >> tools/dashboard/utilities.py

# Run validation - should fail
python scripts/ci_validation.py  # Shows FAILURE

# Restore
git checkout tools/dashboard/utilities.py
```

## Next Steps

1. **Run validation**: `python scripts/ci_validation.py`
2. **Fix broken modules** (Option A or B above)  
3. **Verify CI passes**: `python scripts/ci_validation.py`
4. **Install pre-commit framework**: `pip install pre-commit && pre-commit install`
5. **Make commit** - pre-commit hook will verify imports work

## Why This Matters

Before this CI setup:
- ❌ Incomplete refactors went undetected
- ❌ Broken imports shipped without catching
- ❌ Dashboard silently failed on import

After this CI setup:
- ✅ Every commit verified to have working imports
- ✅ GitHub Actions blocks merge on broken code  
- ✅ Developers catch issues immediately on their machine
- ✅ No broken code can reach main branch

## Troubleshooting

**Q: "pre-commit: command not found"**
A: Install it: `pip install pre-commit`

**Q: Hook not running on commit**
A: Install the git hook: `pre-commit install`

**Q: CI validation shows [FAILURE]**
A: Check the error messages. Modules listed need to be fixed by restoring or removing imports.

**Q: How do I skip the hook?**
A: Not recommended, but: `SKIP=ci-validation git commit`

## References

- Pre-commit framework: https://pre-commit.com/
- GitHub Actions: https://docs.github.com/en/actions
- Steering docs: `steering/ci-strategy.md`
