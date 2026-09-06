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

### A. ENTITY-TYPE STRUCTURAL EXEMPTIONS (HIGH PRIORITY)
**Estimated Impact:** 250-500+ symbols, ~0 lines of code changed

CEF/BDC/ETF/Banks are structurally unable to provide traditional 10-K filings:
- **CEF (Closed-end funds)** → file N-1A, not 10-K
- **BDC (Business development companies)** → file N-2, not 10-K
- **ETF (Exchange-traded funds)** → file N-1A, not 10-K
- **Banks (FDIC-insured)** → regulatory exemption (post-2024)

**TODO:** Query `company_profile.entity_type` and auto-categorize these as "Legitimate / not applicable"

### B. SCALE MISMATCH AUTO-CORRECTION (MEDIUM PRIORITY)
**Estimated Impact:** 210 symbols (129 shares_outstanding + 81 EPS)

Current state: Detected but not corrected.
- `shares_outstanding_scale_mismatch` (129) → could auto-fix thousands→units or vice versa
- `eps_scale_mismatch` (81) → could auto-fix basis point→percentage or vice versa

**Risk:** Low if we verify the scale direction first (ratio sanity check).

### C. FALLBACK MECHANISMS FOR RARELY-REPORTED CONCEPTS (LOWER PRIORITY)
**Estimated Impact:** 50-100+ symbols

Some concepts are legitimately rare:
- `capex_never_tagged_in_recent_filings` (435)
  - Could use: capex ≈ PPE(t) - PPE(t-1) + depreciation
  - Or: capex = depreciation (for mature companies)

- `interest_expense_not_itemized` (354)
  - Could use: interest ≈ total_debt × weighted_avg_rate
  - Or: interest = net_income - operating_income (approximation)

**TODO:** Research which fallbacks are safe without introducing more noise than signal.

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
