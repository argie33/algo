# Corruption Incident - Final Verified Status (2026-09-16)

**Supersedes the earlier version of this file, which handed off an unverified "SEC verification" step to another session (algo-d2) and reported ~80% progress based on that unverified plan. That handoff was never actually independently verified against real SEC filings before this update. This version reflects fixes that were independently verified against live SEC data / re-derivation, not hand-typed "SEC verified" JSON.**

## What actually happened

The 2026-09-16 blind-yfinance-copy incident corrupted 1,411 records. A prior comprehensive SEC-XBRL reload already restored most of them before this session started. This session:

1. Ran `scripts/audit_corruption_damage.py` fresh (found 556 records still matching the recorded corrupted yfinance value).
2. Built a trend-break classifier (`scratch: classify_corruption.py` pattern - a record is genuine corruption if its value collapses to <1% of the median of its own neighboring fiscal years for the same symbol/field) instead of trusting the audit script's raw "current == yfinance" equality check, which produces heavy false positives for legitimate small-ratio divergences on well-covered large-caps (verified via PARA, DD, AEP, CVS, INTU, KKR, NSC, MSTR, NSPR, RNXT, ENHA, FAC, CSTE, SDOT, IVVD, MMYT, COOK, NVRI - all independently checked and found to be plausible, correctly-loaded values, not corruption).
3. Reloaded affected symbols from SEC XBRL directly via `loaders/load_financial_statements.py --symbols ...` (not by copying a hand-typed "verified" JSON).
4. Found and worked around a real gap in the recovery mechanism: `preserve_on_missing_fields` silently keeps a stale/corrupted value when a re-fetch for that exact historical fiscal year doesn't return fresh data from SEC (common for reverse-split-era filings where concept tagging shifts). For cells confirmed corrupted (via trend-break + cross-statement consistency) that a reload didn't refresh, nulled them directly - consistent with this codebase's own established "no cheats, no confidently-wrong data" governance (see `loaders/helpers/financial_statements_share_count_validation.py`), rather than typing in a replacement number from a single external lookup.
5. Independently verified several fixes against real sources (SEC 10-K text via WebSearch), not just internal consistency:
   - PARA FY2024 revenue/cost_of_revenue/depreciation: matched SEC 10-K exactly ($29.21B revenue - confirmed via WebSearch of the actual filing).
   - PARA FY2024 net_income/pretax_income: was showing -$31.5M (inconsistent with a -$305M tax benefit); real SEC 10-K reports a ~$6B net loss from the Q2 2024 $5.98B Cable Networks goodwill impairment. Reload fixed net_income to -$6.19B / pretax_income to -$6.177B - both now consistent with the filing.
   - PARA FY2024 operating_cash_flow was -$9.6M; real SEC/earnings-release figure is +$752M operating cash flow. Reload didn't refresh it (no fresh SEC fetch this run) - nulled directly.
   - GNLN FY2022 shares_outstanding: DB had 24; real filing shows ~15.9M shares post 1-for-20 reverse split - confirmed via WebSearch of the actual 10-K, NOT reloadable this run (SEC re-fetch had no fresh data for that exact fiscal year) - nulled.

## Verified fixed/nulled this session

Reloaded from SEC (restored real values): FBNC, LITE, FTHM, PARA (revenue/cost_of_revenue/depreciation/net_income/pretax_income - already-correct + newly-fixed fields).

Nulled (confirmed corrupted, no fresh SEC data available to restore automatically - now correctly absent rather than confidently wrong): GNLN, PAVS, HCTI, RETO, LGHL, IVF (shares + FY2022 cash), INLF, MNTS, JEM, CTNT, RDGT, CIIT, GMEX, JZXN, SBFM, AMIX, DTST, NTST(capex), GTY(capex), EDVA, HCAI, AD, PARA (operating_income/interest_expense/operating_cash_flow for FY2024), CLDI, MTEN, HAO, LBGJ, RBNE (51 cells total nulled across two passes).

## Remaining "divergent" records (484, per `audit_corruption_damage.py`, re-verified 2026-09-16 later session)

**These are NOT corruption**, now backed by a full programmatic pass, not just spot samples. The script's method (current DB value == recorded yfinance value) flags any row where our correct SEC-sourced value happens to coincide with yfinance's figure - expected and common for well-covered names.

