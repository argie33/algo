-- Migration 1225: Null out quarterly_balance_sheet.total_assets values left over from the
-- comparative-fact-aliasing bug fixed 2026-08-24 in utils/external/sec_statements.py
-- (real-money-readiness audit continuation).
--
-- Root cause (see [[sec_statements_instant_fact_comparative_only_accn_aliasing_found_20260824]]
-- in memory): a filer's later 10-Q can carry only a prior-fiscal-year-end comparative Assets
-- fact (never re-tagging its own current-quarter value), tagged with THAT filing's own
-- fiscal-period label. Because it was the only fact in its accession, the pre-fix
-- accn-latest-end-date filter couldn't distinguish it from a genuine current-period value, so
-- it silently overwrote the real same-quarter fact via the "prefer latest end date" tiebreak.
-- The code fix (commit 9dc5dd36b) makes extraction always derive the fiscal quarter from the
-- fact's own end date instead of trusting the filing-context label - live-verified this
-- correctly re-derives real distinct quarters going forward, and correctly returns NO value
-- (rather than a wrong one) for a quarter whose only source was such a comparative echo.
--
-- These specific (symbol, fiscal_year, fiscal_quarter) rows were re-backfilled
-- (--backfill-days 99999) after the code fix landed and STILL carry their pre-fix value: live
-- re-extraction for each confirms no genuine fact exists for that quarter any more (the fix
-- correctly stopped generating a value for it - same "fetch returns nothing new, pre-existing
-- row is never revisited" gap already documented for the original 66249a0f9 contamination fix
-- and the incomplete_sec_filing sweep in migration 1220), so the stale value is provably wrong,
-- not just unconfirmed. Spot-verified 10/10 across a representative sample (CCLD, KKR x2, WEC,
-- MSI, APGE, CCEC, HRZN, KRNT, KNRX, TSAT, WRD) via direct SEC companyfacts re-fetch before
-- generalizing to this full list - not a blind bulk edit.
--
-- Scope: total_assets only (the field this bug's detection tracked and every case above was
-- individually confirmed against). Other instant balance-sheet fields on these same rows
-- (stockholders_equity, liabilities, long_term_debt, cash) may carry the same class of stale
-- value but were not individually verified here - a narrower, deliberately conservative scope,
-- left for a future pass if warranted.
--
-- Deliberately NOT setting data_unavailable/reason: this codebase's convention (see
-- load_financial_statements.py's transform(), ~line 1976-1997) always sets those two together
-- at the WHOLE-ROW level, and only when every required field is missing (total_assets AND
-- stockholders_equity both NULL for balance sheet). This is a single-field null on rows that
-- may still carry other real, required data (e.g. stockholders_equity) - setting a row-level
-- "unavailable" flag here would incorrectly hide that other data from any reader gating on it.
--
-- Real-money relevance: mostly old/thin-data historical quarters for smaller-cap names
-- (2008-2018), not today's live snapshot - see the 2026-08-24 code-fix commit for the handful
-- of more recent/active-large-cap cases (BX 2010, KKR 2011/2023) this also cleans up.

WITH stale_rows (symbol, fiscal_year, fiscal_quarter) AS (
  VALUES
    ('AES', 2008, 2),
    ('AES', 2009, 1),
    ('APGE', 2023, 1),
    ('ARLO', 2017, 2),
    ('ARLO', 2018, 1),
    ('BHB', 2011, 1),
    ('BX', 2010, 1),
    ('CCEC', 2011, 2),
    ('CCEC', 2020, 2),
    ('CCEC', 2022, 2),
    ('CCLD', 2014, 1),
    ('CCLD', 2019, 2),
    ('CHCT', 2015, 1),
    ('CNDT', 2016, 1),
    ('CNF', 2021, 3),
    ('CODX', 2017, 1),
    ('COHN', 2011, 1),
    ('CRVO', 2012, 1),
    ('CRVO', 2023, 1),
    ('CWK', 2018, 1),
    ('EPD', 2009, 1),
    ('FRPH', 2016, 1),
    ('GH', 2017, 3),
    ('GH', 2018, 1),
    ('GYRO', 2025, 1),
    ('HRZN', 2022, 1),
    ('IA', 2025, 1),
    ('KKR', 2011, 1),
    ('KKR', 2023, 1),
    ('KNRX', 2024, 2),
    ('KRNT', 2015, 3),
    ('KRNT', 2016, 2),
    ('KRNT', 2019, 2),
    ('KRNT', 2020, 3),
    ('KRNT', 2021, 2),
    ('LGND', 2011, 1),
    ('MSI', 2008, 2),
    ('MSI', 2009, 1),
    ('NEE', 2009, 1),
    ('NRP', 2010, 1),
    ('NUTR', 2024, 2),
    ('NUTX', 2011, 1),
    ('NUTX', 2014, 1),
    ('ORI', 2010, 1),
    ('ORN', 2011, 1),
    ('OTTR', 2010, 1),
    ('PAGP', 2013, 1),
    ('PAL', 2025, 1),
    ('PRGO', 2015, 2),
    ('RDCM', 2012, 2),
    ('RDCM', 2015, 1),
    ('RNAC', 2016, 1),
    ('TACT', 2011, 1),
    ('TK', 2012, 2),
    ('TK', 2016, 3),
    ('TNK', 2012, 2),
    ('TNK', 2015, 3),
    ('TSAT', 2024, 2),
    ('TSEM', 2011, 2),
    ('TUSK', 2015, 3),
    ('TUSK', 2016, 1),
    ('VC', 2010, 2),
    ('VC', 2016, 3),
    ('WEC', 2009, 1),
    ('WELL', 2010, 1),
    ('WRD', 2024, 2),
    ('XEL', 2009, 1)
)
UPDATE quarterly_balance_sheet qbs
   SET total_assets = NULL
  FROM stale_rows sr
 WHERE qbs.symbol = sr.symbol
   AND qbs.fiscal_year = sr.fiscal_year
   AND qbs.fiscal_quarter = sr.fiscal_quarter;
