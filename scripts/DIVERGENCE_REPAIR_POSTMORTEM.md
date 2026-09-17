# Divergence Repair Incident Postmortem
## 2026-09-16 Data Corruption Event

### Executive Summary
Blind application of 7 repair scripts that copied yfinance values without validation resulted in 1,411 records being corrupted with garbage data. The incident began at 17:56 UTC when repair scripts ran with `--fix` flag, targeting divergences in annual_income_statement, annual_balance_sheet, and annual_cash_flow tables.

---

### Timeline
- **17:53 UTC**: User goal set: "fix all divergent records and ensure full understanding of issues"
- **17:56 UTC**: 7 repair scripts executed with `--fix`:
  - repair_all_scale_errors_gt_100x.py: 168 records
  - repair_moderate_50_100x_errors.py: 69 records
  - repair_moderate_10_50x_errors.py: 367 records
  - repair_minor_2_10x_errors.py: 970 records
  - repair_shares_outstanding_scale_errors.py: 106 records
  - repair_depreciation_and_ar_scale_errors.py: 14 records
  - repair_missing_capex_and_debt.py: 66 records
  - **Total attempted**: 1,760 repairs
  - **Total successful**: 1,411 corruptions
- **17:58 UTC**: algo-d2 session flagged data corruption via cross-session message
- **18:00+ UTC**: Damage assessment and coordination underway

---

### Root Cause Analysis

#### Primary Cause: Blind Trust in Yfinance
The repair scripts assumed `xbrl_yfinance_line_item_report.yfinance_value` was ground truth and copied it directly into source tables without:
- Validating yfinance data (e.g., checking for micro-cap garbage)
- Checking data plausibility (shares=24, depreciation=186049 for large companies)
- Understanding WHY the divergence existed
- Reviewing whether yfinance or SEC was actually wrong

#### Secondary Cause: Unvalidated Repair Design
The scripts were designed for blind-copy without review because:
- Repairs never flagged suspicious patterns (e.g., tiny share counts for large-cap companies)
- No pre-copy validation layer existed
- No dry-run review gates before `--fix`
- Scripts output only 10-20 row previews; full logs would have revealed patterns

#### Why Yfinance Unreliable
Yfinance data quality degrades for:
- Micro-caps (symbols <$5-10M market cap)
- Delisted/bankrupt companies (stale data from last trade)
- ADRs and cross-listed securities (currency/scale confusion)
- Stocks with unusual structures (shell companies, SPACs, etc.)

The xbrl_yfinance_line_item_report table flags divergences with WARN severity - meaning "reviewed and flagged, not confirmed correct."

---

### Corruption Examples

**Worst Cases** (confirms garbage was copied):
- GNLN FY2022 shares_outstanding: 24 (31,375x error from SEC)
- EDBL FY2023 shares_outstanding_diluted: 25 (264,320x error)
- CDT FY2023 shares: 24 (27,906x error)
- EDSA FY2024 depreciation_expense: 186,049 (543,792x error)

**Pattern**: Yfinance returned absurdly tiny values for micro-caps; scripts copied them verbatim.

---

### Damage Scope

**Total Corrupted**: 1,411 records

**By Severity**:
- **Severe (>1000x ratio)**: 68 records - unmistakably wrong
- **Moderate (100-1000x ratio)**: 96 records - likely wrong
- **Mild (<=100x ratio)**: 1,247 records - plausible reporting difference vs actual corruption

**Affected Tables**:
- annual_income_statement: ~1,100 records
- annual_balance_sheet: ~200 records
- annual_cash_flow: ~110 records

**Affected Symbols**: ~80+ unique symbols

**Most Common Fields**:
- shares_outstanding_basic/diluted: ~400 records
- depreciation_expense: ~80 records
- capex: ~50 records
- operating_income: ~40 records

---

### What Went Right (Enabled Detection)

1. **Cross-session monitoring**: algo-d2 session was independently working the same problem and caught the corruption quickly
2. **Audit logging**: xbrl_yfinance_line_item_report preserved original values for unswept symbols (though not usable due to legitimate same-day updates complicating detection)
3. **Distinctive patterns**: Micro-cap garbage values were unmistakably wrong (shares=24 for GNLN is immediately flagged)
4. **Early halt**: Corruption was halted within minutes of discovery, preventing cascade through dependent systems

---

### Recovery Strategy

**Phase 1: Identify Affected Records** ✓ COMPLETE
- 1,411 records identified and classified by severity
- All stored in /tmp/corruption_audit.json with full metadata

**Phase 2: Targeted SEC Reload** IN PROGRESS
- Strategy: For each corrupted symbol/field/fiscal_year, reload ONLY that record from SEC XBRL source via load_financial_statements.py
- Rationale: SEC source is authoritative and available; targeted approach avoids full reload costs
- Execution: Symbol-by-symbol batch reload to restore correct values

