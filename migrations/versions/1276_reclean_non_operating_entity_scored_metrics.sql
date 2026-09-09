-- Migration 1276: Re-clean closed-end fund / BDC / trust rows from stock_scores AND their
-- upstream quality_metrics/growth_metrics/value_metrics/stability_metrics source rows.
--
-- Goal (2026-09-09, /goal session: "digging into weird scoring rules"): migration 1213
-- (2026-08-20) deleted the same class of non-operating-entity rows from stock_scores alone,
-- but never touched quality_metrics/growth_metrics/value_metrics/stability_metrics - the
-- upstream tables those scores are computed FROM. Live-confirmed those upstream rows were
-- never deleted and kept being re-scored every single day since: loaders/helpers/
-- vqg_quality_batch.py's update_quality_sector_neutral_scores(), loaders/stock_scores/
-- value_metrics.py's update_value_multiples_percentiles(), loaders/stock_scores/
-- growth_scoring.py's update_growth_sector_neutral_scores(), and loaders/stock_scores/
-- momentum_scoring.py's update_rs_percentiles() are all post_run() BATCH passes that operate
-- over "every row already in the table with a non-null score", with no join back to
-- stock_symbols/company_info_sec to check the row still belongs to the active, non-fund
-- scored universe (the same check get_active_symbols(exclude_etfs=True) and every per-symbol
-- fetch_incremental() loader already apply). The per-symbol path correctly never re-inserts
-- these symbols, but the batch passes kept refreshing (new updated_at, freshly recomputed
-- sector-neutral z-scores/percentiles) whatever stale rows migration 1213 missed in the
-- upstream tables - live-confirmed RGT (Royce Global Trust, entity_type='other', sic_code
-- NULL) held quality_score=90.38, the single HIGHEST quality_score in the entire live
-- universe, with quality_metrics.updated_at/stock_scores.updated_at from THIS MORNING'S run.
-- ASA/GGN/GNT/GAM/BSTZ/BDJ/CET/ETO/HQL/GAB and ~100 more closed-end funds/trusts showed the
-- identical pattern - real, current-day scores computed from fund-level NAV/distribution
-- financials, not operating-company fundamentals, several ranking in the top few percent of
-- Quality specifically because most of their real scoring inputs (debt_to_equity, fcf_margin,
-- gross_profitability, roce_pct) are NULL for a fund and get renormalized away rather than
-- counted against them - a fund with only 3 of 8 quality components available still clears
-- the pillar's own 40%-weight floor easily.
--
-- Matches the exact classification the code fix in loaders/runner.py/utils/loaders/helpers.py
-- already uses for get_active_symbols(exclude_etfs=True) - see that function's own extensive
-- inline history. See also loaders/stock_scores/*.py's batch pass functions for the
-- accompanying code fix that stops this from recurring (adds the same active-universe join
-- to each pass's own query), landed in the same change as this migration.

DELETE FROM stock_scores tt
USING stock_symbols s
LEFT JOIN company_info_sec c ON c.symbol = s.symbol
WHERE tt.symbol = s.symbol
  AND s.active = true
  AND s.data_unavailable IS NOT TRUE
  AND (
        (s.etf IS NOT NULL AND s.etf = 'true')
        OR s.security_name ~* '\y(Warrant|Unit|Contingent Value|ETNs?|Exchange[- ]Traded Notes?|Double Long|Double Short|Inverse|Leveraged|Acquisition Corp|SPAC|Crypto|Debenture|Subordinated|Preferred|Perpetual)\y'
        OR (
              COALESCE(c.sic_code, 0) = 0
              AND COALESCE(c.entity_type, 'operating') IN ('other', 'investment')
              AND s.symbol != 'OZK'
        )
        OR s.symbol IN ('TVC', 'TVE', 'SCE$L')
        OR s.symbol IN (
            'BBDC', 'BCSF', 'CCAP', 'CION', 'CSWC', 'EQS', 'FSK', 'GAIN', 'GSBD', 'HRZN',
            'HTGC', 'ICMB', 'KBDC', 'LIEN', 'MAIN', 'NCDL', 'NMFC', 'OBDC', 'OTF', 'PFLT',
            'PFX', 'PNNT', 'PSBD', 'RWAY', 'SAR', 'SCM', 'TPVG', 'TRIN', 'TSLX'
        )
        OR s.symbol = 'GRN'
      );

DELETE FROM quality_metrics tt
USING stock_symbols s
LEFT JOIN company_info_sec c ON c.symbol = s.symbol
WHERE tt.symbol = s.symbol
  AND s.active = true
  AND s.data_unavailable IS NOT TRUE
  AND (
        (s.etf IS NOT NULL AND s.etf = 'true')
        OR s.security_name ~* '\y(Warrant|Unit|Contingent Value|ETNs?|Exchange[- ]Traded Notes?|Double Long|Double Short|Inverse|Leveraged|Acquisition Corp|SPAC|Crypto|Debenture|Subordinated|Preferred|Perpetual)\y'
        OR (
              COALESCE(c.sic_code, 0) = 0
              AND COALESCE(c.entity_type, 'operating') IN ('other', 'investment')
              AND s.symbol != 'OZK'
        )
        OR s.symbol IN ('TVC', 'TVE', 'SCE$L')
        OR s.symbol IN (
            'BBDC', 'BCSF', 'CCAP', 'CION', 'CSWC', 'EQS', 'FSK', 'GAIN', 'GSBD', 'HRZN',
            'HTGC', 'ICMB', 'KBDC', 'LIEN', 'MAIN', 'NCDL', 'NMFC', 'OBDC', 'OTF', 'PFLT',
            'PFX', 'PNNT', 'PSBD', 'RWAY', 'SAR', 'SCM', 'TPVG', 'TRIN', 'TSLX'
        )
        OR s.symbol = 'GRN'
      );

DELETE FROM growth_metrics tt
USING stock_symbols s
LEFT JOIN company_info_sec c ON c.symbol = s.symbol
WHERE tt.symbol = s.symbol
  AND s.active = true
  AND s.data_unavailable IS NOT TRUE
  AND (
        (s.etf IS NOT NULL AND s.etf = 'true')
        OR s.security_name ~* '\y(Warrant|Unit|Contingent Value|ETNs?|Exchange[- ]Traded Notes?|Double Long|Double Short|Inverse|Leveraged|Acquisition Corp|SPAC|Crypto|Debenture|Subordinated|Preferred|Perpetual)\y'
        OR (
              COALESCE(c.sic_code, 0) = 0
              AND COALESCE(c.entity_type, 'operating') IN ('other', 'investment')
              AND s.symbol != 'OZK'
        )
        OR s.symbol IN ('TVC', 'TVE', 'SCE$L')
        OR s.symbol IN (
            'BBDC', 'BCSF', 'CCAP', 'CION', 'CSWC', 'EQS', 'FSK', 'GAIN', 'GSBD', 'HRZN',
            'HTGC', 'ICMB', 'KBDC', 'LIEN', 'MAIN', 'NCDL', 'NMFC', 'OBDC', 'OTF', 'PFLT',
            'PFX', 'PNNT', 'PSBD', 'RWAY', 'SAR', 'SCM', 'TPVG', 'TRIN', 'TSLX'
        )
        OR s.symbol = 'GRN'
      );

DELETE FROM value_metrics tt
USING stock_symbols s
LEFT JOIN company_info_sec c ON c.symbol = s.symbol
WHERE tt.symbol = s.symbol
  AND s.active = true
  AND s.data_unavailable IS NOT TRUE
  AND (
        (s.etf IS NOT NULL AND s.etf = 'true')
        OR s.security_name ~* '\y(Warrant|Unit|Contingent Value|ETNs?|Exchange[- ]Traded Notes?|Double Long|Double Short|Inverse|Leveraged|Acquisition Corp|SPAC|Crypto|Debenture|Subordinated|Preferred|Perpetual)\y'
        OR (
              COALESCE(c.sic_code, 0) = 0
              AND COALESCE(c.entity_type, 'operating') IN ('other', 'investment')
              AND s.symbol != 'OZK'
        )
        OR s.symbol IN ('TVC', 'TVE', 'SCE$L')
        OR s.symbol IN (
            'BBDC', 'BCSF', 'CCAP', 'CION', 'CSWC', 'EQS', 'FSK', 'GAIN', 'GSBD', 'HRZN',
            'HTGC', 'ICMB', 'KBDC', 'LIEN', 'MAIN', 'NCDL', 'NMFC', 'OBDC', 'OTF', 'PFLT',
            'PFX', 'PNNT', 'PSBD', 'RWAY', 'SAR', 'SCM', 'TPVG', 'TRIN', 'TSLX'
        )
        OR s.symbol = 'GRN'
      );

DELETE FROM stability_metrics tt
USING stock_symbols s
LEFT JOIN company_info_sec c ON c.symbol = s.symbol
WHERE tt.symbol = s.symbol
  AND s.active = true
  AND s.data_unavailable IS NOT TRUE
  AND (
        (s.etf IS NOT NULL AND s.etf = 'true')
        OR s.security_name ~* '\y(Warrant|Unit|Contingent Value|ETNs?|Exchange[- ]Traded Notes?|Double Long|Double Short|Inverse|Leveraged|Acquisition Corp|SPAC|Crypto|Debenture|Subordinated|Preferred|Perpetual)\y'
        OR (
              COALESCE(c.sic_code, 0) = 0
              AND COALESCE(c.entity_type, 'operating') IN ('other', 'investment')
              AND s.symbol != 'OZK'
        )
        OR s.symbol IN ('TVC', 'TVE', 'SCE$L')
        OR s.symbol IN (
            'BBDC', 'BCSF', 'CCAP', 'CION', 'CSWC', 'EQS', 'FSK', 'GAIN', 'GSBD', 'HRZN',
            'HTGC', 'ICMB', 'KBDC', 'LIEN', 'MAIN', 'NCDL', 'NMFC', 'OBDC', 'OTF', 'PFLT',
            'PFX', 'PNNT', 'PSBD', 'RWAY', 'SAR', 'SCM', 'TPVG', 'TRIN', 'TSLX'
        )
        OR s.symbol = 'GRN'
      );
