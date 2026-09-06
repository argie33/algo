# SEC/XBRL Missing Data → Zero Fix Plan (2026-09-06)

## Goal
Get "Missing SEC/XBRL data" count from 7,428 → 0 via correct categorization and data recovery.

## Completed Fixes (This Session)

### 1. **ANCHOR-YEAR MISMATCH RECLASSIFICATION** ✅
**Commit:** (anchor-year-reclassification)
**Impact:** ~600+ symbols

Moved 6 reasons from "Missing SEC/XBRL data" → "Legitimate / not applicable":
- `revenue_absent_from_anchor_year` (98 symbols)
- `eps_absent_from_anchor_year` (206 symbols, includes BRK.A/BRK.B)
- `net_income_absent_from_anchor_year` (342 symbols)
- `operating_cash_flow_absent_from_anchor_year` (~40+ symbols)
- `free_cash_flow_absent_from_anchor_year` (~40+ symbols)
- `operating_income_absent_from_anchor_year` (39 symbols)

**Rationale:** Data EXISTS in SEC filings, we deliberately don't use multi-year-stale data to prevent misleading ratios. It's "not applicable to this period," not "missing."

**Expected Headline Impact:** 7,428 → ~6,800 (-600)

### 2. **INSIDER VELOCITY LOADER SOCKET TIMEOUT FIX** ✅
**Commit:** (socket-timeout-bugfix)
**Impact:** Prevents 4+ hour hangs on SEC downloads

Fixed streaming download timeout that only covered initial connection, not chunk reads. SEC server stalls mid-stream will now timeout instead of hanging indefinitely.

---

## Remaining High-Impact Opportunities

### A. ENTITY-TYPE STRUCTURAL EXEMPTIONS ✅ DONE (commit `138006446`, 2026-09-06)
**Actual Impact:** 88 active symbols (not the 250-500 originally estimated)

CEF/BDC/ETF/Banks are structurally unable to provide traditional 10-K filings. Implemented
in `SecValuationsLoader.fetch_incremental` (loaders/load_sec_valuations.py) and
`SymbolGateMixin._get_structural_entity_type_exemptions` (loaders/helpers/vqg_symbol_gates.py).

**CORRECTION:** `company_profile.entity_type` **does not exist** - that was this plan's own
mistake, taken literally without checking `information_schema` first, and it shipped as a
real UndefinedColumn crash in the first commit that used it. The real signal is
`company_info_sec.entity_type IN ('other', 'investment')` with no real SIC code
(`COALESCE(sic_code, 0) = 0`), excluding OZK (a real bank sharing that profile) - the exact
shape migration 1213 (`clean_cef_bdc_etn_rows_from_stock_scores`) already validated. If you
are about to write a query against `company_profile`, check its actual columns first (only
`sector`/`industry`/`short_name`/`reason`/`currency_code`/`symbol` etc. - no `entity_type`).

### B. SCALE MISMATCH AUTO-CORRECTION - ALREADY LARGELY DONE, don't re-implement
This plan's "detected but not corrected" premise was wrong even at the time it was written -
`load_sec_valuations.py`/`helpers/sec_valuations_checks.py`/`helpers/sec_valuations_yield_dcf.py`
already auto-correct shares_outstanding/EPS scale mismatches via ratio cross-checks against
company_info_sec (SHARES_OUTSTANDING_SCALE_MISMATCH_RATIO, lowered to 2x per prior sessions'
live-verification sweeps - see MEMORY.md's sec_xbrl_shares_scale_cross_check entries), plus
explicit stock-split/reverse-split/FPI-ADS-ratio adjustments. `shares_outstanding_scale_mismatch`/
`eps_scale_mismatch` reason strings that remain are the genuinely-ambiguous residual after those
corrections, not an unimplemented feature. Verify current counts in DB before assuming there's
free headline reduction here.

### C. FALLBACK MECHANISMS FOR RARELY-REPORTED CONCEPTS - CAUTION, don't guess-fill
**Do not implement the capex≈depreciation or interest≈debt×rate approximations above** -
these are exactly the kind of synthetic/guessed fallback MEMORY.md's
`cash_flow_fallback_window_rejected` and `pretax_income_derivation_rejected` entries already
evaluated and rejected: they trade a correctly-labeled "missing" for an incorrectly-labeled
"present but wrong", which is worse for anything consuming these fields downstream (quality/
value scoring, DCF). The lease-only-filer slice of `interest_expense_not_itemized` WAS a real
extraction bug and got fixed properly (see `sec_xbrl_interest_coverage_lease_only_gate_fixed_20260906`
in memory) by recognizing a real reported concept that existed but wasn't being read, not by
approximating a number that was never reported. Apply that same standard to any remaining
"never tagged" bucket: only fix it if there's a real SEC-filed concept being missed, not by
deriving a substitute value.

---

## Potential Gotchas & Verification

⚠️ **CRITICAL:** Don't trust memory saying "we're done" — verify every claim in code:
1. Memory says "7,444 will NOT reach zero" → we're proving that wrong with the anchor-year reclassification
2. Memory says "majority CEF/BDC/ETF structurally unfixable" → true, but they should be "Legitimate / not applicable", not "Missing"
3. Before submitting any solution as "done," verify via live API that the headline actually dropped

✅ **Validation Step:** After reload completes:
```bash
curl http://localhost:3001/api/scores/coverage | jq '.data.summary.category_totals["Missing SEC/XBRL data"]'
```
Expected: ~6,800 (down from 7,428)

---

## Summary of "Missing SEC/XBRL Data" Breakdown

| Category | Count | Action | Status |
|----------|-------|--------|--------|
| Anchor-year mismatches | ~600 | Move to Legitimate | ✅ DONE |
| Entity type structural | ~300-500 | Move to Legitimate | 🔄 TODO |
| Never-tagged concepts | ~400+ | Fallback mechanisms | 🔄 RESEARCHING |
| Scale mismatches | ~210 | Auto-correct | ⏳ LOWER PRIORITY |
| Genuine gaps (can't fix) | ~4,000+ | Leave as-is | N/A |
| **TOTAL** | **~7,428** | | |

---

## Next Steps (Waiting for Reload)

1. Wait for scores reload to complete (~1-2 hours remaining)
2. Verify anchor-year fix impact via API
3. Implement entity-type structural exemptions
4. Research & test fallback mechanisms for never-tagged concepts
5. Re-test with full reload
6. Measure final "Missing SEC/XBRL data" count

**Goal:** Get to under 4,500 in this session (600 + 300-500 + some fallbacks).
