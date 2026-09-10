-- Migration 1270: Add net_income_attributable_to_common to annual/quarterly income statement
--
-- Root-caused via tie_out.py's check_eps_reconciliation/check_basic_eps_reconciliation, and
-- documented in memory (eps_reconciliation_post_reload_nci_attributable_income_gap_20260907):
-- diluted/basic EPS is legitimately computed by filers against net income ATTRIBUTABLE TO
-- COMMON SHAREHOLDERS (net of noncontrolling interests and preferred dividends), while our
-- "net_income" column captures total consolidated net income. This is the EPS-side twin of
-- the balance-sheet NCI gap already closed by migration 1265 (noncontrolling_interest) -
-- REITs and other NCI-heavy entities (AAT/American Assets Trust live-confirmed: 10 straight
-- fiscal years 2011-2020, diluted_eps * shares_outstanding_diluted landing at ~65-75% of
-- net_income) structurally trip the reconciliation check for this same underlying reason.
--
-- Real SEC XBRL concepts: NetIncomeLossAvailableToCommonStockholdersDiluted (preferred, nets
-- out any preferred dividends too) falling back to
-- NetIncomeLossAvailableToCommonStockholdersBasic when only the basic variant is tagged.
-- Same table scope as accounts_payable (1263) / noncontrolling_interest (1265): annual +
-- quarterly only. Data-availability only, same as those two migrations - not yet used in any
-- scoring/quality-pillar logic or in check_eps_reconciliation itself.

ALTER TABLE annual_income_statement ADD COLUMN IF NOT EXISTS net_income_attributable_to_common NUMERIC(20, 2);
ALTER TABLE quarterly_income_statement ADD COLUMN IF NOT EXISTS net_income_attributable_to_common NUMERIC(20, 2);

COMMENT ON COLUMN annual_income_statement.net_income_attributable_to_common IS
    'Real SEC XBRL NetIncomeLossAvailableToCommonStockholdersDiluted/Basic concept - net income attributable to common shareholders, net of noncontrolling interests and preferred dividends. Used to correctly interpret diluted/basic EPS vs. total net_income for NCI-heavy filers (REITs, JVs). Not yet used in any scoring/quality-pillar logic.';
COMMENT ON COLUMN quarterly_income_statement.net_income_attributable_to_common IS
    'Real SEC XBRL NetIncomeLossAvailableToCommonStockholdersDiluted/Basic concept - net income attributable to common shareholders, net of noncontrolling interests and preferred dividends. Not yet used in any scoring/quality-pillar logic.';