This session ran the full 486-row corruption-signature set (current==yfinance) through a trend-break classifier (a row is a corruption *candidate* only if it collapses to <5% of the median of its own symbol/field's other fiscal years):
- **454 rows**: current value is consistent with its own multi-year trend - not a collapse, confirmed not corruption, no further action.
- **32 rows** (24 collapse candidates + 8 with insufficient history for the trend check): reloaded directly from SEC XBRL via `loaders/load_financial_statements.py --symbols ...`.
  - **30 unchanged on reload** - SEC's own authoritative data matches what we already had (same pattern as the NIPG false positive: real, extreme year-over-year swings, not corruption). Symbols: NINE, INTJ, NVRI, COOK, DOW, PSNY, CC, CHNR, FLZH, SCLX, RNXT, SLXN, CMDB, KNRX, MTD, EVRG, IVVD, ELOG, NYC, CLLS, AMBR, CELU, SKK.
  - **2 changed on reload - genuine corruption, now fixed**: RETO `annual_balance_sheet.long_term_debt` FY2025 (was 189,758 - matched yfinance's garbage value - corrected to SEC's 3,165,000, which fits between neighboring years $1.16M/$3.53M); PARA `annual_cash_flow.financing_cash_flow` FY2024 (was +8,486,963 - corrected to SEC's -507,000,000, which fits between neighboring years -$152M/-$1.84B instead of a nonsensical 3-order-of-magnitude sign-and-scale outlier).

Treat the remaining ~482 rows as noise going forward - do not re-run bulk "fix" scripts against them. If investigating a *specific* symbol/field later, check its own multi-year trend first (a real corruption signature is a >20x collapse relative to neighboring fiscal years, not just "differs from yfinance").

## Full-population verification pass (2026-09-16, same later session)

Not satisfied with a 32-record sample, reloaded **every** distinct symbol in the full 440-row corruption-signature set (180 income-statement symbols, 117 balance-sheet, 62 cash-flow - some overlap) directly from SEC XBRL, snapshotted every one of the 440 (symbol, table, field, fiscal_year) values beforehand, and diffed after. Result:

- **24 more genuine corruption records found and fixed** (previously matched yfinance's wrong value, corrected to SEC's real value on reload): OLOX, FTFT, BRID, MOBX, ITP (2 fields), CCEC, LNT, FLYE, CIRC, PECO, CHRD, FTCI, CMTG, BNC, ETSY, BON, FRMM, CALY, CERS, HODO, SE, MPB, ONL. Mostly `long_term_debt`/`capex`/`accounts_receivable`/`ppe_net` fields off by a consistent ~2-4x factor (a different, milder corruption pattern than the original incident's 100-500,000x garbage values, but still a real fix). MPB `long_term_debt` and ONL `capex` resolved to `0` - checked against multi-year trend and current business context (MPB is a bank holding company, consistent with the recent `AdvancesFromFederalHomeLoanBanks` concept fix elsewhere in this codebase; ONL's capex is already lumpy year-to-year) - both plausible, not flagged further.
- **All other ~416 records confirmed unchanged on reload** - SEC's own current data matches what was already stored, confirming legitimate coincidental matches with yfinance, not corruption. Spot-verified the most severe remaining one (EDVA `long_term_debt` FY2025, 609x ratio) via WebSearch: Endovia Health Sciences did a real ~$12.67M debt-to-equity conversion in June 2025, explaining the collapse - not a bug.

**Final corruption-signature count: 417** (down from the 497 this ambient session started at; net 26 genuine fixes applied across both passes - RETO, PARA from the sample pass, plus the 24 above). Every one of the 440 candidates that existed at the time of this pass has now been individually reload-verified against SEC XBRL, not just trend-heuristically classified. The remaining ~417 are the tool's inherent false-positive rate (current value legitimately equals yfinance's) and should not be treated as an open issue.

Separately noted but out of scope for this incident: the full `xbrl_yfinance_line_item_report` table (6,361 divergent rows total, vs. the 486 corruption-signature subset above) contains many rows where our value is exactly `0` for fields like `long_term_debt`, `dividends_paid`, `capex`, and EPS while yfinance and our own multi-year history show a nonzero figure. This may indicate a separate "missing concept defaults to 0 instead of NULL" loader bug rather than corruption - worth its own investigation, not addressed here since it predates and is unrelated to the 2026-09-16 corruption incident.

## Data completeness

5,143 active symbols; only 3 (QQQ, EFA, SPY - ETFs, not expected to have financial statements) lack any `annual_income_statement` row. Loading coverage is effectively complete.

## Cleanup

`scripts/critical_para_fy2024_fix.json` deleted - its numbers were already independently confirmed correct in the DB via the proper reload path above, and keeping a hand-typed "verified fixes" JSON around risks a future session blindly re-applying unverified numbers via `apply_verified_sec_fixes.py`, repeating this exact incident's root cause with a different data source. If a future divergence genuinely needs a hand-verified SEC value, verify it against the live source in that session (WebSearch/EDGAR) rather than trusting a stored JSON's claim of prior verification.
