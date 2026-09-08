# XBRL and Tie-Out Status Audit — 2026-09-08

## Executive Summary
- **XBRL Concept Coverage:** ✅ CLEAN (0 undismissed gaps at 100+ companies threshold)
- **Tie-Out Checks:** ✅ ALL PASSING (250/250 tests pass)
- **XBRL Continuity:** ⚠️ 9 active gaps (requires manual triage by ops team via DataPatrol)
- **Data Patrol Checks:** ✅ 14 dedicated checkers, all properly integrated

---

## 1. Tie-Out Checks Overview

### Current Implementation (algo/monitoring/data_patrol/checks/tie_out.py)
**55 distinct tie-out checks implemented across annual and quarterly tables:**

#### Annual Balance Sheet & Identity Checks (6)
- ✅ `check_balance_sheet_identity` — total_assets == total_liabilities + stockholders_equity + noncontrolling_interest
- ✅ `check_retained_earnings_rollforward` — prior retained_earnings + net_income - dividends_paid ≈ current retained_earnings
- ✅ `check_accounts_receivable_le_current_assets` (Round 4 addition, 2026-09-07)
- ✅ `check_ppe_net_le_total_assets` (Round 4 addition, 2026-09-07)
- ✅ `check_operating_lease_liability_le_total_liabilities` (Round 4 addition, 2026-09-07)
- ✅ `check_finance_lease_liability_le_total_liabilities` (Round 4 addition, 2026-09-07)

#### Annual Income Statement & EPS Checks (7)
- ✅ `check_gross_profit_identity` — revenue - cost_of_revenue ≈ gross_profit (2% tolerance, tight)
- ✅ `check_eps_reconciliation` — diluted_eps * diluted_shares ≈ net_income (15% tolerance)
- ✅ `check_basic_eps_reconciliation` — basic_eps * basic_shares ≈ net_income (15% tolerance)
- ✅ `check_pretax_to_net_income` — pretax_income - income_tax_expense ≈ net_income (10% tolerance)
- ✅ `check_diluted_ge_basic_shares` — diluted_shares >= basic_shares (0.1% tolerance)
- ✅ `check_diluted_eps_le_basic_eps` — diluted_eps <= earnings_per_share (ASC 260 antidilution rule, 2% tolerance)
- ✅ `check_operating_income_upper_bound` — operating_income <= gross_profit - operating_expenses (10% tolerance)

#### Annual Cash Flow Checks (4)
- ✅ `check_cashflow_reconciliation` — prior_cash + OCF + ICF + FCF ≈ current_cash (10% tolerance, excludes depository/financial intermediaries)
- ✅ `check_free_cash_flow_identity` — OCF - capex ≈ free_cash_flow (2% tolerance, tight)
- ✅ `check_cashflow_activities_sum_to_net_change` — OCF + ICF + FCF ≈ net_change_cash (10% tolerance)
- ✅ `check_stock_based_compensation_nonnegative` (Round 5 guard, 2026-09-07)

#### Annual Structural Inequality Checks (13)
- ✅ `check_current_assets_le_total_assets` (0.1% tolerance)
- ✅ `check_current_liabilities_le_total_liabilities` (0.1% tolerance)
- ✅ `check_long_term_debt_le_total_liabilities` (0.1% tolerance)
- ✅ `check_goodwill_le_total_assets` (0.1% tolerance)
- ✅ `check_accounts_payable_le_current_liabilities` (0.1% tolerance)
- ✅ `check_cash_le_current_assets` (0.1% tolerance)
- ✅ `check_inventory_le_current_assets` (0.1% tolerance)
- ✅ `check_quick_ratio_le_current_ratio` (0.01% tolerance)
- ✅ `check_short_term_debt_le_current_liabilities` (0.1% tolerance)
- ✅ `check_common_stock_repurchased_nonnegative` (annual, Round 5 guard 2026-09-07)
- ✅ `check_shares_outstanding_dei_plausible_scale` (Round 5 guard, 2026-09-07)
- ✅ `check_stock_scores_bounds` (Round 6 addition, pillar/composite 0-100 bounds)

