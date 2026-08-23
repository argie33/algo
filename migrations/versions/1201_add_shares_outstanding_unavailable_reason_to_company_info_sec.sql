-- Migration 1201: Add shares_outstanding_unavailable_reason to company_info_sec
--
-- ISSUE: shares_outstanding is explicitly best-effort in load_company_info_sec.py (a NULL
-- here doesn't fail the whole row - entity_name/sic_code etc. are still real and useful),
-- but when it IS null there was no field explaining why, unlike every other partial-field
-- gap in this codebase (quality_metrics/growth_metrics/value_metrics all have dozens of
-- *_unavailable_reason siblings for exactly this reason). Live audit (goal session,
-- "Ownership data unresolved" bucket investigation) found 1,237 active-universe rows with
-- shares_outstanding NULL and data_unavailable=false, and had to manually decompose them via
-- ad-hoc SQL to confirm none were a new bug:
--   - 1,035 are foreign private issuers (is_foreign_private_issuer=true) - the loader's own
--     restrict_to_domestic_forms guard (see load_company_info_sec.py's 2026-08-19 comment on
--     AEM's stale 6-K fact) deliberately excludes 20-F/40-F/6-K facts to avoid a wrong-scale
--     ADS-ratio bug, by design.
--   - 152 have has_annual_report_filing=false - closed-end funds/trusts that never file
--     10-K/20-F at all (see migration 1193's own CEF investigation), so the cover-page
--     dei:EntityCommonStockSharesOutstanding fact this loader looks for structurally can't
--     exist for them.
--   - 50 are real 10-K/20-F filers where the loader still found nothing - live-confirmed via
--     symbol inspection this is overwhelmingly dual/multi-class tickers (DGICA/DGICB,
--     FWONA/FWONK, GLIBA/GLIBK, LLYVA/LLYVK, MKC/MKC.V, UHAL/UHAL.B, WLY/WLYB, Ford's
--     non-public Class B, ...) and royalty trusts reporting "units" not "shares" (SBR/SJT/
--     PBT/CRT) - the same already-triaged structural EDGAR limitation as the dual-class
--     primary-ticker gap found in a prior session, not a new code bug.
--
-- FIX: surface which of these 3 buckets applies directly on the row, computed from data the
-- loader already has in hand (is_foreign_private_issuer/has_annual_report_filing), so this
-- decomposition doesn't need re-deriving by hand next time, and any future *new* unexplained
-- case (a real single-class 10-K filer with no shares data) is visibly distinct from these 3
-- known structural categories instead of blending into the same silent NULL.

ALTER TABLE company_info_sec ADD COLUMN IF NOT EXISTS shares_outstanding_unavailable_reason TEXT;

COMMENT ON COLUMN company_info_sec.shares_outstanding_unavailable_reason IS
    'Set only when shares_outstanding is NULL on an otherwise-available row (data_unavailable=false). One of: fpi_shares_excluded_domestic_only (20-F/40-F/6-K facts deliberately excluded, see restrict_to_domestic_forms), no_annual_report_filing (CEF/trust - never files 10-K/20-F), or shares_outstanding_not_in_xbrl_or_filing_text (real annual-report filer, likely dual/multi-class or a unit trust - all 3 pathways exhausted). NULL = shares_outstanding is populated, or predates this migration.';
