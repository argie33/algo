-- Migration 1226: second pass of migration 1225 (comparative-fact-aliasing cleanup,
-- utils/external/sec_statements.py fix, commit 9dc5dd36b).
--
-- Migration 1225's detection query only matched a row when EXACTLY ONE quarter equaled Q4
-- with the OTHER quarters distinct from it. For these 13 (symbol, fiscal_year) pairs, TWO
-- quarters independently aliased to the same Q4 value in the pre-fix data (the same bug can
-- affect more than one quarter in a year when a filer omits its own current-period fact in
-- more than one subsequent filing) - 1225 correctly nulled one of the two, which then made
-- the other newly visible to a plain "one quarter equals Q4" re-scan. Live re-confirmed via
-- direct SEC re-extraction (2026-08-24) for every row below: the still-nulled quarter has no
-- real fact any more post-fix (matches the exact same signature verified for migration 1225's
-- rows), not a new/different problem.

WITH stale_rows (symbol, fiscal_year, fiscal_quarter) AS (
  VALUES
    ('AES', 2008, 3),
    ('ARLO', 2017, 3),
    ('CNDT', 2016, 2),
    ('GH', 2018, 2),
    ('GYRO', 2025, 2),
    ('HRZN', 2022, 2),
    ('KKR', 2023, 2),
    ('MSI', 2008, 3),
    ('NUTR', 2024, 3),
    ('PAGP', 2013, 2),
    ('PAL', 2025, 2),
    ('TSAT', 2024, 3),
    ('VC', 2010, 3)
)
UPDATE quarterly_balance_sheet qbs
   SET total_assets = NULL
  FROM stale_rows sr
 WHERE qbs.symbol = sr.symbol
   AND qbs.fiscal_year = sr.fiscal_year
   AND qbs.fiscal_quarter = sr.fiscal_quarter;
