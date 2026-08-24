-- Migration 1227: third pass of the comparative-fact-aliasing cleanup (see 1225/1226 and
-- utils/external/sec_statements.py commit 9dc5dd36b).
--
-- These 11 (symbol, fiscal_year) rows were initially set aside as "IPO/spinoff-year
-- artifacts" without individual verification - that label was wrong (checked: most have real
-- data on file for YEARS BEFORE the flagged one, ruling out first-reporting-year sparsity).
-- Live re-verified properly via direct SEC companyfacts inspection (debug-traced SHAK's raw
-- Assets facts specifically): the filing-context-vs-fact-identity conflation this whole bug
-- class is about means every candidate fact for these (symbol, fiscal_year) combinations is
-- a comparative echo living in a LATER accn that has its own later, distinct current-period
-- value (correctly excluded by the accn-latest-end-date filter, working as designed) - the
-- filer's OWN real current-period 10-K/10-Q fact for that specific fiscal year genuinely does
-- not appear in this SEC concept at all (a real, separate data-availability gap, not this
-- aliasing bug and not fabricatable). Confirmed benign, matching the already-accepted
-- EQR/PARA "genuine sparsity" pattern - just a different specific mechanism than either of
-- those.
--
-- Scope per symbol: SHAK/UUUU/GTES/KREF/VST/FPH/INSP have no real data for ANY quarter of the
-- flagged year (all 4 nulled); CCLD/PBR/HESM/UTL have a real, correctly-populated Q4 (kept) -
-- only Q1-Q3 nulled.

WITH stale_rows (symbol, fiscal_year, fiscal_quarter) AS (
  VALUES
    ('SHAK', 2014, 1), ('SHAK', 2014, 2), ('SHAK', 2014, 3), ('SHAK', 2014, 4),
    ('UUUU', 2015, 1), ('UUUU', 2015, 2), ('UUUU', 2015, 3), ('UUUU', 2015, 4),
    ('GTES', 2017, 1), ('GTES', 2017, 2), ('GTES', 2017, 3), ('GTES', 2017, 4),
    ('KREF', 2016, 1), ('KREF', 2016, 2), ('KREF', 2016, 3), ('KREF', 2016, 4),
    ('VST', 2016, 1), ('VST', 2016, 2), ('VST', 2016, 3), ('VST', 2016, 4),
    ('FPH', 2016, 1), ('FPH', 2016, 2), ('FPH', 2016, 3), ('FPH', 2016, 4),
    ('INSP', 2017, 1), ('INSP', 2017, 2), ('INSP', 2017, 3), ('INSP', 2017, 4),
    ('PBR', 2009, 1), ('PBR', 2009, 2), ('PBR', 2009, 3),
    ('CCLD', 2021, 1), ('CCLD', 2021, 2), ('CCLD', 2021, 3),
    ('HESM', 2019, 1), ('HESM', 2019, 2), ('HESM', 2019, 3),
    ('UTL', 2010, 1), ('UTL', 2010, 2), ('UTL', 2010, 3)
)
UPDATE quarterly_balance_sheet qbs
   SET total_assets = NULL
  FROM stale_rows sr
 WHERE qbs.symbol = sr.symbol
   AND qbs.fiscal_year = sr.fiscal_year
   AND qbs.fiscal_quarter = sr.fiscal_quarter;