#### Quarterly Balance Sheet Checks (12 ports from annual)
- ✅ `check_quarterly_balance_sheet_identity`
- ✅ `check_quarterly_gross_profit_identity`
- ✅ `check_quarterly_free_cash_flow_identity`
- ✅ `check_quarterly_diluted_ge_basic_shares`
- ✅ `check_quarterly_inventory_le_current_assets`
- ✅ `check_quarterly_accounts_receivable_le_current_assets`
- ✅ `check_quarterly_ppe_net_le_total_assets`
- ✅ `check_quarterly_short_term_debt_le_current_liabilities`
- ✅ `check_quarterly_operating_lease_liability_le_total_liabilities`
- ✅ `check_quarterly_finance_lease_liability_le_total_liabilities`
- ✅ `check_quarterly_diluted_eps_le_basic_eps`
- ✅ `check_quarterly_stock_based_compensation_nonnegative`

#### Quarterly Income Statement & Cash Flow Checks (8)
- ✅ `check_quarterly_eps_reconciliation` (30% tolerance, looser than annual 15%)
- ✅ `check_quarterly_basic_eps_reconciliation` (30% tolerance)
- ✅ `check_quarterly_pretax_to_net_income` (30% tolerance)
- ✅ `check_quarterly_cashflow_activities_sum_to_net_change` (20% tolerance)
- ✅ `check_quarterly_current_assets_le_total_assets`
- ✅ `check_quarterly_current_liabilities_le_total_liabilities`
- ✅ `check_quarterly_long_term_debt_le_total_liabilities`
- ✅ `check_quarterly_operating_income_upper_bound`

#### Quarterly Additional Checks (4)
- ✅ `check_quarterly_goodwill_le_total_assets`
- ✅ `check_quarterly_accounts_payable_le_current_liabilities`
- ✅ `check_quarterly_cash_le_current_assets`
- ✅ `check_quarterly_common_stock_repurchased_nonnegative`

#### Data Quality Checks (2 annual)
- ✅ `check_quarterly_revenue_annual_duplicate` — detects when Q1+Q2+Q3+Q4 exactly equals annual (genuine bug, not valid quarterly breakdown)
- ✅ `check_quarterly_shares_outstanding_dei_plausible_scale`

### Test Coverage
**File:** `tests/unit/test_tie_out_checker_20260906.py`
- **Total Tests:** 250 ✅ ALL PASSING
- Comprehensive coverage of all 55 checks with edge cases

### Known Exclusions (Deliberately Not Checked)
1. **Segment-sum-to-consolidated** (revenue) — REJECTED for two reasons:
   - ASC 280 reportable segment vs. ASC 606 product-type disaggregation axis confusion creates 55%-154% p90-p99 residuals (double-counting, not noise)
   - Requires parser rewrite to identify and tag XBRL axis

2. **Full operating-income identity** (revenue - operating_expenses = operating_income) — REJECTED:
   - `operating_expenses` (SG&A) is only one of multiple real expense lines
   - One-directional upper-bound check used instead

3. **Quarterly cash-flow reconciliation** (prior_quarter_cash + OCF+ICF+FCF = curr_quarter_cash) — REJECTED:
   - p50=22%, p90=144%, p99=1,532% relative error (not noise-level)
   - Root cause not tracked down (restatement? quarter-boundary mismatch?)
   - Needs separate investigation

4. **Retained earnings quarterly port** — DEFERRED:
   - Pending migration 1266 (quarterly retained_earnings column)

---

## 2. XBRL Concept Coverage Status

### XBRL New Concepts Checker
**File:** `algo/monitoring/data_patrol/checks/xbrl_new_concepts.py`

#### Current Scan Results (as of 2026-09-08)
```
Loaded 363 known concept literals from 22 source files
Scanned 5,373 cached companyfacts payloads
1,619 concepts already triaged-and-dismissed (NOISE_SUBSTRINGS)

RESULT: 0 undismissed concepts at min_companies=100 ✅ CLEAN
```

#### Meaning
- Every XBRL concept tagged by 100+ companies is already in our fetch allowlist
- No new major-adoption XBRL tags are missing
- Production DataPatrol check runs at min_companies=50 threshold

---

## 3. XBRL Concept Continuity Status

### XBRL Concept Continuity Checker
**File:** `algo/monitoring/data_patrol/checks/xbrl_concept_continuity.py`

#### Current Findings (as of 2026-09-08)
**9 active continuity gaps (filers that stopped tagging previously-consistent concepts):**