**Phase 3: Validation** PENDING
- Verify all 1,411 records restored from SEC
- Re-run xbrl_yfinance_crosscheck to confirm divergences moved back to original state
- Compare with pre-corruption baseline to ensure no unintended side-effects

---

### Prevention for Future Divergence Repairs

#### Rule 1: Never Blindly Copy Yfinance
**Why**: Yfinance is a secondary source, not ground truth. Divergence means one source is wrong, not which one.

**How to Apply**:
- Always validate yfinance data against industry benchmarks before copying
- For shares_outstanding: validate against max observed in that symbol's history, flag if <1000
- For income statement fields: validate signs/magnitudes against industry norms
- For balance sheet fields: check against prior fiscal years (sudden >10x changes are suspicious)

#### Rule 2: Root-Cause Divergences Before Fixing
**Why**: Repair strategy depends on understanding root cause (scale error, currency mismatch, accounting method change, corruption, data stale, etc)

**How to Apply**:
- Before fixing ANY divergence, investigate:
  - Does yfinance have stale/delisted/bad data? (check yfinance history and recent changes)
  - Is SEC value a known scale error? (check XBRL unit/scale factors)
  - Is it a legitimate accounting difference? (e.g., revenue recognition timing, consolidation scope)
  - Does SEC value match filer's own filing data? (cross-check filing HTML)
- Document root cause in repair comments
- Only fix if cause is understood and fix is correct

#### Rule 3: Staged Validation Before Applying Repairs
**Why**: Blind previews (10-20 rows) miss patterns; full review catches garbage

**How to Apply**:
- Dry-run must generate FULL list of changes to a file, not just previews
- Review file for patterns (e.g., "all shares values <1000", "all capex negative")
- Flag any suspicious patterns to human reviewer
- Require explicit approval before `--fix` for any repair affecting >100 records
- For >1000 records: require sampling-based spot checks on random 5% of records

#### Rule 4: Separate Yfinance Validation from Repair Scripts
**Why**: Yfinance validation is complex and cross-cutting; mixing it with repair logic obscures it

**How to Apply**:
- Create validate_yfinance_plausibility.py that checks:
  - Micro-cap (<$10M) share counts <=1,000 (likely garbage from yfinance)
  - Negative values for inherently-positive fields (capex, revenue, etc)
  - Values >1000x divergent from stock-split-adjusted history
  - Signs inconsistent with industry norms
- Run validation BEFORE repair scripts
- Flag unreliable yfinance data and EXCLUDE from repair candidates
- Build allowlist of "yfinance is known-bad for this field" per symbol (e.g., GNLN shares)

#### Rule 5: Maintain Pre-Repair Backups
**Why**: Database state snapshots enable rollback if validation fails

**How to Apply**:
- Before any bulk repair (>100 records), take snapshot of affected tables
- Store snapshot file with timestamp, symbol list, expected change count
- On corruption discovery, allow rollback from snapshot
- Delete snapshots after validation confirms no-corruption for 24h

---

### Lessons for Future Work

1. **Divergences ≠ Errors**: A divergence only means two sources disagree. Until root-cause is understood, it's unclear which is wrong.

2. **Yfinance is Not Ground Truth**: Yfinance is useful for:
   - Large-cap US stocks (generally reliable)
   - Broad trend validation
   - Detecting major data issues

   But unreliable for:
   - Micro-caps, delisted, ADRs
   - Precise historical values
   - Field-level accuracy

3. **SEC Source is Authoritative**: When a divergence involves SEC vs yfinance, SEC is authoritative for US stocks. Use yfinance as validation, not replacement.

4. **Validation is the Hard Part**: Finding divergences is easy (~3500 lines of code). Fixing them safely requires:
   - Understanding the specific cause for each divergence
   - Validating the proposed fix against multiple sources
   - Testing on a sample before bulk application
   - This is manual work that doesn't automate well

---

### Remediation in Progress

- [ ] Restore all 1,411 corrupted records from SEC XBRL source (algo-d2 session)
- [ ] Validate restored data matches SEC source
- [ ] Re-run xbrl_yfinance_crosscheck to confirm state matches pre-corruption
- [ ] Document which divergences were legitimate (not corruption) vs which were SEC errors
- [ ] Implement validation rules above to prevent blind-copy repairs
- [ ] Add pre-fix approval gates for large repairs

---

### Files/References

- Corruption audit: /tmp/corruption_audit.json (1,411 records)
- Repair scripts: scripts/repair_*.py (disabled, do not use)
- Detection script: scripts/identify_corruption.py
- Validation tool (pending): validate_yfinance_plausibility.py
- Recovery tool (prepared): revert_corruption_from_report.py (for future reference)
- Recovery in progress: algo-d2 session (targeted SEC reload)

---

### Team Coordination

- **algo-49** (this session): Repair orchestration, damage assessment, audit generation
- **algo-d2**: Root-cause analysis, recovery strategy, SEC reload execution

---

*Postmortem completed: 2026-09-16 18:15 UTC*
*Recovery status: IN PROGRESS (targeting 100% restoration from SEC source)*
