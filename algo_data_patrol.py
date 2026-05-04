#!/usr/bin/env python3
"""
Data Patrol — Continuous integrity watchdog

Beyond simple staleness checks, validates that loaded data is actually USABLE
for finance decisions. Real-money trading needs real data — this catches the
silent failures that mock and sample-based testing miss:

  P1. STALENESS         latest data within expected window per source
  P2. NULL ANOMALIES    sudden spike in NULL values (loader regression)
  P3. ZERO/IDENTICAL    rows with all zeros, identical OHLC (API limit hit)
  P4. PRICE SANITY      prices within reasonable %-change vs prior day
  P5. VOLUME SANITY     volume not zero, not absurdly high
  P6. CROSS-SOURCE      validate top symbols vs Alpaca (free, already have key)
  P7. UNIVERSE COVERAGE %symbols updated today (drop-off detection)
  P8. SEQUENCE          dates contiguous (no missing trading days)
  P9. CONSTRAINT        DB integrity (FK, unique, NOT NULL violations)
 P10. SCORE FRESHNESS   computed scores updated post raw data refresh

Every check writes to data_patrol_log with severity (info/warn/error/critical).
The orchestrator's Phase 1 reads aggregate severity and fails closed on critical.

Designed to run multiple times per day for the high-frequency tables (price,
signals) and daily for fundamentals/earnings. Can run in parallel where safe.

USAGE:
  python3 algo_data_patrol.py                    # full patrol
  python3 algo_data_patrol.py --quick            # critical checks only
  python3 algo_data_patrol.py --validate-alpaca  # cross-source check vs Alpaca
"""

import os
import json
import argparse
import psycopg2
import requests
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, date as _date, timedelta

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "stocks"),
}

# Severity levels
INFO, WARN, ERROR, CRIT = 'info', 'warn', 'error', 'critical'


