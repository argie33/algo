-- Migration 1287: Seed stock_symbols + delisting_events rows for major historical
-- bankruptcies/failures that were confirmed completely absent from stock_symbols (not even
-- marked inactive) - see memory scoring_methodology_audit_survivorship_lookahead_restatement_20260912
-- and survivorship_bias_concretely_reverified_zero_rows_named_failures_20260912. Without a
-- stock_symbols row these names can never be selected as backfill candidates by the existing
-- "stock_symbols WHERE active = false" candidate-selection pattern
-- (scripts/tiingo_delisted_price_backfill.py, scripts/wayback_yahoo_delisted_price_backfill.py).
--
-- Symbol choices: use the company's real historical ticker except where it collides with an
-- unrelated symbol already live in stock_symbols today (confirmed by direct query 2026-09-13):
--   WM   -> already Waste Management Inc (active) -> use WAMUQ (WaMu's actual real post-
--           receivership OTC pink-sheet ticker, not a synthetic placeholder).
-- LEH/BSC/ENE/WCOM/SHLD/JCP/CS/TOY/FRC/SIVB/SBNY/PACW all confirmed free of collision.
-- SIVB/SBNY/PACW already exist (added by the real-time delisting-detection path) - not
-- reinserted here, ON CONFLICT DO NOTHING guards it anyway.
--
-- last_price/last_price_date left NULL except LEH, where the 2008-12-17 pink-sheet close of
-- $0.03 was directly confirmed via a live Wayback Machine archive fetch of Yahoo Finance's
-- LEHMQ.PK historical-prices page during this same session, not estimated.

INSERT INTO stock_symbols (symbol, company_name, security_name, active, data_unavailable, data_unavailable_reason)
VALUES
    ('LEH',   'Lehman Brothers Holdings Inc', 'Lehman Brothers Holdings Inc', FALSE, TRUE, 'historical_bankruptcy_backfill_2026-09-13: Chapter 11 filed 2008-09-15, delisted from NYSE'),
    ('BSC',   'The Bear Stearns Companies Inc', 'The Bear Stearns Companies Inc', FALSE, TRUE, 'historical_bankruptcy_backfill_2026-09-13: acquired by JPMorgan Chase 2008-05-30 under duress, delisted from NYSE'),
    ('WAMUQ', 'Washington Mutual Inc', 'Washington Mutual Inc (post-receivership OTC)', FALSE, TRUE, 'historical_bankruptcy_backfill_2026-09-13: FDIC receivership/seizure 2008-09-25, largest bank failure in US history; original ticker WM reused by unrelated Waste Management Inc'),
    ('ENE',   'Enron Corp', 'Enron Corp', FALSE, TRUE, 'historical_bankruptcy_backfill_2026-09-13: Chapter 11 filed 2001-12-02, delisted from NYSE'),
    ('WCOM',  'WorldCom Inc', 'WorldCom Inc', FALSE, TRUE, 'historical_bankruptcy_backfill_2026-09-13: Chapter 11 filed 2002-07-21, delisted from NASDAQ'),
    ('SHLD',  'Sears Holdings Corp', 'Sears Holdings Corp', FALSE, TRUE, 'historical_bankruptcy_backfill_2026-09-13: Chapter 11 filed 2018-10-15, delisted from NASDAQ'),
    ('JCP',   'J.C. Penney Company Inc', 'J.C. Penney Company Inc', FALSE, TRUE, 'historical_bankruptcy_backfill_2026-09-13: Chapter 11 filed 2020-05-15, delisted from NYSE'),
    ('CS',    'Credit Suisse Group AG', 'Credit Suisse Group AG', FALSE, TRUE, 'historical_bankruptcy_backfill_2026-09-13: emergency acquisition by UBS completed 2023-06-12, delisted from NYSE/SIX'),
    ('TOY',   'Toys R Us Inc', 'Toys R Us Inc', FALSE, TRUE, 'historical_bankruptcy_backfill_2026-09-13: went private via LBO 2005-07-21 (pre-collapse public history only); parent later liquidated 2018'),
    ('FRC',   'First Republic Bank', 'First Republic Bank', FALSE, TRUE, 'historical_bankruptcy_backfill_2026-09-13: FDIC receivership/seizure 2023-05-01, sold to JPMorgan Chase')
ON CONFLICT (symbol) DO NOTHING;

INSERT INTO delisting_events (symbol, detection_reason, last_price_date, last_price)
VALUES
    ('LEH',   'historical_backfill: Ch11 2008-09-15; LEHMQ.PK $0.03-0.04 confirmed 2008-12-17 via Wayback', '2008-12-17', 0.03),
    ('BSC',   'historical_backfill: acquired by JPMorgan Chase 2008-05-30 under Fed-brokered deal', NULL, NULL),
    ('WAMUQ', 'historical_backfill: FDIC receivership 2008-09-25, largest US bank failure by assets', NULL, NULL),
    ('ENE',   'historical_backfill: Chapter 11 filed 2001-12-02', NULL, NULL),
    ('WCOM',  'historical_backfill: Chapter 11 filed 2002-07-21', NULL, NULL),
    ('SHLD',  'historical_backfill: Chapter 11 filed 2018-10-15', NULL, NULL),
    ('JCP',   'historical_backfill: Chapter 11 filed 2020-05-15', NULL, NULL),
    ('CS',    'historical_backfill: emergency acquisition by UBS completed 2023-06-12', NULL, NULL),
    ('TOY',   'historical_backfill: went private via LBO 2005-07-21', NULL, NULL),
    ('FRC',   'historical_backfill: FDIC receivership 2023-05-01, sold to JPMorgan Chase', '2023-05-01', NULL)
ON CONFLICT (symbol, detection_reason) DO NOTHING;
