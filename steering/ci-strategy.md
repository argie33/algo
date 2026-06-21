# CI/CD Strategy: Robust Import & Code Quality Validation

## Problem Statement

Commit `471d5020e` (refactor: Final batch) was **incomplete** - it deleted functions from core modules but left imports pointing to them, breaking the dashboard silently. This went undetected because:

- **MyPy**: Only does static type analysis, doesn't execute imports
- **Ruff**: Lints code but doesn't verify imports work
- **Bandit**: Excluded from dashboard scanning
- **No import validation**: No CI step verified Python modules are actually importable

Result: Broken code was committed without detection.

## Solution: Three-Layer Validation

### Layer 1: Pre-Commit Hook (Local)
**File**: `.pre-commit-config.yaml` + `scripts/ci_validation.py`

Runs **before commit** on developer machine. Catches issues immediately:
- ✓ All Python files compile (syntax check)
- ✓ Critical dashboard imports work
- ✓ No broken function references
- ✓ All utilities modules importable

**When it blocks**: Prevents commit if any import fails

```bash
# Run manually:
python scripts/ci_validation.py
```

### Layer 2: Local Linting & Type Checking
**Tools**: Ruff + MyPy

Runs **after commit** in pre-commit hook chain:
- `ruff check`: Syntax errors, undefined names (E, F categories)
- `mypy`: Type checking for type safety

### Layer 3: GitHub Actions CI/CD
**File**: `.github/workflows/ci-validation.yml`

Runs on **every push/PR** to main branch:
1. Runs full CI validation script
2. Ruff syntax check (E, F)
3. MyPy type checking
4. Blocks merge if validation fails

## Critical Imports Verified

These must **always** import successfully:

### tools/dashboard/utilities.py
- `LOAD_SEQ`, `MASCOT_COLORS`, `MASCOT_FRAMES`, `MASCOT_W`
- `G`, `R`, `Y`, `TIER_COLOR`, `TIER_SHORT`
- `normalize_positions_data()` - positions data normalization
- `compute_sector_agg()` - sector aggregation caching
- `extract_items_and_error()` - data extraction
- `validate_data_freshness()` - timestamp validation
- `record_data_quality_issue()`, `get_data_quality_report()` - diagnostics

### tools/dashboard/panels/portfolio.py
- `panel_portfolio()` - portfolio display panel
- `panel_performance_spark()` - performance metrics panel
- `panel_portfolio_perf_expanded()` - detailed P&L panel
- `_calculate_adjusted_win_rate()` - win rate calculation

### tools/dashboard/panels/sectors.py
- `_rdelta()` - relative delta calculation
- `compute_sector_agg()` - cached sector aggregation
- `panel_sector_compact()`, `panel_sectors_expanded()` - sector panels

### tools/dashboard/panels/data_extractors.py
- `safe_get_dict()`, `safe_get_field()`, `safe_get_list()` - data access

## Handling Incomplete Refactors

If a refactor deletes functions, follow this process:

1. **Before committing**:
   - Run `python scripts/ci_validation.py` locally
   - If it fails: restore the deleted functions OR complete the refactor fully
   - Never commit with broken imports

2. **If PR has broken imports**:
   - GitHub Actions will reject the merge
   - Pre-commit hook will reject the commit on rebase

3. **To complete a refactor**:
   - Either restore all deleted functions
   - Or remove all imports/exports pointing to them
   - Update `__all__` exports when changing function visibility

## Running CI Locally

```bash
# Full validation (all layers):
python scripts/ci_validation.py

# Pre-commit hook:
pre-commit run --all-files

# Individual checks:
python -m ruff check tools/ --select=E,F
python -m mypy tools/dashboard --ignore-missing-imports
```

## Future Improvements

- [ ] Add docstring validation (prevent stub implementations)
- [ ] Add dependency graph checking (detect circular imports)
- [ ] Add test coverage requirements
- [ ] Add performance regression testing
- [ ] Add security scanning (currently excluded for dashboard)

## References

- Pre-commit framework: https://pre-commit.com/
- MyPy documentation: https://mypy.readthedocs.io/
- Ruff documentation: https://docs.astral.sh/ruff/
- GitHub Actions: https://docs.github.com/en/actions