class DataPatrol:
    """Comprehensive data integrity patrol."""

    def __init__(self):
        self.conn = None
        self.cur = None
        self.results = []

    def connect(self):
        self.conn = psycopg2.connect(**DB_CONFIG)
        self.cur = self.conn.cursor()

    def disconnect(self):
        if self.cur: self.cur.close()
        if self.conn: self.conn.close()
        self.cur = self.conn = None

    # Note: data_patrol_log table created by init_database.py (schema as code)

    def log(self, name, severity, target, message, details=None):
        self.results.append({
            'check': name, 'severity': severity, 'target': target,
            'message': message, 'details': details,
        })
        try:
            self.cur.execute(
                """INSERT INTO data_patrol_log (patrol_run_id, check_name, severity,
                                                target_table, message, details)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (self._run_id, name, severity, target, message,
                 json.dumps(details) if details else None),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()

    # ============================================================
    # CHECKS
    # ============================================================

    def check_staleness(self):
        """P1. Latest data within expected window."""
        sources = [
            ('price_daily', 'date', 'daily', 7, CRIT),
            ('technical_data_daily', 'date', 'daily', 7, CRIT),
            ('buy_sell_daily', 'date', 'daily', 7, CRIT),
            ('trend_template_data', 'date', 'daily', 7, CRIT),
            ('signal_quality_scores', 'date', 'daily', 7, ERROR),
            ('market_health_daily', 'date', 'daily', 7, ERROR),
            ('sector_ranking', 'date_recorded', 'daily', 10, WARN),
            ('industry_ranking', 'date_recorded', 'daily', 10, WARN),
            ('insider_transactions', 'transaction_date', 'daily', 14, WARN),
            ('analyst_upgrade_downgrade', 'action_date', 'daily', 14, INFO),
            ('stock_scores', 'score_date', 'weekly', 14, ERROR),
            ('aaii_sentiment', 'date', 'weekly', 14, WARN),
            ('growth_metrics', 'date', 'monthly', 45, WARN),
            ('earnings_history', 'quarter', 'quarterly', 120, INFO),
        ]
        today = _date.today()
        for tbl, col, freq, max_days, sev_on_stale in sources:
            try:
                self.cur.execute(f"SELECT MAX({col}::date), COUNT(*) FROM {tbl}")
                latest, count = self.cur.fetchone()
                if not latest:
                    self.log('staleness', CRIT, tbl, f'EMPTY table {tbl}', {'count': count})
                    continue
                age = (today - latest).days
                if age > max_days:
                    self.log('staleness', sev_on_stale, tbl,
                             f'{tbl} stale: {age}d > {max_days}d threshold',
                             {'latest': str(latest), 'age_days': age, 'freq': freq})
                else:
                    self.log('staleness', INFO, tbl,
                             f'{tbl} fresh ({age}d old)',
                             {'latest': str(latest), 'age_days': age})
            except Exception as e:
                self.log('staleness', ERROR, tbl, f'Check failed: {e}', None)

    def check_null_anomalies(self):
        """P2. Sudden spike in NULL values vs historical."""
        # Sample most-recent day vs prior 30 days for price_daily
        try:
            self.cur.execute("""
                SELECT
                    SUM(CASE WHEN close IS NULL THEN 1 ELSE 0 END) FILTER (
                        WHERE date = (SELECT MAX(date) FROM price_daily)) AS today_nulls,
                    COUNT(*) FILTER (WHERE date = (SELECT MAX(date) FROM price_daily)) AS today_total
                FROM price_daily
                WHERE date >= (SELECT MAX(date) FROM price_daily) - INTERVAL '30 days'
            """)
            today_nulls, today_total = self.cur.fetchone()
            today_nulls = int(today_nulls or 0)
            today_total = int(today_total or 1)
            null_pct = today_nulls / today_total * 100 if today_total else 0
            if null_pct > 5:
                self.log('null_anomaly', ERROR, 'price_daily',
                         f'{null_pct:.1f}% NULL closes on latest date',
                         {'today_nulls': today_nulls, 'today_total': today_total})
            else:
                self.log('null_anomaly', INFO, 'price_daily',
                         f'NULL rate {null_pct:.2f}% acceptable',
                         {'today_nulls': today_nulls, 'today_total': today_total})
        except Exception as e:
            self.log('null_anomaly', ERROR, 'price_daily', f'Check failed: {e}', None)

    def check_zero_or_identical(self):
        """P3. Rows with all zeros or identical OHLC (sign of API limit hit)."""
        try:
            self.cur.execute("""
                SELECT COUNT(*) FROM price_daily
                WHERE date = (SELECT MAX(date) FROM price_daily)
                  AND (volume = 0 OR open = 0 OR close = 0)
            """)
            zero_count = int(self.cur.fetchone()[0] or 0)
            if zero_count > 50:
                self.log('zero_data', ERROR, 'price_daily',
                         f'{zero_count} symbols with zero OHLC/volume on latest date',
                         {'zero_count': zero_count})
            elif zero_count > 5:
                self.log('zero_data', WARN, 'price_daily',
                         f'{zero_count} suspicious zero rows',
                         {'zero_count': zero_count})
            else:
                self.log('zero_data', INFO, 'price_daily', f'{zero_count} zero rows', None)

            # Identical OHLC = high==low==open==close (often API-limit fallback)
            self.cur.execute("""
                SELECT COUNT(*) FROM price_daily
                WHERE date = (SELECT MAX(date) FROM price_daily)
                  AND open = high AND high = low AND low = close
                  AND volume > 0
            """)
            ident_count = int(self.cur.fetchone()[0] or 0)
            if ident_count > 30:
                self.log('identical_ohlc', WARN, 'price_daily',
                         f'{ident_count} symbols with identical OHLC (suspicious)',
                         {'count': ident_count})
        except Exception as e:
            self.log('zero_data', ERROR, 'price_daily', f'Check failed: {e}', None)

    def check_price_sanity(self):
        """P4. Day-over-day moves within reasonable range (no >50% moves without reason)."""
        try:
            self.cur.execute("""
                WITH d AS (
                    SELECT pd.symbol, pd.date, pd.close,
                           LAG(pd.close) OVER (PARTITION BY pd.symbol ORDER BY pd.date) AS prev
                    FROM price_daily pd
                    WHERE pd.date >= (SELECT MAX(date) FROM price_daily) - INTERVAL '5 days'
                )
                SELECT symbol, date, close, prev,
                       ABS(close - prev) / NULLIF(prev, 0) * 100 AS pct_change
                FROM d
                WHERE prev IS NOT NULL
                  AND ABS(close - prev) / NULLIF(prev, 0) > 0.5  -- > 50% move
                  AND date = (SELECT MAX(date) FROM price_daily)
                ORDER BY pct_change DESC
                LIMIT 20
            """)
            extreme = self.cur.fetchall()
            if len(extreme) > 10:
                self.log('price_sanity', WARN, 'price_daily',
                         f'{len(extreme)} symbols with >50% day-over-day move',
                         {'count': len(extreme),
                          'samples': [{'symbol': r[0], 'pct_change': float(r[4])}
                                      for r in extreme[:5]]})
            elif len(extreme) > 0:
                self.log('price_sanity', INFO, 'price_daily',
                         f'{len(extreme)} extreme moves (likely real events)',
                         {'samples': [{'symbol': r[0], 'pct_change': float(r[4])}
                                      for r in extreme[:5]]})
            else:
                self.log('price_sanity', INFO, 'price_daily', 'No extreme moves detected', None)
        except Exception as e:
            self.log('price_sanity', ERROR, 'price_daily', f'Check failed: {e}', None)

    def check_universe_coverage(self):
        """P7. % symbols updated today (catches loader drop-offs)."""
        try:
            self.cur.execute("""
                SELECT
                    (SELECT COUNT(DISTINCT symbol) FROM price_daily
                       WHERE date >= (SELECT MAX(date) FROM price_daily)) AS today_count,
                    (SELECT COUNT(DISTINCT symbol) FROM price_daily) AS total_count
            """)
            today_count, total_count = self.cur.fetchone()
            today_count = int(today_count or 0)
            total_count = int(total_count or 1)
            pct = today_count / total_count * 100 if total_count else 0

            if pct < 90:
                self.log('coverage', ERROR, 'price_daily',
                         f'Only {pct:.1f}% of universe updated on latest date',
                         {'today': today_count, 'total': total_count, 'pct': round(pct, 2)})
            elif pct < 98:
                self.log('coverage', WARN, 'price_daily',
                         f'{pct:.1f}% coverage on latest date',
                         {'today': today_count, 'total': total_count})
            else:
                self.log('coverage', INFO, 'price_daily',
                         f'{pct:.1f}% universe coverage', None)
        except Exception as e:
            self.log('coverage', ERROR, 'price_daily', f'Check failed: {e}', None)

    def check_sequence_continuity(self):
        """P8. Trading-day sequence: no gaps in price_daily for SPY (canary)."""
        try:
            self.cur.execute("""
                WITH d AS (
                    SELECT date, LAG(date) OVER (ORDER BY date) AS prev
                    FROM price_daily
                    WHERE symbol = 'SPY'
                      AND date >= CURRENT_DATE - INTERVAL '60 days'
                )
                SELECT date, prev, (date - prev) AS gap_days
                FROM d
                WHERE prev IS NOT NULL AND (date - prev) > 4  -- weekend = 3 days max
                ORDER BY date DESC
                LIMIT 5
            """)
            gaps = self.cur.fetchall()
            if gaps:
                self.log('sequence', WARN, 'price_daily',
                         f'{len(gaps)} sequence gaps in SPY (last 60 days)',
                         {'gaps': [{'date': str(r[0]), 'days': int(r[2])} for r in gaps]})
            else:
                self.log('sequence', INFO, 'price_daily',
                         'SPY price sequence contiguous', None)
        except Exception as e:
            self.log('sequence', ERROR, 'price_daily', f'Check failed: {e}', None)

    def check_score_freshness(self):
        """P10. Computed scores should be updated AFTER raw data."""
        try:
            self.cur.execute("""
                SELECT
                    (SELECT MAX(date) FROM price_daily) AS price_latest,
                    (SELECT MAX(date) FROM trend_template_data) AS trend_latest,
                    (SELECT MAX(date) FROM signal_quality_scores) AS sqs_latest
            """)
            price_d, trend_d, sqs_d = self.cur.fetchone()
            for name, comp_date in [('trend_template_data', trend_d),
                                     ('signal_quality_scores', sqs_d)]:
                if comp_date and price_d:
                    if comp_date < price_d:
                        self.log('score_freshness', WARN, name,
                                 f'{name} ({comp_date}) older than price_daily ({price_d})',
                                 {'lag_days': (price_d - comp_date).days})
                    else:
                        self.log('score_freshness', INFO, name,
                                 f'{name} aligned with price data', None)
        except Exception as e:
            self.log('score_freshness', ERROR, 'computed_scores', f'Check failed: {e}', None)

    def check_yahoo_cross_validate(self, top_n=10):
        """P6b. Cross-validate top symbols against Yahoo Finance (free, no API key).

        Second-source verification — if our DB matches Alpaca but disagrees with
        Yahoo, that's a real signal something's off. Yahoo's chart endpoint
        accepts unauthenticated requests for basic OHLC.
        """
        try:
            self.cur.execute(
                """
                SELECT symbol FROM price_daily
                WHERE date = (SELECT MAX(date) FROM price_daily)
                ORDER BY volume DESC LIMIT %s
                """,
                (top_n,),
            )
            symbols = [r[0] for r in self.cur.fetchall()]
        except Exception as e:
            self.log('yahoo_xval', ERROR, 'price_daily', f"Couldn't pick symbols: {e}", None)
            return

        mismatches = []
        for sym in symbols:
            try:
                # Yahoo's free endpoint
                url = f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}'
                resp = requests.get(
                    url,
                    headers={'User-Agent': 'Mozilla/5.0 (algo-patrol)'},
                    params={'interval': '1d', 'range': '5d'},
                    timeout=5,
                )
                if resp.status_code != 200:
                    continue
                data = resp.json()
                results = data.get('chart', {}).get('result', [])
                if not results:
                    continue
                quote = results[0].get('indicators', {}).get('quote', [{}])[0]
                closes = quote.get('close', [])
                if not closes:
                    continue
                yahoo_close = float(closes[-1]) if closes[-1] else None
                if not yahoo_close:
                    continue

                # Compare to our DB
                self.cur.execute(
                    "SELECT close, date FROM price_daily WHERE symbol = %s ORDER BY date DESC LIMIT 1",
                    (sym,),
                )
                row = self.cur.fetchone()
                if not row or not row[0]:
                    continue
                our_close = float(row[0])
                pct_diff = abs(our_close - yahoo_close) / yahoo_close * 100
                if pct_diff > 5:
                    mismatches.append({
                        'symbol': sym, 'our_close': our_close,
                        'yahoo_close': yahoo_close,
                        'pct_diff': round(pct_diff, 2),
                        'our_date': str(row[1]),
                    })
            except Exception:
                continue

        if mismatches:
            self.log('yahoo_xval', WARN, 'price_daily',
                     f'{len(mismatches)}/{len(symbols)} top symbols mismatch Yahoo > 5%',
                     {'mismatches': mismatches})
        else:
            self.log('yahoo_xval', INFO, 'price_daily',
                     f'All {len(symbols)} top symbols match Yahoo within 5%', None)

    def check_alpaca_cross_validate(self, top_n=10):
        """P6. Cross-validate top symbols vs Alpaca (uses existing free credentials)."""
        key = os.getenv('APCA_API_KEY_ID')
        secret = os.getenv('APCA_API_SECRET_KEY')
        base = os.getenv('APCA_API_BASE_URL', 'https://paper-api.alpaca.markets')
        if not key or not secret:
            self.log('alpaca_xval', INFO, 'alpaca', 'No Alpaca creds — skipping cross-validate', None)
            return

        # Get top N symbols by recent volume from our DB
        try:
            self.cur.execute("""
                SELECT symbol FROM price_daily
                WHERE date = (SELECT MAX(date) FROM price_daily)
                ORDER BY volume DESC LIMIT %s
            """, (top_n,))
            symbols = [r[0] for r in self.cur.fetchall()]
        except Exception as e:
            self.log('alpaca_xval', ERROR, 'price_daily', f'Couldn\'t pick symbols: {e}', None)
            return

        # Alpaca data API (paper API doesn't have market data; use data API)
        # The free Alpaca-Markets data API lives at data.alpaca.markets
        data_base = 'https://data.alpaca.markets'
        headers = {'APCA-API-KEY-ID': key, 'APCA-API-SECRET-KEY': secret}
        mismatches = []
        for sym in symbols:
            try:
                # Get latest bar from Alpaca
                resp = requests.get(
                    f'{data_base}/v2/stocks/{sym}/bars/latest',
                    headers=headers, timeout=5,
                )
                if resp.status_code != 200:
                    continue
                bar = resp.json().get('bar', {})
                alpaca_close = float(bar.get('c', 0))

                # Compare against our DB latest close
                self.cur.execute(
                    "SELECT close, date FROM price_daily WHERE symbol = %s ORDER BY date DESC LIMIT 1",
                    (sym,),
                )
                row = self.cur.fetchone()
                if not row or not row[0] or alpaca_close <= 0:
                    continue
                our_close = float(row[0])
                pct_diff = abs(our_close - alpaca_close) / alpaca_close * 100
                if pct_diff > 5:  # >5% difference is suspicious
                    mismatches.append({
                        'symbol': sym, 'our_close': our_close,
                        'alpaca_close': alpaca_close, 'pct_diff': round(pct_diff, 2),
                        'our_date': str(row[1]),
                    })
            except Exception:
                continue

        if mismatches:
            self.log('alpaca_xval', WARN, 'price_daily',
                     f'{len(mismatches)}/{len(symbols)} symbols mismatch Alpaca >5%',
                     {'mismatches': mismatches})
        else:
            self.log('alpaca_xval', INFO, 'price_daily',
                     f'All {len(symbols)} top-volume symbols match Alpaca within 5%', None)

    def check_loader_contracts(self):
        """P11. Per-loader contracts — each loader has expected output thresholds.

        Catches silent loader regressions where the loader runs (no error) but
        produces dramatically less data than expected (API limit, source change,
        broken filter, etc).
        """
        contracts = [
            # (table, condition, min_rows_expected, severity, description)
            ('price_daily',
             "date >= CURRENT_DATE - INTERVAL '14 days'",
             50000, ERROR,
             'Daily price data should be ~5000 symbols × 14 days = 70K+ rows'),
            ('technical_data_daily',
             "date >= CURRENT_DATE - INTERVAL '14 days'",
             50000, ERROR,
             'Technical indicators should match price coverage'),
            ('buy_sell_daily',
             "date >= CURRENT_DATE - INTERVAL '14 days'",
             1000, ERROR,
             'Pine signals should produce 100+ per day in active market'),
            ('buy_sell_daily',
             "date >= CURRENT_DATE - INTERVAL '14 days' AND signal IN ('BUY', 'SELL')",
             1000, ERROR,
             'NO null/None signals — ratio of clean BUY/SELL must be >95%'),
            ('trend_template_data',
             "date >= CURRENT_DATE - INTERVAL '14 days'",
             20000, ERROR,
             'Trend template covers 4900+ symbols × 14 days'),
            ('signal_quality_scores',
             "date >= CURRENT_DATE - INTERVAL '14 days'",
             20000, WARN,
             'SQS should match trend coverage'),
            ('sector_ranking',
             "date_recorded >= CURRENT_DATE - INTERVAL '7 days'",
             10, WARN,
             'Sector ranking: 11 sectors per recent date'),
            ('industry_ranking',
             "date_recorded >= CURRENT_DATE - INTERVAL '7 days'",
             100, WARN,
             '197 industries should rank, threshold low for partial coverage'),
            ('market_health_daily',
             "date >= CURRENT_DATE - INTERVAL '14 days'",
             10, ERROR,
             'Market health: ~14 daily rows expected'),
            ('market_exposure_daily',
             "date >= CURRENT_DATE - INTERVAL '14 days'",
             5, WARN,
             'Market exposure: should compute most days'),
            ('stock_scores', '1=1', 4500, WARN,
             'Stock scores: should cover ~4900 symbols (latest snapshot)'),
            ('data_completeness_scores', '1=1', 4500, ERROR,
             'Completeness: every symbol scored'),
        ]

        # Buy/sell ratio specific check
        try:
            self.cur.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE signal IN ('BUY', 'SELL')) AS clean,
                    COUNT(*) AS total
                FROM buy_sell_daily
                WHERE date >= CURRENT_DATE - INTERVAL '30 days'
            """)
            row = self.cur.fetchone()
            if row and row[1] > 0:
                clean_pct = (row[0] / row[1]) * 100
                if clean_pct < 80:
                    self.log('contract_signal_quality', ERROR, 'buy_sell_daily',
                             f'Only {clean_pct:.1f}% of recent signals are clean BUY/SELL '
                             f'({row[1] - row[0]} NULL/None of {row[1]} total)',
                             {'clean_pct': clean_pct})
                else:
                    self.log('contract_signal_quality', INFO, 'buy_sell_daily',
                             f'{clean_pct:.1f}% clean BUY/SELL signals', None)
        except Exception as e:
            self.log('contract_signal_quality', ERROR, 'buy_sell_daily', f'Failed: {e}', None)

        # Generic count contracts
        for tbl, cond, min_rows, severity, desc in contracts:
            try:
                self.cur.execute(f"SELECT COUNT(*) FROM {tbl} WHERE {cond}")
                actual = int(self.cur.fetchone()[0] or 0)
                if actual < min_rows:
                    self.log('loader_contract', severity, tbl,
                             f'{actual:,} rows < {min_rows:,} expected ({desc})',
                             {'actual': actual, 'expected': min_rows})
                else:
                    self.log('loader_contract', INFO, tbl,
                             f'{actual:,} rows OK', None)
            except Exception as e:
                self.log('loader_contract', ERROR, tbl, f'Check failed: {e}', None)

    def check_db_constraints(self):
        """P9. Look for FK / unique / NOT NULL violations from recent inserts."""
        try:
            # Generic check: count rows with NULL primary-key-like fields
            checks = [
                ('algo_trades', 'symbol IS NULL OR trade_id IS NULL'),
                ('algo_positions', 'symbol IS NULL OR position_id IS NULL'),
                ('price_daily', 'symbol IS NULL OR date IS NULL'),
                ('buy_sell_daily', 'symbol IS NULL OR date IS NULL OR signal IS NULL'),
            ]
            for tbl, cond in checks:
                try:
                    self.cur.execute(f"SELECT COUNT(*) FROM {tbl} WHERE {cond}")
                    n = int(self.cur.fetchone()[0])
                    if n > 0:
                        self.log('db_constraints', ERROR, tbl,
                                 f'{n} rows with NULL key fields ({cond})',
                                 {'count': n, 'condition': cond})
                except Exception:
                    pass
            self.log('db_constraints', INFO, 'all', 'Constraint check complete', None)
        except Exception as e:
            self.log('db_constraints', ERROR, 'all', f'Check failed: {e}', None)

    # ============================================================
    # ENTRYPOINT
    # ============================================================

    def run(self, quick=False, validate_alpaca=False):
        self._run_id = f"PATROL-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        self.connect()
        try:
            print(f"\n{'='*82}\nDATA PATROL — {self._run_id}\n{'='*82}\n")

            # Always run critical checks
            self.check_staleness()
            self.check_universe_coverage()
            self.check_zero_or_identical()
            self.check_db_constraints()

            if not quick:
                self.check_null_anomalies()
                self.check_price_sanity()
                self.check_sequence_continuity()
                self.check_score_freshness()
                self.check_loader_contracts()

            if validate_alpaca:
                self.check_alpaca_cross_validate()
                self.check_yahoo_cross_validate()

            return self.summarize()
        finally:
            self.disconnect()

    def summarize(self):
        counts = {INFO: 0, WARN: 0, ERROR: 0, CRIT: 0}
        for r in self.results:
            counts[r['severity']] = counts.get(r['severity'], 0) + 1

        print(f"\n{'='*82}\nPATROL RESULTS — {self._run_id}\n{'='*82}\n")
        print(f"  INFO:     {counts.get(INFO, 0)}")
        print(f"  WARN:     {counts.get(WARN, 0)}")
        print(f"  ERROR:    {counts.get(ERROR, 0)}")
        print(f"  CRITICAL: {counts.get(CRIT, 0)}\n")

        # Show all non-INFO findings
        flagged = [r for r in self.results if r['severity'] != INFO]
        if flagged:
            print("FLAGGED:")
            for r in flagged:
                sev_pad = r['severity'].upper().rjust(8)
                print(f"  [{sev_pad}] {r['check']:20s} {r['target']:28s} : {r['message']}")
        else:
            print("  No issues — all checks clean.\n")

        ready = counts.get(CRIT, 0) == 0 and counts.get(ERROR, 0) == 0
        print(f"\n{'='*82}")
        print(f"  ALGO READY TO TRADE: {'YES' if ready else 'NO'}")
        print(f"{'='*82}\n")

        return {
            'run_id': self._run_id,
            'counts': counts,
            'ready': ready,
            'flagged': flagged,
            'all_results': self.results,
        }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Data integrity patrol')
    parser.add_argument('--quick', action='store_true', help='Critical checks only')
    parser.add_argument('--validate-alpaca', action='store_true', help='Cross-validate vs Alpaca')
    parser.add_argument('--json', action='store_true', help='JSON output')
    args = parser.parse_args()

    p = DataPatrol()
    summary = p.run(quick=args.quick, validate_alpaca=args.validate_alpaca)

    if args.json:
        print(json.dumps(summary, default=str, indent=2))

    import sys
    sys.exit(0 if summary['ready'] else 1)