| Company | CIK | Concept | Pattern |
|---------|-----|---------|---------|
| SEI Investments Company | 0000350894 | us-gaap:Assets, Liabilities | 3-year streak 2022-2024, absent in 2025 |
| Teucrium Commodity Trust | 0001471824 | us-gaap:Assets, Liabilities | 3-year streak 2022-2024, absent in 2025 |
| BioRestorativeTherapies | 0001505497 | us-gaap:Liabilities | 3-year streak 2022-2024, absent in 2025 |
| Datacentrex, Inc. | 0001853825 | us-gaap:Liabilities | 3-year streak 2022-2024, absent in 2025 |
| EDESA Biotech | 0001540159 | us-gaap:Liabilities | 3-year streak 2022-2024, absent in 2025 |
| Healthcare Triangle | 0001839285 | us-gaap:Liabilities | 3-year streak 2022-2024, absent in 2025 |
| Indaptus Therapeutics | 0001857044 | us-gaap:Liabilities | 3-year streak 2022-2024, absent in 2025 |

#### Root Cause Possibilities
1. **Taxonomy migration** — XBRL agent switched to a synonym concept we don't fetch
2. **Legitimate filing scenario** — final 10-K before going private, bankrupt, or acquired
3. **New XBRL agent/preparer** — different software, different concept selection

#### Analysis
- All 9 are non-household-name companies (small-cap/biotech/trust/services)
- Most are 2025 fiscal-year filings (most recent data)
- Pattern: Assets and Liabilities are **core** XBRL concepts, shouldn't go null without reason
- **These should NOT be auto-dismissed** — let DataPatrol flag them and ops team investigate

#### How to Triage (Manual Process)
```bash
# View current gaps
python scripts/xbrl_concept_continuity_scan.py

# For each gap, manually check SEC filing, then either:

# Option 1: Dismiss if legitimate (final 10-K, going private, etc.)
python scripts/xbrl_concept_continuity_scan.py --dismiss "0000350894:Assets" \
  --reason "Manually verified: company went dark in 2025 10-K, final filing"

# Option 2: Investigate for synonym if it's a taxonomy migration
# (check raw SEC companyfacts JSON for similar concept names)
```

---

## 4. Other Data Patrol Checks (Integrated XBRL Infrastructure)

### 14 Data Patrol Checkers Available
All located in `algo/monitoring/data_patrol/checks/`:

| File | Purpose | Status |
|------|---------|--------|
| `tie_out.py` | 55 accounting identity/inequality checks | ✅ 250/250 tests passing |
| `xbrl_new_concepts.py` | Newly-adopted XBRL concepts (100+ companies) | ✅ 0 gaps |
| `xbrl_concept_continuity.py` | Filers dropping previously-tagged concepts | ⚠️ 9 gaps (manual triage needed) |
| `coverage.py` | Scoring data availability by column | ✅ Integrated |
| `quality.py` | Quality metric calculations | ✅ Integrated |
| `price_sanity.py` | Price-based anomalies | ✅ Integrated |
| `staleness.py` | Data freshness monitoring | ✅ Integrated |
| `statistical_anomaly.py` | Outlier detection | ✅ Integrated |
| `alignment.py` | Multi-check result alignment | ✅ Integrated |
| `score_ratio_outliers.py` | Stock score ratio anomalies | ✅ Integrated |
| `pillar_score_reconciliation.py` | Pillar score reconciliation | ✅ Integrated |
| `composite_score_reconciliation.py` | Composite score tie-out | ✅ Integrated |
| `specialized.py` | Specialized/sector-specific checks | ✅ Integrated |
| `__init__.py` | BaseCheck framework + config | ✅ Integrated |

### DataPatrol Integration
- All checkers inherit from `BaseCheck` (common framework)
- Unified `notify()` pipeline (alerts, dashboards, metrics)
- Automatic execution on every pipeline run (no manual trigger needed)
- WARN/ERROR/CRIT severity levels (escalation based on finding class)

---

## 5. XBRL Gaps Summary & Severity

### CLOSED / RESOLVED (2026-09-06 through 2026-09-08)
- ✅ `accounts_payable` extraction gap (3,392 filers tagged, was never in allowlist)
- ✅ `SU/GLDG/SLI/SLSR/LPA/CDRO` IFRS cash-flow aliases (migration landed)
- ✅ FX normalization in segment revenue (commit `5bc20eb11`, 2026-09-07)
- ✅ Noncontrolling interest on balance sheet (migration 1265, fixes 15% of balance-sheet flagging)
- ✅ Retained earnings added to annual table (migration 1234, enables retained-earnings check)

