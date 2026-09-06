-- Migration 1258: Add dcf_fcf_unavailable_reason to sec_valuations
-- Date: 2026-09-05

-- ROOT CAUSE (goal session: "SEC/XBRL missing data to zero" / implausible-values sweep):
-- load_value_quality_growth_metrics.py's intrinsic_value_unavailable_reason/
-- margin_of_safety_unavailable_reason (value_metrics) infer WHY the DCF returned NULL purely
-- from sec_valuations.fcf_yield's sign (see intrinsic_value_reason_from_fcf_yield in
-- loaders/helpers/vqg_shared.py) - "implausible_dcf_result" whenever fcf_yield > 0 but the
-- DCF result is NULL. That's a proxy, not the real signal: the DCF's own `fcf` input
-- (loaders/helpers/sec_valuations_dcf.py's _compute_dcf_intrinsic_value, called from
-- load_sec_valuations.py with `dcf_fcf_base` - OCF - CapEx - SBC, then adjusted by a
-- balance-sheet net-borrowing correction that fcf_yield's own FCF base never receives) can
-- differ in SIGN from fcf_yield's FCF base specifically because of that net-borrowing
-- adjustment (e.g. a large one-time debt paydown/issuance). Live-confirmed via a debug trace
-- against 17 real "implausible_dcf_result" symbols (APTV, AER, ASB, ACA, ACDC, ACU, ADMA,
-- ADUS, AEG, AGRO, AGRZ, AHCO, AIR, ALGM, ALNT, ALTO, AMCX): the DCF's actual `fcf` was
-- negative or None for 13 of 17 (hitting _compute_dcf_intrinsic_value's very first `fcf <= 0`
-- gate, well before any bounds check ever runs), not an out-of-bounds DCF result at all -
-- mislabeled as "Implausible / rejected value" in the coverage headline when the true,
-- already-recognized reason (negative_free_cash_flow) is categorized "Legitimate / not
-- applicable".
--
-- Fix: persist the real reason at the one place that has the ground truth - the DCF call
-- site in load_sec_valuations.py, which already knows dcf_fcf_base's exact value - instead of
-- re-guessing it downstream from a decoupled proxy signal. vqg_value.py now prefers this
-- column when populated, falling back to its previous fcf_yield-based inference only for
-- rows this loader hasn't reprocessed yet.

BEGIN;

ALTER TABLE sec_valuations ADD COLUMN IF NOT EXISTS dcf_fcf_unavailable_reason TEXT;

COMMENT ON COLUMN sec_valuations.dcf_fcf_unavailable_reason IS
    'Why _compute_dcf_intrinsic_value''s own fcf input (OCF - CapEx - SBC, net-borrowing-adjusted) was unusable when intrinsic_value_per_share is NULL: "negative_free_cash_flow" (fcf <= 0), "missing_cash_flow_data" (fcf is None), or "implausible_dcf_result" (fcf was positive but the DCF''s own bounds check rejected the result) - the ground-truth counterpart to fcf_yield, which uses a FCF base that does not receive the DCF-only net-borrowing adjustment and can therefore have the opposite sign.';

COMMIT;
