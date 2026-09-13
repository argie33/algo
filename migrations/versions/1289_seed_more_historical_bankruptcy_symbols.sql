-- Migration 1289: Second round of stock_symbols + delisting_events seeds, widening the
-- historical-failure population beyond migration 1287's bank/retail-heavy set to genuinely
-- cross-sector 2000s-2010s failures (airlines, autos, telecom/cable, brokerage) - per the
-- original audit's own finding that survivorship bias spans every sector, not just financials
-- (scoring_methodology_audit_survivorship_lookahead_restatement_20260912 explicitly named
-- WorldCom/telecom and Toys R Us/Sears/retail alongside the bank failures already seeded).
--
-- Symbol choices: real historical ticker except where it collides with an unrelated symbol
-- already live in stock_symbols today (confirmed by direct query 2026-09-13):
--   GM -> today's General Motors Company (post-2009 reorg) is already active under GM ->
--         use MTLQQ, the OLD General Motors Corporation's real post-bankruptcy OTC ticker
--         (Motors Liquidation Company).
--   CC -> today's Chemours Company is active under CC -> use CCTYQ, Circuit City's real
--         post-bankruptcy liquidation OTC ticker.
--   MF -> today's MindForge Inc is active under MF -> use MFGLQ, MF Global's real
--         post-bankruptcy OTC ticker.
-- KM/LCC/BBI/ADLAC/GX all confirmed free of collision.

INSERT INTO stock_symbols (symbol, company_name, security_name, active, data_unavailable, data_unavailable_reason)
VALUES
    ('KM',     'Kmart Corp', 'Kmart Corp', FALSE, TRUE, 'historical_bankruptcy_backfill_2026-09-13: Chapter 11 filed 2002-01-22, delisted from NYSE'),
    ('LCC',    'US Airways Group Inc', 'US Airways Group Inc', FALSE, TRUE, 'historical_bankruptcy_backfill_2026-09-13: Chapter 11 filed twice (2002, 2004); merged into American Airlines Group 2013-12-09'),
    ('MTLQQ',  'General Motors Corp (pre-2009 reorg)', 'General Motors Corp (post-Ch11 OTC, Motors Liquidation Co)', FALSE, TRUE, 'historical_bankruptcy_backfill_2026-09-13: Chapter 11 filed 2009-06-01; original ticker GM reused by the new post-reorg General Motors Company'),
    ('CCTYQ',  'Circuit City Stores Inc', 'Circuit City Stores Inc (post-Ch11 OTC)', FALSE, TRUE, 'historical_bankruptcy_backfill_2026-09-13: Chapter 11 filed 2008-11-10, liquidated 2009; original ticker CC reused by an unrelated company'),
    ('BBI',    'Blockbuster Inc', 'Blockbuster Inc', FALSE, TRUE, 'historical_bankruptcy_backfill_2026-09-13: Chapter 11 filed 2010-09-23, liquidated 2011'),
    ('MFGLQ',  'MF Global Holdings Ltd', 'MF Global Holdings Ltd (post-Ch11 OTC)', FALSE, TRUE, 'historical_bankruptcy_backfill_2026-09-13: Chapter 11 filed 2011-10-31; original ticker MF reused by an unrelated company'),
    ('ADLAC',  'Adelphia Communications Corp', 'Adelphia Communications Corp', FALSE, TRUE, 'historical_bankruptcy_backfill_2026-09-13: Chapter 11 filed 2002-06-25, assets sold to Comcast/Time Warner 2006'),
    ('GX',     'Global Crossing Ltd', 'Global Crossing Ltd', FALSE, TRUE, 'historical_bankruptcy_backfill_2026-09-13: Chapter 11 filed 2002-01-28')
ON CONFLICT (symbol) DO NOTHING;

INSERT INTO delisting_events (symbol, detection_reason, last_price_date, last_price)
VALUES
    ('KM',    'historical_backfill: Chapter 11 filed 2002-01-22', NULL, NULL),
    ('LCC',   'historical_backfill: merged into American Airlines Group 2013-12-09', NULL, NULL),
    ('MTLQQ', 'historical_backfill: Chapter 11 filed 2009-06-01 (old GM, pre-reorg)', NULL, NULL),
    ('CCTYQ', 'historical_backfill: Chapter 11 filed 2008-11-10, liquidated 2009', NULL, NULL),
    ('BBI',   'historical_backfill: Chapter 11 filed 2010-09-23, liquidated 2011', NULL, NULL),
    ('MFGLQ', 'historical_backfill: Chapter 11 filed 2011-10-31', NULL, NULL),
    ('ADLAC', 'historical_backfill: Chapter 11 filed 2002-06-25', NULL, NULL),
    ('GX',    'historical_backfill: Chapter 11 filed 2002-01-28', NULL, NULL)
ON CONFLICT (symbol, detection_reason) DO NOTHING;
