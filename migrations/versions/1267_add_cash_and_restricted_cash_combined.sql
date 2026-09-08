-- Migration 1267: Add cash_and_restricted_cash_combined to annual/quarterly cash_flow
--
-- Root-caused via tie_out.py's check_cashflow_reconciliation: 588/many symbol-years fail
-- prior_cash + OCF + ICF + FCF ~= curr_cash beyond tolerance - not purely staleness/extraction
-- bugs. Live-confirmed via real SEC companyfacts JSON (ADP, CIK 0000008670): FY2026 OCF
-- ($5.4412B) + ICF (-$4.7138B) + FCF ($4.881B) = $5.608B, but our stored cash_and_equivalents
-- (CashAndCashEquivalentsAtCarryingValue) only changed $0.882B ($3.3478B -> $4.2301B).
--
-- Root cause: per ASU 2016-18, a filer's cash-flow statement reconciles OCF+ICF+FCF to its
-- COMBINED cash+restricted-cash total (us-gaap:CashCashEquivalentsRestrictedCashAndRestricted
-- CashEquivalents), not to unrestricted cash alone - ADP holds large restricted cash (funds
-- held for clients, a payroll processor's normal balance-sheet structure). ADP's real combined
-- total changed $5.571B FY2026 (end 2026-06-30 minus 2025-06-30), matching OCF+ICF+FCF almost
-- exactly. Affects any filer with material restricted cash: payroll processors, banks/trust
-- companies, escrow-heavy businesses - a genuine structural gap, not per-symbol noise.
--
-- Stored as its own column (not derived by subtraction from cash_and_equivalents) to avoid a
-- fragile two-concept derivation - same single-concept-per-column convention as
-- accounts_payable (migration 1263)/noncontrolling_interest (migration 1265). NULL for the
-- (majority) of filers with no material restricted cash, where cash_and_equivalents alone
-- already reconciles correctly - tie_out.py's check_cashflow_reconciliation COALESCEs to
-- cash_and_equivalents when this is NULL, so no regression for that population.
--
-- Lives on annual_balance_sheet/quarterly_balance_sheet, same table as cash_and_equivalents
-- itself (an instant/point-in-time balance-sheet concept, not a cash-flow-statement line item -
-- OCF/ICF/FCF stay on annual_cash_flow/quarterly_cash_flow unchanged).

ALTER TABLE annual_balance_sheet ADD COLUMN IF NOT EXISTS cash_and_restricted_cash_combined NUMERIC(20, 2);
ALTER TABLE quarterly_balance_sheet ADD COLUMN IF NOT EXISTS cash_and_restricted_cash_combined NUMERIC(20, 2);

COMMENT ON COLUMN annual_balance_sheet.cash_and_restricted_cash_combined IS
    'Real SEC XBRL CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents concept - the combined cash+restricted-cash total a filer''s own cash-flow statement reconciles OCF+ICF+FCF to per ASU 2016-18. NULL when the filer has no material restricted cash (cash_and_equivalents alone already reconciles). Used by check_cashflow_reconciliation as a COALESCE preference over cash_and_equivalents.';
COMMENT ON COLUMN quarterly_balance_sheet.cash_and_restricted_cash_combined IS
    'Real SEC XBRL CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents concept - the combined cash+restricted-cash total. NULL when the filer has no material restricted cash. Not yet used in any quarterly tie-out check or scoring logic.';
