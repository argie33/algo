# 2026-09-16 Data Corruption Incident: Recovery & Prevention Guide

## Incident Summary

On 2026-09-16 at 17:56 UTC, 7 blind-copy repair scripts corrupted **1,411 financial records** by copying unreliable yfinance values directly into SEC XBRL tables without validation.

**Root Cause**: Divergence ≠ Error. The scripts assumed yfinance was authoritative without verifying data plausibility.

---

## Recovery Progress

### Phase 1: Damage Assessment ✓ COMPLETE
- **1,411 corrupted records identified** (audit in `/tmp/corruption_audit.json`)
- Categorized by severity: 68 severe (>1000x), 96 moderate (100-1000x), 1,247 mild (≤100x)
- Affected symbols: ~80+ unique symbols
- Most common fields: shares_outstanding (400+), depreciation (80+), capex (50+)

### Phase 2A: Comprehensive Recovery (In Progress)
- **Symbols reloaded**: 846 symbols across 3 statement types
- **Records restored so far**: 490 of 1,063 (46% through comprehensive reload)
- **Remaining corrupted**: 573 records
- **Targeted reload pending**: 54 most severe/moderate cases

### Phase 2B: Targeted Severe/Moderate Reload (Running)
- **Symbols queued**: 35 symbols with ratio >100x
- **Expected records**: 54 most severe cases
- **Execution**: Full-history reload via `load_financial_statements` loader

### Phase 3: Validation (Pending)
- Post-reload audit to verify all corruptions restored
- Compare with pre-corruption baseline
- Identify truly legitimate divergences

---

## Prevention Rules (From Postmortem)

### Rule 1: Never Blindly Copy Yfinance
**Why**: Yfinance is secondary source, not ground truth.

**How to Apply**:
- Always validate yfinance against industry benchmarks BEFORE copying
- For shares_outstanding: flag if <1000 (almost always garbage)
- For income statement: validate signs/magnitudes against norms
- For balance sheet: check against prior years (>10x changes are suspicious)

### Rule 2: Root-Cause Divergences Before Fixing
**Why**: Repair strategy depends on understanding WHY divergence exists.

**How to Apply**:
- Before fixing ANY divergence, investigate:
  - Does yfinance have stale/delisted/bad data?
  - Is SEC value a known scale error?
  - Is it legitimate accounting difference?
  - Does SEC value match filer's own filing?
- Document root cause in repair comments
- Only fix if cause is understood

### Rule 3: Staged Validation Before Applying Repairs
**Why**: Blind previews (10-20 rows) miss patterns; full review catches garbage.

**How to Apply**:
- Dry-run must generate FULL list of changes to file
- Review file for patterns (e.g., "all shares <1000", "all capex negative")
- Flag suspicious patterns to human reviewer
- Require explicit approval for >100 records
- For >1000 records: spot-check random 5%

### Rule 4: Separate Yfinance Validation from Repair Scripts
**Why**: Yfinance validation is complex, cross-cutting; mixing it obscures it.

**How to Apply**:
- Run `validate_yfinance_plausibility.py` BEFORE repair scripts
- Flags micro-cap garbage, negative values, extreme divergences
- Build allowlist of "yfinance known-bad for this field" per symbol
- EXCLUDE flagged records from repair candidates

### Rule 5: Maintain Pre-Repair Backups
**Why**: Database snapshots enable rollback if validation fails.

**How to Apply**:
- Before any bulk repair (>100 records), snapshot affected tables
- Store with timestamp, symbol list, expected change count
- Allow rollback from snapshot on corruption discovery
- Delete after 24h validation confirms no corruption

---

## Key Findings

### Yfinance Unreliability Factors
- **Micro-caps** (<$5-10M market cap): tiny garbage share counts (24, 69, 288)
- **Delisted/bankrupt**: stale data from last trade
- **ADRs/cross-listed**: currency/scale confusion
- **Unusual structures**: shell companies, SPACs often have bad data
- **Field-level**: depreciation, capex, shares especially unreliable

### Legitimate Divergence Categories
1. **Scale errors**: Unit/period mismatch (thousands vs millions)
2. **Currency mismatch**: ADRs with conversion confusion
3. **Accounting methods**: Revenue timing, consolidation scope
4. **Reporting timing**: Preliminary vs final, etc.

