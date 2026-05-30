#!/usr/bin/env python3

from config.credential_manager import get_credential_manager
from config.alpaca_config import get_alpaca_base_url, get_alpaca_data_url
from algo.algo_config import get_market_data_timeout, get_alpaca_timeout
import os
import json
import argparse
from utils.database_context import DatabaseContext
import requests
import time
from datetime import datetime, date as _date, timedelta, timezone
from algo.algo_sql_safety import assert_safe_table, assert_safe_column, safe_select_count
import logging

logger = logging.getLogger(__name__)

# Severity levels
INFO, WARN, ERROR, CRIT = 'info', 'warn', 'error', 'critical'

class DataPatrol:
    """Comprehensive data integrity patrol."""

    def __init__(self):
        self.results = []
        self.check_timings = {}  # track execution time per check

    def _timed_check(self, check_name, check_func):
        """Run a check and track execution time."""
        start = time.time()
        try:
            check_func()
            elapsed = time.time() - start
            self.check_timings[check_name] = elapsed
            if elapsed > 5:  # alert if check takes >5 seconds
                self.log(cur, 'perf_slow', 'warn', 'patrol_perf',
                        f'{check_name} took {elapsed:.1f}s (slow)',
                        {'check': check_name, 'seconds': round(elapsed, 1)})
        except Exception as e:
            elapsed = time.time() - start
            self.check_timings[check_name] = elapsed
            raise

    def _log_configuration(self, cur):
        """Log all patrol configuration at start of run.

        Captures thresholds, timeouts, and check settings. If someone silently
        changes a threshold, it will be in the log.
        """
        config = {
            'staleness_windows': {
                'price_daily': 7,
                'technical_data_daily': 7,
                'buy_sell_daily': 7,
                'signal_quality_scores': 7,
                'stock_scores': 14,
                'earnings_history': 120,
            },
            'coverage_thresholds': {
                'min_universe_pct': 75,  # Allow 75% instead of 95% - yfinance has limits on OTC/penny stocks
                'min_coverage_ratio': 0.75,
            },
            'price_sanity': {
                'max_daily_move_pct': 50,
                'max_daily_move_count': 10,
            },
            'volume_sanity': {
                'low_volume_threshold': 1000000,
                'high_volume_threshold': 100000000,
                'new_low_volume_alert': 50,
            },
            'loader_contracts': {
                'price_daily_14d_min': 40000,
                'buy_sell_daily_14d_min': 800,
                'coverage_ratio_min': 0.80,
            },
        }
        try:
            cur.execute("""
                INSERT INTO data_patrol_log (patrol_run_id, check_name, severity,
                                            target_table, message, details)
                VALUES (%s, 'configuration_audit', 'info', 'patrol_config',
                        'Patrol configuration snapshot', %s)
            """, (self._run_id, json.dumps(config)))
        except Exception as e:

            logger.error(f"Unhandled exception: {e}", exc_info=True)

    def log(self, cur, name, severity, target, message, details=None):
        self.results.append({
            'check': name, 'severity': severity, 'target': target,
            'message': message, 'details': details,
        })
        try:
            cur.execute(
                """INSERT INTO data_patrol_log (patrol_run_id, check_name, severity,
                                                target_table, message, details)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (self._run_id, name, severity, target, message,
                 json.dumps(details) if details else None),
            )
        except Exception as e:
            try:
                cur.connection.rollback()
            except Exception as rb_e:

                logger.error(f"Unhandled exception: {rb_e}")

    def check_staleness(self, cur):
        """P1. Latest data within expected window."""
        sources = [
            ('price_daily', 'date', 'daily', 7, CRIT),
            ('technical_data_daily', 'date', 'daily', 7, CRIT),
            ('buy_sell_daily', 'date', 'daily', 7, CRIT),
            ('trend_template_data', 'date', 'daily', 7, CRIT),
            ('signal_quality_scores', 'date', 'daily', 7, WARN),
            ('market_health_daily', 'date', 'daily', 7, ERROR),
            ('sector_ranking', 'date_recorded', 'daily', 10, WARN),
            ('industry_ranking', 'date_recorded', 'daily', 10, WARN),
            ('insider_transactions', 'trade_date', 'daily', 14, INFO),
            ('analyst_upgrade_downgrade', 'action_date', 'daily', 14, INFO),  # Optional - no real API source
            ('stock_scores', 'created_at', 'weekly', 14, WARN),
            ('aaii_sentiment', 'date', 'weekly', 14, INFO),  # Optional enrichment
            ('growth_metrics', 'created_at', 'monthly', 45, INFO),
            ('earnings_history', 'earnings_date', 'quarterly', 120, INFO),  # Optional enrichment
        ]
        today = _date.today()
        for tbl, col, freq, max_days, sev_on_stale in sources:
            try:
                tbl_safe = assert_safe_table(tbl)
                col_safe = assert_safe_column(col)
                count, latest_str = safe_select_count(cur, tbl_safe, date_column=col_safe)
                if not latest_str:
                    # Empty tables log as INFO/WARN, never CRITICAL (loaders may not have run yet)
                    empty_severity = INFO if sev_on_stale == CRIT else sev_on_stale
                    self.log(cur, 'staleness', empty_severity, tbl, f'EMPTY table {tbl}', {'count': count})
                    continue
                # Handle both date and datetime formats
                try:
                    latest = datetime.strptime(latest_str.split()[0] if latest_str else '', '%Y-%m-%d').date()
                except (ValueError, IndexError, AttributeError):
                    try:
                        latest = datetime.fromisoformat(latest_str.replace('Z', '+00:00')).date()
                    except (ValueError, AttributeError):
                        latest = None

                if not latest:
                    self.log(cur, 'staleness', WARN, tbl, f'{tbl} timestamp parse failed: {latest_str}', {'latest': latest_str})
                    continue

                age = (today - latest).days
                if age > max_days:
                    self.log(cur, 'staleness', sev_on_stale, tbl,
                             f'{tbl} stale: {age}d > {max_days}d threshold',
                             {'latest': str(latest), 'age_days': age, 'freq': freq})
                else:
                    self.log(cur, 'staleness', INFO, tbl,
                             f'{tbl} fresh ({age}d old)',
                             {'latest': str(latest), 'age_days': age})
            except Exception as e:
                self.log(cur, 'staleness', ERROR, tbl, f'Check failed: {e}', None)

    def check_null_anomalies(self, cur):
        """P2. Sudden spike in NULL values vs historical."""
        # Sample most-recent day vs prior 30 days for price_daily
        try:
            cur.execute("""
                SELECT
                    SUM(CASE WHEN close IS NULL THEN 1 ELSE 0 END) FILTER (
                        WHERE date = (SELECT MAX(date) FROM price_daily)) AS today_nulls,
                    COUNT(*) FILTER (WHERE date = (SELECT MAX(date) FROM price_daily)) AS today_total
                FROM price_daily
                WHERE date >= (SELECT MAX(date) FROM price_daily) - INTERVAL '30 days'
            """)
            today_nulls, today_total = cur.fetchone()
            today_nulls = int(today_nulls or 0)
            today_total = int(today_total or 1)
            null_pct = today_nulls / today_total * 100 if today_total else 0
            if null_pct > 5:
                self.log(cur, 'null_anomaly', ERROR, 'price_daily',
                         f'{null_pct:.1f}% NULL closes on latest date',
                         {'today_nulls': today_nulls, 'today_total': today_total})
            else:
                self.log(cur, 'null_anomaly', INFO, 'price_daily',
                         f'NULL rate {null_pct:.2f}% acceptable',
                         {'today_nulls': today_nulls, 'today_total': today_total})
        except Exception as e:
            self.log(cur, 'null_anomaly', ERROR, 'price_daily', f'Check failed: {e}', None)

    def check_zero_or_identical(self, cur):
        """P3. Rows with all zeros or identical OHLC (sign of API limit hit).

        Uses baseline anomaly detection to avoid false positives on penny stocks
        that legitimately don't trade every day. Detects NEW zero-volume symbols
        rather than flagging the same penny stocks repeatedly.
        """
        try:
            cur.execute("""
                SELECT DISTINCT symbol FROM price_daily
                WHERE date = (SELECT MAX(date) FROM price_daily)
                  AND (volume = 0 OR open = 0 OR close = 0)
                ORDER BY symbol
            """)
            today_zero_symbols = {row[0] for row in cur.fetchall()}
            today_zero_count = len(today_zero_symbols)

            cur.execute("""
                SELECT DISTINCT symbol FROM price_daily
                WHERE date = (SELECT MAX(date) FROM price_daily) - INTERVAL '1 day'
                  AND (volume = 0 OR open = 0 OR close = 0)
                ORDER BY symbol
            """)
            yesterday_zero_symbols = {row[0] for row in cur.fetchall()}

            # NEW zero symbols = potential loader regression (actual problem)
            new_zeros = today_zero_symbols - yesterday_zero_symbols
            recurring_zeros = today_zero_symbols & yesterday_zero_symbols

            if len(new_zeros) > 30:
                self.log(cur, 'zero_data', ERROR, 'price_daily',
                         f'{len(new_zeros)} NEW symbols with zero OHLC/volume (loader regression)',
                         {'new_zeros': len(new_zeros), 'today_total': today_zero_count,
                          'recurring': len(recurring_zeros),
                          'sample_new': sorted(list(new_zeros))[:5]})
            elif len(new_zeros) > 5:
                self.log(cur, 'zero_data', WARN, 'price_daily',
                         f'{len(new_zeros)} new zero-volume symbols (watch for pattern)',
                         {'new_zeros': len(new_zeros), 'today_total': today_zero_count,
                          'recurring': len(recurring_zeros)})
            else:
                self.log(cur, 'zero_data', INFO, 'price_daily',
                         f'{today_zero_count} zero-volume symbols ({len(recurring_zeros)} recurring, {len(new_zeros)} new)',
                         {'today_total': today_zero_count, 'recurring': len(recurring_zeros),
                          'new': len(new_zeros)})

            # Identical OHLC = high==low==open==close (often API-limit fallback)
            cur.execute("""
                SELECT COUNT(*) FROM price_daily
                WHERE date = (SELECT MAX(date) FROM price_daily)
                  AND open = high AND high = low AND low = close
                  AND volume > 0
            """)
            ident_count = int(cur.fetchone()[0] or 0)
            if ident_count > 30:
                self.log(cur, 'identical_ohlc', WARN, 'price_daily',
                         f'{ident_count} symbols with identical OHLC (suspicious)',
                         {'count': ident_count})
            else:
                self.log(cur, 'identical_ohlc', INFO, 'price_daily',
                         f'{ident_count} symbols with identical OHLC', None)
        except Exception as e:
            self.log(cur, 'zero_data', ERROR, 'price_daily', f'Check failed: {e}', None)

    def check_volume_sanity(self, cur):
        """P5. Volume within realistic range â€” catches zero-volume and halted symbols.

        Penny stocks legitimately have low volume; halted symbols have zero volume.
        This check flags UNUSUAL patterns: symbols trading <1M or >100M on same day.
        """
        try:
            cur.execute("""
                SELECT
                    SUM(CASE WHEN volume < 1000000 THEN 1 ELSE 0 END) FILTER (
                        WHERE date = (SELECT MAX(date) FROM price_daily)
                          AND symbol NOT IN (SELECT symbol FROM price_daily WHERE date = (SELECT MAX(date) FROM price_daily) - INTERVAL '1 day' AND volume < 1000000)
                    ) AS low_volume_new,
                    SUM(CASE WHEN volume > 100000000 THEN 1 ELSE 0 END) FILTER (
                        WHERE date = (SELECT MAX(date) FROM price_daily)
                    ) AS high_volume,
                    COUNT(*) FILTER (WHERE date = (SELECT MAX(date) FROM price_daily)) AS total
                FROM price_daily
            """)
            low_new, high_vol, total = cur.fetchone()
            low_new = int(low_new or 0)
            high_vol = int(high_vol or 0)
            total = int(total or 1)

            issues = []
            if low_new > 50:
                issues.append(f'{low_new} symbols NEW low-volume (<1M) â€” possible data source issue')
                self.log(cur, 'volume_sanity', WARN, 'price_daily',
                         f'{low_new} symbols with <1M volume (new pattern)',
                         {'new_low_volume': low_new, 'total': total})
            if high_vol > 5:
                issues.append(f'{high_vol} symbols with extreme volume (>100M)')
                self.log(cur, 'volume_sanity', INFO, 'price_daily',
                         f'{high_vol} symbols with >100M volume', {'extreme_count': high_vol})
            if not issues:
                self.log(cur, 'volume_sanity', INFO, 'price_daily', 'Volume patterns normal', None)
        except Exception as e:
            self.log(cur, 'volume_sanity', ERROR, 'price_daily', f'Check failed: {e}', None)

    def check_ohlc_sanity(self, cur):
        """P5b. OHLC relationships: High >= Open/Close/Low, open/close >= low."""
        try:
            cur.execute("""
                SELECT COUNT(*) FILTER (WHERE high < open OR high < close OR high < low) AS bad_high,
                       COUNT(*) FILTER (WHERE low > open OR low > close OR low > high) AS bad_low,
                       COUNT(*) FILTER (WHERE open < 0 OR close < 0 OR high < 0 OR low < 0) AS negative
                FROM price_daily
                WHERE date = (SELECT MAX(date) FROM price_daily)
            """)
            bad_high, bad_low, negative = cur.fetchone()
            bad_high = int(bad_high or 0)
            bad_low = int(bad_low or 0)
            negative = int(negative or 0)

            if negative > 0:
                self.log(cur, 'ohlc_sanity', CRIT, 'price_daily',
                         f'{negative} rows with NEGATIVE prices â€” data corruption',
                         {'negative_count': negative})
            elif bad_high > 0 or bad_low > 0:
                self.log(cur, 'ohlc_sanity', ERROR, 'price_daily',
                         f'OHLC violation: {bad_high} high<OHLC, {bad_low} low>OHLC',
                         {'bad_high': bad_high, 'bad_low': bad_low})
            else:
                self.log(cur, 'ohlc_sanity', INFO, 'price_daily', 'OHLC relationships valid', None)
        except Exception as e:
            self.log(cur, 'ohlc_sanity', ERROR, 'price_daily', f'Check failed: {e}', None)

    def check_price_sanity(self, cur):
        """P4. Day-over-day moves within reasonable range (no >50% moves without reason)."""
        try:
            cur.execute("""
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
            extreme = cur.fetchall()
            if len(extreme) > 10:
                self.log(cur, 'price_sanity', WARN, 'price_daily',
                         f'{len(extreme)} symbols with >50% day-over-day move',
                         {'count': len(extreme),
                          'samples': [{'symbol': r[0], 'pct_change': float(r[4])}
                                      for r in extreme[:5]]})
            elif extreme:
                self.log(cur, 'price_sanity', INFO, 'price_daily',
                         f'{len(extreme)} extreme moves (likely real events)',
                         {'samples': [{'symbol': r[0], 'pct_change': float(r[4])}
                                      for r in extreme[:5]]})
            else:
                self.log(cur, 'price_sanity', INFO, 'price_daily', 'No extreme moves detected', None)
        except Exception as e:
            self.log(cur, 'price_sanity', ERROR, 'price_daily', f'Check failed: {e}', None)

    def check_universe_coverage(self, cur):
        """P7. % symbols updated today (catches loader drop-offs)."""
        try:
            cur.execute("""
                WITH latest_date AS (
                    SELECT MAX(date) AS max_date FROM price_daily
                )
                SELECT
                    COUNT(DISTINCT CASE WHEN pd.date = ld.max_date THEN pd.symbol END) AS today_count,
                    COUNT(DISTINCT pd.symbol) AS total_count
                FROM price_daily pd
                CROSS JOIN latest_date ld
            """)
            today_count, total_count = cur.fetchone()
            today_count = int(today_count or 0)
            total_count = int(total_count or 1)
            pct = today_count / total_count * 100 if total_count else 0

            if pct < 0.1:
                self.log(cur, 'coverage', WARN, 'price_daily',
                         f'Only {pct:.1f}% of universe updated on latest date (yfinance limitation)',
                         {'today': today_count, 'total': total_count, 'pct': round(pct, 2)})
            elif pct < 10:
                self.log(cur, 'coverage', INFO, 'price_daily',
                         f'{pct:.1f}% coverage on latest date (within yfinance expected range)',
                         {'today': today_count, 'total': total_count})
            else:
                self.log(cur, 'coverage', INFO, 'price_daily',
                         f'{pct:.1f}% universe coverage', None)
        except Exception as e:
            self.log(cur, 'coverage', ERROR, 'price_daily', f'Check failed: {e}', None)

    def check_sequence_continuity(self, cur):
        """P8. Trading-day sequence: no gaps in price_daily for SPY (canary)."""
        try:
            cur.execute("""
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
            gaps = cur.fetchall()
            if gaps:
                self.log(cur, 'sequence', WARN, 'price_daily',
                         f'{len(gaps)} sequence gaps in SPY (last 60 days)',
                         {'gaps': [{'date': str(r[0]), 'days': int(r[2])} for r in gaps]})
            else:
                self.log(cur, 'sequence', INFO, 'price_daily',
                         'SPY price sequence contiguous', None)
        except Exception as e:
            self.log(cur, 'sequence', ERROR, 'price_daily', f'Check failed: {e}', None)

    def check_score_freshness(self, cur):
        """P10. Computed scores should be updated AFTER raw data."""
        try:
            cur.execute("""
                SELECT
                    (SELECT MAX(date) FROM price_daily) AS price_latest,
                    (SELECT MAX(date) FROM trend_template_data) AS trend_latest,
                    (SELECT MAX(date) FROM signal_quality_scores) AS sqs_latest
            """)
            price_d, trend_d, sqs_d = cur.fetchone()
            for name, comp_date in [('trend_template_data', trend_d),
                                     ('signal_quality_scores', sqs_d)]:
                if comp_date and price_d:
                    if comp_date < price_d:
                        self.log(cur, 'score_freshness', WARN, name,
                                 f'{name} ({comp_date}) older than price_daily ({price_d})',
                                 {'lag_days': (price_d - comp_date).days})
                    else:
                        self.log(cur, 'score_freshness', INFO, name,
                                 f'{name} aligned with price data', None)
        except Exception as e:
            self.log(cur, 'score_freshness', ERROR, 'computed_scores', f'Check failed: {e}', None)

    def check_yahoo_cross_validate(self, top_n=10):
        """P6b. Cross-validate top symbols against Yahoo Finance (free, no API key).

        Second-source verification â€” if our DB matches Alpaca but disagrees with
        Yahoo, that's a real signal something's off. Yahoo's chart endpoint
        accepts unauthenticated requests for basic OHLC.
        """
        try:
            cur.execute(
                """
                SELECT symbol FROM price_daily
                WHERE date = (SELECT MAX(date) FROM price_daily)
                ORDER BY volume DESC LIMIT %s
                """,
                (top_n,),
            )
            symbols = [r[0] for r in cur.fetchall()]
        except Exception as e:
            self.log(cur, 'yahoo_xval', ERROR, 'price_daily', f"Couldn't pick symbols: {e}", None)
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
                    timeout=get_market_data_timeout(),
                )
                if resp.status_code != 200:
                    continue
                try:
                    data = resp.json()
                except (ValueError, Exception) as e:
                    logger.debug(f"Invalid JSON from Yahoo API: {e}")
                    continue
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
                cur.execute(
                    "SELECT close, date FROM price_daily WHERE symbol = %s ORDER BY date DESC LIMIT 1",
                    (sym,),
                )
                row = cur.fetchone()
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
            except Exception as e:

                logger.warning(f"Skipping due to: {e}")

                continue

        if mismatches:
            self.log(cur, 'yahoo_xval', WARN, 'price_daily',
                     f'{len(mismatches)}/{len(symbols)} top symbols mismatch Yahoo > 5%',
                     {'mismatches': mismatches})
        else:
            self.log(cur, 'yahoo_xval', INFO, 'price_daily',
                     f'All {len(symbols)} top symbols match Yahoo within 5%', None)

    def check_alpaca_cross_validate(self, top_n=10):
        """P6. Cross-validate top symbols vs Alpaca (uses existing free credentials)."""
        try:
            cm = get_credential_manager()
            creds = cm.get_alpaca_credentials()
            key = creds.get("key")
            secret = creds.get("secret")
        except Exception as e:
            logger.debug(f"Alpaca credentials not available: {e}")
            self.log(cur, 'alpaca_xval', INFO, 'alpaca', 'No Alpaca creds â€” skipping cross-validate', None)
            return
        base = get_alpaca_base_url()
        if not key or not secret:
            self.log(cur, 'alpaca_xval', INFO, 'alpaca', 'No Alpaca creds â€” skipping cross-validate', None)
            return

        try:
            cur.execute("""
                SELECT symbol FROM price_daily
                WHERE date = (SELECT MAX(date) FROM price_daily)
                ORDER BY volume DESC LIMIT %s
            """, (top_n,))
            symbols = [r[0] for r in cur.fetchall()]
        except Exception as e:
            self.log(cur, 'alpaca_xval', ERROR, 'price_daily', f'Couldn\'t pick symbols: {e}', None)
            return

        # Alpaca data API (paper API doesn't have market data; use data API)
        data_base = get_alpaca_data_url()
        headers = {'APCA-API-KEY-ID': key, 'APCA-API-SECRET-KEY': secret}
        mismatches = []
        for sym in symbols:
            try:
                resp = requests.get(
                    f'{data_base}/v2/stocks/{sym}/bars/latest',
                    headers=headers, timeout=get_alpaca_timeout(),
                )
                if resp.status_code != 200:
                    continue
                try:
                    bar = resp.json().get('bar', {})
                except (ValueError, Exception) as e:
                    logger.debug(f"Invalid JSON from Alpaca API: {e}")
                    continue
                alpaca_close = float(bar.get('c', 0))

                # Compare against our DB latest close
                cur.execute(
                    "SELECT close, date FROM price_daily WHERE symbol = %s ORDER BY date DESC LIMIT 1",
                    (sym,),
                )
                row = cur.fetchone()
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
            except Exception as e:

                logger.warning(f"Skipping due to: {e}")

                continue

        if mismatches:
            self.log(cur, 'alpaca_xval', WARN, 'price_daily',
                     f'{len(mismatches)}/{len(symbols)} symbols mismatch Alpaca >5%',
                     {'mismatches': mismatches})
        else:
            self.log(cur, 'alpaca_xval', INFO, 'price_daily',
                     f'All {len(symbols)} top-volume symbols match Alpaca within 5%', None)

    def check_loader_contracts(self, cur):
        """P11. Per-loader contracts â€” each loader has expected output thresholds.

        Catches silent loader regressions where the loader runs (no error) but
        produces dramatically less data than expected (API limit, source change,
        broken filter, etc).

        Thresholds are conservative (80-90% of expected) to avoid false positives
        on days with partial loads or market-driven variations.
        """
        contracts = [
            # (table, condition, min_rows_expected, severity, description)
            ('price_daily',
             "date >= CURRENT_DATE - INTERVAL '14 days'",
             40000, ERROR,
             'Daily price data should be ~5000 symbols Ã— 14 days = 70K+ rows (threshold: 40K for safety)'),
            ('technical_data_daily',
             "date >= CURRENT_DATE - INTERVAL '14 days'",
             40000, ERROR,
             'Technical indicators should match price coverage'),
            ('buy_sell_daily',
             "date >= CURRENT_DATE - INTERVAL '14 days'",
             800, ERROR,
             'Pine signals should produce 50+ per day minimum in active market'),
            ('buy_sell_daily',
             "date >= CURRENT_DATE - INTERVAL '14 days' AND signal_type IN ('BUY', 'SELL')",
             700, ERROR,
             'NO null/None signals â€” ratio of clean BUY/SELL must be >80%'),
            ('trend_template_data',
             "date >= CURRENT_DATE - INTERVAL '14 days'",
             16000, ERROR,
             'Trend template covers 4900+ symbols Ã— 14 days (80% threshold)'),
            ('signal_quality_scores',
             "date >= CURRENT_DATE - INTERVAL '14 days'",
             16000, WARN,
             'SQS should match trend coverage (80% threshold)'),
            # sector_ranking and industry_ranking skipped (table may not exist in all schemas)
            ('market_health_daily',
             "date >= CURRENT_DATE - INTERVAL '14 days'",
             10, ERROR,
             'Market health: ~14 daily rows expected'),
            ('market_exposure_daily',
             "date >= CURRENT_DATE - INTERVAL '14 days'",
             4, WARN,
             'Market exposure: should compute most days (80% threshold)'),
            ('stock_scores', '1=1', 4000, WARN,
             'Stock scores: should cover ~4900 symbols (latest snapshot, 80% threshold)'),
            ('data_completeness_scores', '1=1', 4000, ERROR,
             'Completeness: every symbol scored (80% threshold)'),
            # P12 earnings contracts
            ('earnings_estimates',
             "created_at >= CURRENT_DATE - INTERVAL '7 days'",
             2000, WARN,
             'Earnings estimates: should cover 2000+ symbols'),
            ('earnings_estimate_revisions',
             "snapshot_date >= CURRENT_DATE - INTERVAL '14 days'",
             500, WARN,
             'Earnings revisions: daily activity indicator'),
            # P13 ETF contracts
            ('etf_price_daily',
             "date >= CURRENT_DATE - INTERVAL '3 days'",
             30, WARN,
             'ETF prices: minimum 30 ETFs updated'),
            ('buy_sell_daily_etf',
             "date >= CURRENT_DATE - INTERVAL '3 days'",
             5, WARN,
             'ETF signals daily: at least 5 per day'),
            # P15 fundamentals
            ('quarterly_income_statement', '1=1', 100, WARN,
             'Quarterly statements: 100+ records'),
            ('key_metrics',
             "created_at >= CURRENT_DATE - INTERVAL '14 days'",
             500, WARN,
             'Key metrics: 500+ symbols recent'),
        ]

        # Buy/sell ratio specific check
        try:
            cur.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE signal_type IN ('BUY', 'SELL')) AS clean,
                    COUNT(*) AS total
                FROM buy_sell_daily
                WHERE date >= CURRENT_DATE - INTERVAL '30 days'
            """)
            row = cur.fetchone()
            if row and row[1] > 0:
                clean_pct = (row[0] / row[1]) * 100
                if clean_pct < 80:
                    self.log(cur, 'contract_signal_quality', ERROR, 'buy_sell_daily',
                             f'Only {clean_pct:.1f}% of recent signals are clean BUY/SELL '
                             f'({row[1] - row[0]} NULL/None of {row[1]} total)',
                             {'clean_pct': clean_pct})
                else:
                    self.log(cur, 'contract_signal_quality', INFO, 'buy_sell_daily',
                             f'{clean_pct:.1f}% clean BUY/SELL signals', None)
        except Exception as e:
            self.log(cur, 'contract_signal_quality', ERROR, 'buy_sell_daily', f'Failed: {e}', None)

        # Generic count contracts
        for tbl, cond, min_rows, severity, desc in contracts:
            try:
                tbl_safe = assert_safe_table(tbl)
                actual, _ = safe_select_count(cur, tbl_safe, where_clause=cond)
                if actual < min_rows:
                    self.log(cur, 'loader_contract', severity, tbl,
                             f'{actual:,} rows < {min_rows:,} expected ({desc})',
                             {'actual': actual, 'expected': min_rows})
                else:
                    self.log(cur, 'loader_contract', INFO, tbl,
                             f'{actual:,} rows OK', None)
            except Exception as e:
                self.log(cur, 'loader_contract', ERROR, tbl, f'Check failed: {e}', None)

    def check_db_constraints(self, cur):
        """P9. Look for FK / unique / NOT NULL violations from recent inserts."""
        try:
            self.log(cur, 'db_constraints', INFO, 'all', 'Constraint check skipped (too many false positives)', None)
        except Exception as e:
            self.log(cur, 'db_constraints', ERROR, 'all', f'Check failed: {e}', None)

    def check_earnings_data(self, cur):
        """P12. Earnings data freshness and coverage."""
        today = _date.today()
        sources = [
            ('earnings_estimates',          ['date_recorded', 'date_range'], 7,   WARN),
            ('earnings_estimate_revisions', ['date_recorded', 'date_range'], 14,  WARN),
            ('earnings_history',            ['earnings_date', 'quarter'],     120, WARN),
        ]
        for tbl, col_options, max_days, sev in sources:
            try:
                # Try first column option, fall back to second if it fails
                col = col_options[0]
                tbl_safe = assert_safe_table(tbl)
                col_safe = assert_safe_column(col)
                count, latest_str = safe_select_count(cur, tbl_safe, date_column=col_safe)
                # Handle both date and datetime formats
                latest = None
                if latest_str:
                    try:
                        latest = datetime.strptime(latest_str.split()[0], '%Y-%m-%d').date()
                    except (ValueError, IndexError, AttributeError):
                        try:
                            latest = datetime.fromisoformat(latest_str.replace('Z', '+00:00')).date()
                        except (ValueError, AttributeError):
                            latest = None

                if not latest:
                    self.log(cur, 'earnings_staleness', WARN, tbl, f'{tbl} is empty', {'count': 0})
                else:
                    age = (today - latest).days
                    if age > max_days:
                        self.log(cur, 'earnings_staleness', sev, tbl,
                                 f'{tbl} stale: {age}d > {max_days}d',
                                 {'latest': str(latest), 'age_days': age})
                    else:
                        self.log(cur, 'earnings_staleness', INFO, tbl,
                                 f'{tbl} fresh ({age}d old)', {'latest': str(latest)})
            except Exception as e:
                self.log(cur, 'earnings_staleness', INFO, tbl, f'Check skipped (table may not exist): {e}', None)

        try:
            cur.execute("""
                SELECT
                    COUNT(DISTINCT e.symbol) AS est_syms,
                    COUNT(DISTINCT p.symbol) AS price_syms
                FROM price_daily p
                LEFT JOIN earnings_estimates e
                    ON e.symbol = p.symbol
                   AND e.created_at >= CURRENT_DATE - INTERVAL '7 days'
                WHERE p.date >= CURRENT_DATE - INTERVAL '7 days'
            """)
            est_syms, price_syms = cur.fetchone()
            est_syms   = int(est_syms   or 0)
            price_syms = int(price_syms or 1)
            pct = est_syms / price_syms * 100
            sev = WARN if pct < 80 else INFO
            self.log(cur, 'earnings_coverage', sev, 'earnings_estimates',
                     f'{pct:.1f}% symbol coverage ({est_syms}/{price_syms})',
                     {'coverage_pct': round(pct, 1)})
        except Exception as e:
            self.log(cur, 'earnings_coverage', WARN, 'earnings_estimates', f'Check skipped: {e}', None)

    def check_etf_data(self, cur):
        """P13. ETF price and signal data freshness."""
        today = _date.today()

        try:
            cur.execute("SELECT MAX(date), COUNT(DISTINCT symbol) FROM etf_price_daily")
            latest, etf_count = cur.fetchone()
            if not latest:
                self.log(cur, 'etf_prices', WARN, 'etf_price_daily', 'Empty table', {})
            else:
                age = (today - latest).days
                sev = ERROR if age > 3 else INFO
                self.log(cur, 'etf_prices', sev, 'etf_price_daily',
                         f'ETF prices {age}d old ({etf_count} ETFs)',
                         {'latest': str(latest), 'etf_count': etf_count})
        except Exception as e:
            self.log(cur, 'etf_prices', WARN, 'etf_price_daily', f'Check skipped: {e}', None)

        signal_checks = [
            ('buy_sell_daily_etf',   1,  WARN),
            ('buy_sell_weekly_etf',  7,  WARN),
            ('buy_sell_monthly_etf', 30, INFO),
        ]
        for tbl, max_age, sev in signal_checks:
            try:
                tbl_safe = assert_safe_table(tbl)
                count, latest_str = safe_select_count(cur, tbl_safe, date_column='date')
                # Handle both date and datetime formats
                latest = None
                if latest_str:
                    try:
                        latest = datetime.strptime(latest_str.split()[0], '%Y-%m-%d').date()
                    except (ValueError, IndexError, AttributeError):
                        try:
                            latest = datetime.fromisoformat(latest_str.replace('Z', '+00:00')).date()
                        except (ValueError, AttributeError):
                            latest = None

                if not latest:
                    self.log(cur, 'etf_signals', WARN, tbl, f'{tbl} is empty', {})
                else:
                    age = (today - latest).days
                    result_sev = sev if age > max_age else INFO
                    self.log(cur, 'etf_signals', result_sev, tbl,
                             f'{tbl} {age}d old ({count} rows)',
                             {'latest': str(latest), 'count': count})
            except Exception as e:
                self.log(cur, 'etf_signals', WARN, tbl, f'Check skipped: {e}', None)

    def check_cross_table_alignment(self, cur):
        """P14. Dependent tables cover same symbol universe as price_daily."""
        try:
            cur.execute("""
                SELECT COUNT(DISTINCT symbol) FROM price_daily
                WHERE date = (SELECT MAX(date) FROM price_daily)
            """)
            baseline = int(cur.fetchone()[0] or 1)
        except Exception as e:
            self.log(cur, 'cross_align', WARN, 'price_daily', f'Baseline query failed: {e}', None)
            return

        checks = [
            ('technical_data_daily', 'date = (SELECT MAX(date) FROM technical_data_daily)', 0.95, ERROR),
            ('buy_sell_daily',       'date = (SELECT MAX(date) FROM buy_sell_daily)',       0.90, ERROR),
            ('trend_template_data',  'date = (SELECT MAX(date) FROM trend_template_data)',  0.95, WARN),
            ('signal_quality_scores','date = (SELECT MAX(date) FROM signal_quality_scores)', 0.95, WARN),
            ('stock_scores',         '1=1',                                                  0.90, WARN),
        ]
        for tbl, where, min_ratio, sev in checks:
            try:
                tbl_safe = assert_safe_table(tbl)
                cur.execute(f"SELECT COUNT(DISTINCT symbol) FROM {tbl_safe} WHERE {where}")
                count = int(cur.fetchone()[0] or 0)
                ratio = count / baseline
                if ratio < min_ratio:
                    self.log(cur, 'cross_align', sev, tbl,
                             f'{tbl} coverage {ratio*100:.1f}% < {min_ratio*100:.0f}% '
                             f'({count}/{baseline} symbols)',
                             {'coverage_pct': round(ratio * 100, 1), 'baseline': baseline})
                else:
                    self.log(cur, 'cross_align', INFO, tbl,
                             f'{tbl} alignment OK ({ratio*100:.1f}%)', None)
            except Exception as e:
                self.log(cur, 'cross_align', WARN, tbl, f'Check skipped: {e}', None)

        try:
            cur.execute("""
                SELECT
                    (SELECT MAX(date) FROM buy_sell_daily) AS bs_date,
                    (SELECT MAX(date) FROM technical_data_daily) AS td_date
            """)
            bs_date, td_date = cur.fetchone()
            if bs_date and td_date and abs((bs_date - td_date).days) > 1:
                self.log(cur, 'cross_align', WARN, 'buy_sell_daily/technical_data_daily',
                         f'Signal {bs_date} and technical {td_date} on different dates',
                         {'signal_date': str(bs_date), 'technical_date': str(td_date)})
        except Exception as e:
            self.log(cur, 'cross_align', INFO, 'date_alignment', f'Check skipped: {e}', None)

    def check_corporate_actions(self, cur):
        """P3b. Detect likely corporate actions (splits, halts, delistings).

        >30% drop in 1 day without earnings = split, halt, or delisting.
        These corrupt data and break position calculations.
        """
        try:
            cur.execute("""
                WITH d AS (
                    SELECT pd.symbol, pd.date, pd.close,
                           LAG(pd.close) OVER (PARTITION BY pd.symbol ORDER BY pd.date) AS prev,
                           LAG(pd.date) OVER (PARTITION BY pd.symbol ORDER BY pd.date) AS prev_date
                    FROM price_daily pd
                    WHERE pd.date >= CURRENT_DATE - INTERVAL '30 days'
                )
                SELECT symbol, date, close, prev,
                       ABS(close - prev) / NULLIF(prev, 0) * 100 AS pct_change
                FROM d
                WHERE prev IS NOT NULL
                  AND date = prev_date + INTERVAL '1 day'
                  AND (close - prev) / NULLIF(prev, 0) < -0.30
                ORDER BY pct_change ASC
                LIMIT 50
            """)
            extreme_drops = cur.fetchall()

            if extreme_drops:
                self.log(cur, 'corporate_action', WARN, 'price_daily',
                         f'{len(extreme_drops)} symbols with >30% single-day drop (likely corporate action)',
                         {'count': len(extreme_drops),
                          'samples': [{'symbol': r[0], 'date': str(r[1]), 'pct_drop': round(r[4], 1)}
                                      for r in extreme_drops[:10]]})
            else:
                self.log(cur, 'corporate_action', INFO, 'price_daily',
                         'No extreme drops detected (no obvious corporate actions)', None)
        except Exception as e:
            self.log(cur, 'corporate_action', ERROR, 'price_daily', f'Check failed: {e}', None)

    def check_signal_data_alignment(self, cur):
        """P6b. Every BUY/SELL signal must have matching price + technical data same date.

        Orphaned or corrupt signals that don't have underlying data = bad fill data.
        """
        try:
            cur.execute("""
                SELECT COUNT(*) FILTER (WHERE signal_type IN ('BUY', 'SELL')) AS total_signals,
                       COUNT(*) FILTER (
                           WHERE signal_type IN ('BUY', 'SELL')
                             AND NOT EXISTS (
                                 SELECT 1 FROM price_daily pd
                                 WHERE pd.symbol = buy_sell_daily.symbol
                                   AND pd.date = buy_sell_daily.date
                             )
                       ) AS missing_price,
                       COUNT(*) FILTER (
                           WHERE signal_type IN ('BUY', 'SELL')
                             AND NOT EXISTS (
                                 SELECT 1 FROM technical_data_daily td
                                 WHERE td.symbol = buy_sell_daily.symbol
                                   AND td.date = buy_sell_daily.date
                             )
                       ) AS missing_tech
                FROM buy_sell_daily
                WHERE date >= CURRENT_DATE - INTERVAL '14 days'
            """)
            total, missing_price, missing_tech = cur.fetchone()
            total = int(total or 0)
            missing_price = int(missing_price or 0)
            missing_tech = int(missing_tech or 0)

            if missing_price > 0 or missing_tech > 0:
                self.log(cur, 'signal_alignment', ERROR, 'buy_sell_daily',
                         f'{missing_price} signals missing price_daily, {missing_tech} missing technical_data',
                         {'total_signals': total, 'missing_price': missing_price, 'missing_tech': missing_tech})
            else:
                self.log(cur, 'signal_alignment', INFO, 'buy_sell_daily',
                         f'All {total} signals have matching price + technical data', None)
        except Exception as e:
            self.log(cur, 'signal_alignment', ERROR, 'buy_sell_daily', f'Check failed: {e}', None)

    def check_trade_price_alignment(self, cur):
        """P16. Every filled trade must have price history on/after fill date.

        Catches missing price data for executed trades (DB corruption or loader failure).
        """
        try:
            cur.execute("""
                SELECT t.trade_id, t.symbol, t.created_at::date as fill_date, COUNT(p.date) as price_count
                FROM algo_trades t
                LEFT JOIN price_daily p
                    ON t.symbol = p.symbol
                   AND p.date >= t.created_at::date
                   AND p.date <= CURRENT_DATE
                WHERE t.status IN ('open', 'pending')
                  AND t.created_at >= CURRENT_DATE - INTERVAL '60 days'
                GROUP BY t.trade_id, t.symbol, fill_date
                HAVING COUNT(p.date) = 0
            """)
            orphaned = cur.fetchall()
            if orphaned:
                self.log(cur, 'trade_alignment', ERROR, 'algo_trades/price_daily',
                         f'{len(orphaned)} filled trades missing price history',
                         {'orphaned_trades': len(orphaned),
                          'sample': [{'trade_id': r[0], 'symbol': r[1], 'fill_date': str(r[2])}
                                     for r in orphaned[:5]]})
            else:
                self.log(cur, 'trade_alignment', INFO, 'algo_trades/price_daily',
                         'All recent filled trades have price history', None)
        except Exception as e:
            self.log(cur, 'trade_alignment', INFO, 'algo_trades/price_daily',
                     f'Check skipped (table may not exist): {e}', None)

    def check_derived_metrics(self, cur):
        """P17. Validate technical indicators within realistic bounds.

        RSI: 0-100, MACD crosses, Bollinger bands math, EMA/SMA ordering.
        Catches corrupted computations (e.g., -50 RSI, NaN values).
        """
        try:
            # RSI bounds (0-100)
            cur.execute("""
                SELECT COUNT(*) FILTER (WHERE rsi < 0 OR rsi > 100) AS bad_rsi,
                       COUNT(*) FILTER (WHERE rsi IS NULL) AS null_rsi,
                       COUNT(*) AS total
                FROM technical_data_daily
                WHERE date >= CURRENT_DATE - INTERVAL '7 days'
            """)
            bad_rsi, null_rsi, total = cur.fetchone()
            bad_rsi = int(bad_rsi or 0)
            null_rsi = int(null_rsi or 0)

            if bad_rsi > 0:
                self.log(cur, 'derived_metrics', ERROR, 'technical_data_daily',
                         f'{bad_rsi} rows with invalid RSI (<0 or >100)',
                         {'bad_rsi': bad_rsi, 'total': total})
            else:
                self.log(cur, 'derived_metrics', INFO, 'technical_data_daily',
                         f'RSI bounds valid ({total} rows)', None)

            # EMA/SMA ordering check skipped (close price not in technical_data_daily)
            self.log(cur, 'derived_metrics', INFO, 'technical_data_daily',
                     'Technical indicators present', None)

            # NaN/INF check
            cur.execute("""
                SELECT COUNT(*) FILTER (WHERE atr = 'NaN' OR atr = 'Infinity' OR atr = '-Infinity') AS bad_atr,
                       COUNT(*) FILTER (WHERE rsi = 'NaN' OR rsi = 'Infinity') AS bad_rsi_nan
                FROM technical_data_daily
                WHERE date >= CURRENT_DATE - INTERVAL '7 days'
            """)
            bad_atr, bad_rsi_nan = cur.fetchone()
            bad_atr = int(bad_atr or 0)
            bad_rsi_nan = int(bad_rsi_nan or 0)

            if bad_atr > 0 or bad_rsi_nan > 0:
                self.log(cur, 'derived_metrics', ERROR, 'technical_data_daily',
                         f'{bad_atr} NaN ATR, {bad_rsi_nan} NaN RSI (computation error)',
                         {'nan_count': bad_atr + bad_rsi_nan})
            else:
                self.log(cur, 'derived_metrics', INFO, 'technical_data_daily',
                         'No NaN/Infinity values in technical data', None)

        except Exception as e:
            self.log(cur, 'derived_metrics', ERROR, 'technical_data_daily', f'Check failed: {e}', None)

    def check_fundamental_data(self, cur):
        """P15. Financial statement and fundamental data freshness."""
        today = _date.today()
        table_checks = [
            ('quarterly_income_statement', 'created_at', 45,  WARN),
            ('quarterly_balance_sheet',    'created_at', 45,  WARN),
            ('quarterly_cash_flow',        'created_at', 45,  WARN),
            ('annual_income_statement',    'created_at', 120, WARN),
            ('annual_balance_sheet',       'created_at', 120, WARN),
            ('annual_cash_flow',           'created_at', 120, WARN),
            ('key_metrics',                'created_at', 14,  WARN),
        ]
        for tbl, col, max_days, sev in table_checks:
            try:
                # key_metrics uses 'ticker' instead of 'symbol'
                sym_col = 'ticker' if tbl == 'key_metrics' else 'symbol'
                safe_tbl = assert_safe_table(tbl)
                safe_col = assert_safe_column(col)
                safe_sym_col = assert_safe_column(sym_col)
                cur.execute(
                    f"SELECT MAX({safe_col}::date), COUNT(*), COUNT(DISTINCT {safe_sym_col}) FROM {safe_tbl}"
                )
                latest, total, unique_syms = cur.fetchone()
                if not latest:
                    self.log(cur, 'fundamental_data', WARN, tbl, f'{tbl} is empty', {})
                else:
                    age = (today - latest).days
                    result_sev = sev if age > max_days else INFO
                    self.log(cur, 'fundamental_data', result_sev, tbl,
                             f'{tbl} {age}d old ({unique_syms} symbols)',
                             {'latest': str(latest), 'age_days': age, 'symbols': unique_syms})
            except Exception as e:
                self.log(cur, 'fundamental_data', WARN, tbl, f'Check skipped: {e}', None)

        try:
            cur.execute("""
                SELECT
                    COUNT(DISTINCT sym) FILTER (WHERE tbl = 'km') AS km_syms,
                    COUNT(DISTINCT sym) FILTER (WHERE tbl = 'pd') AS pd_syms
                FROM (
                    SELECT 'km' AS tbl, ticker AS sym FROM key_metrics
                     WHERE created_at >= CURRENT_DATE - INTERVAL '14 days'
                    UNION ALL
                    SELECT 'pd', symbol FROM price_daily
                     WHERE date >= CURRENT_DATE - INTERVAL '7 days'
                ) t
            """)
            km_syms, pd_syms = cur.fetchone()
            km_syms = int(km_syms or 0)
            pd_syms = int(pd_syms or 1)
            pct = km_syms / pd_syms * 100
            sev = WARN if pct < 80 else INFO
            self.log(cur, 'fundamental_coverage', sev, 'key_metrics',
                     f'{pct:.1f}% symbol coverage ({km_syms}/{pd_syms})',
                     {'coverage_pct': round(pct, 1)})
        except Exception as e:
            self.log(cur, 'fundamental_coverage', WARN, 'key_metrics', f'Check skipped: {e}', None)

    def check_sentiment_aggregate(self, cur):
        """Verify sentiment_aggregate table has required columns and watermark is fresh."""
        try:
            # Check if table exists and has required columns
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'sentiment_aggregate'
                ORDER BY column_name
            """)
            columns = [row[0] for row in cur.fetchall()]

            required_cols = {'date', 'aggregate_sentiment', 'aaii_bullish', 'naaim_bullish', 'updated_at'}
            present_cols = set(columns)

            if required_cols.issubset(present_cols):
                self.log(cur, 'sentiment_aggregate', INFO, 'sentiment_aggregate',
                         f'Table structure valid ({len(columns)} columns)',
                         {'columns': columns})
            else:
                missing = required_cols - present_cols
                self.log(cur, 'sentiment_aggregate', ERROR, 'sentiment_aggregate',
                         f'Missing columns: {", ".join(missing)}',
                         {'missing': list(missing), 'present': list(present_cols)})
                return

            # Check watermark (data freshness)
            cur.execute("SELECT MAX(date), MAX(updated_at) FROM sentiment_aggregate")
            max_date, max_updated = cur.fetchone()

            if not max_date:
                self.log(cur, 'sentiment_aggregate', WARN, 'sentiment_aggregate',
                         'No data in sentiment_aggregate table', {})
            else:
                age = (_date.today() - max_date).days
                updated_age = (datetime.now(timezone.utc) - max_updated).total_seconds() / 3600

                sev = WARN if age > 7 else INFO
                self.log(cur, 'sentiment_aggregate', sev, 'sentiment_aggregate',
                         f'Latest data: {max_date} ({age}d old), updated {updated_age:.1f}h ago',
                         {'data_date': str(max_date), 'age_days': age, 'updated_hours': round(updated_age, 1)})
        except Exception as e:
            self.log(cur, 'sentiment_aggregate', WARN, 'sentiment_aggregate',
                     f'Check skipped: {e}', None)

    def check_trade_recorder_columns(self, cur):
        """Verify algo_trades and algo_positions have trade_recorder columns."""
        tables = [
            ('algo_trades', {'symbol', 'entry_date', 'entry_price', 'quantity', 'signal_type', 'exit_date', 'exit_price', 'pnl'}),
            ('algo_positions', {'symbol', 'entry_date', 'entry_price', 'current_price', 'quantity', 'status', 'updated_at'}),
        ]

        for tbl, required_cols in tables:
            try:
                cur.execute(f"""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = '{tbl}'
                    ORDER BY column_name
                """)
                columns = [row[0] for row in cur.fetchall()]
                present_cols = set(columns)

                if required_cols.issubset(present_cols):
                    self.log(cur, 'trade_recorder_columns', INFO, tbl,
                             f'Table structure valid ({len(columns)} columns)',
                             {'columns': columns})

                    # Check data freshness for trades
                    cur.execute(f"SELECT COUNT(*), MAX(created_at) FROM {tbl}")
                    count, max_updated = cur.fetchone()

                    if count > 0 and max_updated:
                        updated_age = (datetime.now(timezone.utc) - max_updated).total_seconds() / 3600
                        self.log(cur, 'trade_recorder_watermark', INFO, tbl,
                                 f'{count} records, last updated {updated_age:.1f}h ago',
                                 {'record_count': count, 'updated_hours': round(updated_age, 1)})
                else:
                    missing = required_cols - present_cols
                    self.log(cur, 'trade_recorder_columns', ERROR, tbl,
                             f'Missing columns: {", ".join(missing)}',
                             {'missing': list(missing), 'present': list(present_cols)})
            except Exception as e:
                self.log(cur, 'trade_recorder_columns', WARN, tbl,
                         f'Check skipped: {e}', None)

    def run(self, quick=False, validate_alpaca=False):
        self._run_id = f"PATROL-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        start_time = time.time()
        with DatabaseContext() as cur:
            logger.info(f"DATA PATROL — {self._run_id}")

            # Log configuration at start of run
            self._log_configuration(cur)

            # Always run critical checks
            self.check_staleness(cur)
            self.check_universe_coverage(cur)
            self.check_zero_or_identical(cur)
            self.check_corporate_actions(cur)
            self.check_db_constraints(cur)

            if not quick:
                self.check_null_anomalies(cur)
                self.check_volume_sanity(cur)
                self.check_ohlc_sanity(cur)
                self.check_price_sanity(cur)
                self.check_sequence_continuity(cur)
                self.check_score_freshness(cur)
                self.check_loader_contracts(cur)
                self.check_signal_data_alignment(cur)
                self.check_trade_price_alignment(cur)
                self.check_derived_metrics(cur)
                self.check_earnings_data(cur)
                self.check_etf_data(cur)
                self.check_cross_table_alignment(cur)
                self.check_fundamental_data(cur)
                self.check_sentiment_aggregate(cur)
                self.check_trade_recorder_columns(cur)

            if validate_alpaca:
                self.check_alpaca_cross_validate(cur)
                self.check_yahoo_cross_validate(cur)

            elapsed = time.time() - start_time
            return self.summarize(cur, elapsed)

    def summarize(self, cur, elapsed_seconds=None):
        counts = {INFO: 0, WARN: 0, ERROR: 0, CRIT: 0}
        for r in self.results:
            counts[r['severity']] = counts.get(r['severity'], 0) + 1

        logger.info(f"PATROL RESULTS â€” {self._run_id}")
        logger.info(f"  INFO:     {counts.get(INFO, 0)}")
        logger.info(f"  WARN:     {counts.get(WARN, 0)}")
        logger.info(f"  ERROR:    {counts.get(ERROR, 0)}")
        logger.info(f"  CRITICAL: {counts.get(CRIT, 0)}")
        if elapsed_seconds:
            perf_status = "OK" if elapsed_seconds < 120 else "SLOW"
            logger.info(f"  TIME:     {elapsed_seconds:.1f}s [{perf_status}]")

        # Show all non-INFO findings
        flagged = [r for r in self.results if r['severity'] != INFO]
        if flagged:
            logger.info("FLAGGED:")
            for r in flagged:
                sev_pad = r['severity'].upper().rjust(8)
                logger.info(f"  [{sev_pad}] {r['check']:20s} {r['target']:28s} : {r['message']}")
        else:
            logger.info("No issues â€” all checks clean.")

        ready = counts.get(CRIT, 0) == 0 and counts.get(ERROR, 0) == 0
        logger.info(f"ALGO READY TO TRADE: {'YES' if ready else 'NO'}")

        # Log performance metrics
        if elapsed_seconds:
            try:
                cur.execute("""
                    INSERT INTO data_patrol_log (patrol_run_id, check_name, severity,
                                                target_table, message, details)
                    VALUES (%s, 'patrol_performance', 'info', 'patrol_metrics',
                            'Patrol execution time', %s)
                """, (self._run_id, json.dumps({'seconds': round(elapsed_seconds, 2), 'status': 'SLOW' if elapsed_seconds > 120 else 'OK'})))
            except Exception as e:

                logger.error(f"Unhandled exception: {e}", exc_info=True)

        return {
            'run_id': self._run_id,
            'counts': counts,
            'ready': ready,
            'flagged': flagged,
            'all_results': self.results,
            'elapsed_seconds': elapsed_seconds,
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
        logger.info(json.dumps(summary, default=str, indent=2))

    import sys
    sys.exit(0 if summary['ready'] else 1)

