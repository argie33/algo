-- Migration 1213: Clean closed-end fund / BDC / SPAC / ETN rows from stock_scores
--
-- Goal (2026-08-20): "the scores seem to still be including etfs" - the dashboard showed
-- ASA, FINS, BSTZ, GRN and similar ranking near the top of composite/factor score
-- leaderboards. Live-confirmed root cause: utils/loaders/helpers.py's
-- get_active_symbols(exclude_etfs=True) - the symbol universe every metrics/scoring loader
-- draws from - relied on (a) the stock_symbols.etf column, which only 5 legacy ETFs ever
-- populate, and (b) a security_name regex that has been silently non-functional in
-- PostgreSQL this whole time (`\b` is a literal backspace byte in Postgres regex, not a
-- word-boundary assertion - `\y` is; see that function's own comment for the full
-- investigation). Neither layer catches closed-end funds (CEFs), BDCs, or ETNs whose names
-- don't contain an obviously-fund-like word - e.g. ASA ("ASA Gold & Precious Metals Ltd"),
-- BSTZ/FINS ("...Term Trust" - bare "Trust" is deliberately not blocklisted, since it also
-- matches real REITs like Digital Realty Trust), GAM/TY/SOR ("...Investors"/"...
-- Corporation"). As a result these symbols were never excluded from the metrics/scoring
-- loaders and accumulated real (garbage) stock_scores rows - fund-level "revenue"/
-- "net_income" figures fed into quality/value/growth scoring nonsensically (GRN, an ETN,
-- showed $13B "revenue" against a market cap of a few hundred million).
--
-- Both get_active_symbols() (the write-time fix, so this doesn't recur) and
-- lambda/api/routes/scores.py's _get_stock_scores where_clause (the read-time filter, which
-- already excluded most of these via has_annual_report_filing but missed GRN specifically,
-- since an ETN's SEC filer is the issuing bank, not the note itself) were fixed in the same
-- change as this migration. This migration only cleans up the stock_scores rows that were
-- already written under the old, incomplete filter - mirrors migration 070's precedent for
-- the original etf_symbols-only cleanup.
--
-- Matches the exact classification used by the code fix: no real SEC industry
-- classification (sic_code NULL/0) combined with a non-operating-company entity_type
-- ('other'/'investment'), explicitly excluding OZK (Bank OZK - a real, large, actively-
-- filing bank that happens to share this same NULL/'other' company_info_sec profile for
-- reasons unrelated to fund structure - see get_active_symbols' comment), plus GRN (the ETN
-- that structurally can't be caught by the sic_code/entity_type signal at all, since its SEC
-- filer is Barclays Bank PLC, not GRN itself).

DELETE FROM stock_scores sc
USING stock_symbols s
LEFT JOIN company_info_sec c ON c.symbol = s.symbol
WHERE sc.symbol = s.symbol
  AND (
        (
            COALESCE(c.sic_code, 0) = 0
            AND COALESCE(c.entity_type, 'operating') IN ('other', 'investment')
            AND s.symbol != 'OZK'
        )
        OR s.symbol = 'GRN'
      );