### What Went Right
- **Cross-session monitoring**: algo-d2 detected corruption quickly
- **Distinctive patterns**: Micro-cap garbage was unmistakable
- **Early halt**: Within minutes, preventing cascade

---

## How to Use Recovery Scripts

### Comprehensive Audit (Current State)
```bash
python scripts/audit_corruption_damage.py
# Outputs: /tmp/corruption_audit.json with all corrupted records
```

### Comprehensive Corruption Recovery
```bash
python scripts/comprehensive_corruption_recovery.py --dry-run    # Preview
python scripts/comprehensive_corruption_recovery.py --fix        # Execute
# Reloads all 846 corrupted symbols from SEC XBRL source
```

### Targeted Severe/Moderate Recovery
```bash
python scripts/full_history_reload_corrupted.py --dry-run   # Preview
python scripts/full_history_reload_corrupted.py --fix       # Execute
# Reloads only ratio>100x records (~35 symbols, 54 records)
```

### Validate Yfinance Plausibility
```bash
python scripts/validate_yfinance_plausibility.py --output /tmp/unreliable.json
# Flags micro-cap garbage, negative values, extreme divergences
```

### Generate Divergence Report
```bash
python scripts/generate_divergence_recovery_report.py --output /tmp/divergence_report.json
# Categorizes remaining divergences by type & severity
```

---

## Post-Recovery Verification Checklist

- [ ] Re-run `audit_corruption_damage.py` and confirm 0 corrupted records
- [ ] Cross-check pre-corruption snapshot (if exists) against current data
- [ ] Sample-check 10 previously-corrupted records in SEC filing
- [ ] Re-run xbrl_yfinance_crosscheck to confirm divergences moved
- [ ] Verify no unintended side-effects in dependent tables
- [ ] Commit prevention rule implementations
- [ ] Update MEMORY.md with lessons learned

---

## Cleanup Tasks

1. **Delete repair scripts** (already deleted):
   - repair_all_scale_errors_gt_100x.py
   - repair_moderate_50_100x_errors.py
   - repair_moderate_10_50x_errors.py
   - repair_minor_2_10x_errors.py
   - repair_shares_outstanding_scale_errors.py
   - repair_depreciation_and_ar_scale_errors.py
   - repair_missing_capex_and_debt.py

2. **Persist Recovery Infrastructure**:
   - audit_corruption_damage.py ✓
   - comprehensive_corruption_recovery.py ✓
   - full_history_reload_corrupted.py ✓
   - validate_yfinance_plausibility.py ✓
   - generate_divergence_recovery_report.py ✓

3. **Delete Temporary Files**:
   - /tmp/corruption_audit.json (after verification)
   - /tmp/compression_audit.log
   - scratch/*.json backup files (after 7-day retention)

4. **Documentation**:
   - This guide (CORRUPTION_RECOVERY_GUIDE.md) ✓
   - Update MEMORY.md with Prevention Rules 1-5 ✓
   - Document in CLAUDE.md: "Never run blind-copy repair scripts" ✓

---

## Lessons Learned

1. **Divergences ≠ Errors**: A divergence only means two sources disagree. Until root-cause is understood, it's unclear which is wrong.

2. **SEC is Authoritative**: For US stocks, SEC XBRL data is ground truth. Use yfinance as validation, not replacement.

3. **Validation is Hard**: Finding divergences is easy (~3,500 LOC). Fixing safely requires:
   - Understanding specific cause for each divergence
   - Validating proposed fix against multiple sources
   - Testing on sample before bulk application
   - This is manual work that doesn't automate well

4. **Staged Deployment Matters**: Even "obvious" fixes should:
   - Generate full preview (not just 10-20 row samples)
   - Flag suspicious patterns automatically
   - Require human review before --fix
   - Have rollback capability

5. **Yfinance is Unreliable for Micro-Caps**: Data quality degrades sharply below $10M market cap. Don't assume yfinance works for the full universe.

---

## Next Steps

1. Complete targeted severe/moderate reload (be11bowr7 running)
2. Re-run audit to verify remaining corruptions
3. Commit recovery scripts and prevention rules
4. Implement validation gates in divergence repair workflows
5. Document legitimate divergences in xbrl_yfinance_line_item_report
6. Update monitoring to flag similar patterns in future

---

*Recovery Guide created: 2026-09-16 (post-incident)*
*Next review: After Phase 3 validation complete*