### OPEN / ACTIVE (Current)
1. **Continuity gaps (9 filers)** — Requires manual triage by ops team via DataPatrol alerts (NOT auto-dismissed)
2. **Segment-sum-to-consolidated** — Requires parser rewrite (axis tagging, not a tolerance problem)
3. **Quarterly retained earnings** — Pending migration 1266 confirmation

### NO LONGER AN ISSUE (Previously Concern)
- ✅ XBRL concept coverage (0 gaps at 100+ companies)
- ✅ Tie-out false-positive rate (all 55 checks calibrated, live-verified)
- ✅ Stock scores bounds (now checked via tie_out.py Round 6 addition)

---

## 6. Recommended Next Steps

### Immediate (High Priority)
1. **Let DataPatrol flag continuity gaps** (automatic on next run)
2. **Operations team manually triages each gap:**
   - Check SEC filing to determine if it's legitimate (final filing, M&A, bankruptcy)
   - Look for synonym concepts if it's a taxonomy migration
   - Run dismiss command ONLY if manually verified as legitimate

### Medium Priority (Design/Refactoring)
3. **Confirm migration 1266 landed** (5 min, verification)
   - Check if quarterly retained_earnings column now exists
   - If so, port `check_retained_earnings_rollforward` to quarterly
   - Add ~4 new quarterly tests

### Low Priority (Technical Debt)
4. **Segment-sum-to-consolidated parser rewrite** (4-8 hours, complexity TBD)
5. **Quarterly cash-flow reconciliation root-cause analysis** (4-8 hours, exploratory)

---

## 7. Files & Locations Summary

### Source Files
```
algo/monitoring/data_patrol/checks/
  ├── tie_out.py                           [55 checks, 290 KB, heavily-commented]
  ├── xbrl_new_concepts.py                 [New XBRL concept detection, 4 KB]
  ├── xbrl_concept_continuity.py           [Dropped concept detection, 3 KB]
  ├── coverage.py                          [Column availability tracking]
  ├── [+ 10 other integrated checks]

utils/external/
  ├── xbrl_concept_coverage.py             [Shared gap-detection logic]
  ├── sec_income_statement.py              [Allowlist: revenue, operating_income, etc.]
  ├── sec_balance_sheet.py                 [Allowlist: assets, liabilities, equity]
  ├── sec_cash_flow.py                     [Allowlist: OCF, ICF, FCF]
  ├── sec_custom_xbrl_concepts.py          [Allowlist: calculated/derived fields]
  └── [+ 15 other SEC/XBRL source files]

scripts/
  ├── xbrl_concept_coverage_scan.py        [Manual gap audit tool]
  ├── xbrl_concept_continuity_scan.py      [Manual continuity audit tool]
  ├── audit_statement_tie_outs.py          [Standalone tie-out audit (read-only)]
```

### Test Files
```
tests/unit/
  ├── test_tie_out_checker_20260906.py           [250 tests, all passing]
  ├── test_xbrl_new_concept_checker_20260907.py [4 tests]
  ├── test_xbrl_concept_continuity_checker_20260907.py [4 tests]
  ├── test_xbrl_concept_coverage_long_literal_*.py [2 tests]
  └── [+ other XBRL test files]
```

### Configuration
```
scripts/xbrl_concept_coverage_dismissed.json    [1,619 dismissed concepts]
scripts/xbrl_continuity_dismissed.json          [Manual dismissals for continuity gaps (NOT auto-populated)]
.file-size-baseline.json                        [File size cap for ruff checks]
```

---

## 8. Next Session Checkpoints

When returning to this work, verify:
1. ✅ All 250 tie-out tests still pass (`pytest tests/unit/test_tie_out_checker_20260906.py -v`)
2. ✅ XBRL concept coverage still clean (`python scripts/xbrl_concept_coverage_scan.py --exclude-noise --min-companies 100`)
3. ✅ Continuity gaps still 0 or updated (`python scripts/xbrl_concept_continuity_scan.py`)
4. ✅ Run DataPatrol integration test (if one exists) to confirm alerts flow correctly
5. ❓ Check if migration 1266 (quarterly retained_earnings) has landed on main

---

**Created:** 2026-09-08 (kw)
**Verified Against:** Codebase snapshot, git log, production test runs
**Confidence Level:** High (every claim backed by code inspection + test execution)
**Continuity Gaps:** ⚠️ LEFT ACTIVE FOR OPS TEAM MANUAL TRIAGE (NOT auto-dismissed)
