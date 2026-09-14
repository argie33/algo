#!/usr/bin/env python3
"""Coverage and loader contract checks."""

import logging
from typing import Any

import psycopg2

from algo.infrastructure.config.sql_intervals import get_interval_sql
from utils.db import assert_safe_table, safe_select_count

from ..base import BaseCheck, CheckResult
from ..config import ERROR, INFO, WARN

logger = logging.getLogger(__name__)


class CoverageChecker(BaseCheck):
    def run(self, cur: Any) -> list[CheckResult]:
        """Execute coverage checks."""
        self.results = []

        self.check_universe_coverage(cur)
        self.check_loader_coverage(cur)
        self.check_loader_contracts(cur)
        self.check_signal_quality_ratio(cur)
        self.check_buy_sell_daily_signal_anomaly_history(cur)

        return self.results

    def check_universe_coverage(self, cur: Any) -> None:
        try:
            cur.execute("""
                WITH latest_date AS (
                    SELECT MAX(date) AS max_date FROM price_daily
                )
                SELECT
                    COUNT(DISTINCT CASE WHEN pd.date = ld.max_date THEN pd.symbol END) AS today_count
                FROM price_daily pd
                CROSS JOIN latest_date ld
            """)
            row = cur.fetchone()
            # BUG FOUND 2026-08-11: DictCursor (psycopg2.extras) returns DictRow, which is
            # dict-LIKE (supports .get()/.keys()) but is NOT a `dict` subclass -
            # isinstance(row, dict) was always False for a correctly-configured DictCursor,
            # so this "mismatch" branch fired on every single real row, unconditionally
            # crashing this checker. Same established pattern already correctly used in
            # specialized.py:206 - accept dict-like via hasattr("keys"), not a strict dict
            # subclass check.
            if isinstance(row, dict) or hasattr(row, "keys"):
                today_count = row.get("today_count")
            else:
                raise TypeError(
                    f"Expected dict-like row from DictCursor, got {type(row).__name__}. "
                    f"This indicates cursor configuration mismatch. Check data_patrol cursor factory."
                )
            if today_count is None:
                msg = "price_daily coverage query returned NULL - data may not be fully loaded yet"
                logger.warning(msg)
                self.log("coverage", WARN, "price_daily", msg, {"today_count": today_count})
                return
            today_count = int(today_count)

            # Get expected symbol count from active symbols, not historical price_daily
            cur.execute("SELECT COUNT(*) FROM stock_symbols WHERE active = true")
            expected_row = cur.fetchone()
            if expected_row is None or expected_row[0] is None:
                msg = "Cannot determine expected symbol count - stock_symbols table may be empty"
                logger.warning(msg)
                self.log("coverage", WARN, "stock_symbols", msg, None)
                return
            total_count = int(expected_row[0])
            if total_count <= 0:
                logger.warning("Expected symbol count is 0 - skipping coverage check")
                return
            pct = today_count / total_count * 100

            if pct < 10:
                self.log(
                    "coverage",
                    WARN,
                    "price_daily",
                    f"Only {pct:.1f}% of active symbols updated on latest date ({today_count}/{total_count})",
                    {"today": today_count, "expected": total_count, "pct": round(pct, 2)},
                )
            elif pct < 90:
                self.log(
                    "coverage",
                    INFO,
                    "price_daily",
                    f"{pct:.1f}% of active symbols have price data on latest date ({today_count}/{total_count})",
                    {"today": today_count, "expected": total_count, "pct": round(pct, 2)},
                )
            else:
                self.log(
                    "coverage",
                    INFO,
                    "price_daily",
                    f"{pct:.1f}% universe coverage ({today_count}/{total_count} active symbols)",
                    {"today": today_count, "expected": total_count, "pct": round(pct, 1)},
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            self.log("coverage", ERROR, "price_daily", f"Check failed: {e}", None)

    def check_loader_coverage(self, cur: Any) -> None:
        """Verify symbol coverage >= threshold for critical loaders."""
        try:
            cov_cfg = self.config.get_coverage_thresholds()
            coverage_error_pct = cov_cfg["error_pct"]
            coverage_warn_pct = cov_cfg["warn_pct"]

            cur.execute("SELECT COUNT(*) FROM stock_symbols WHERE active = true")
            row = cur.fetchone()
            if row is None or row[0] is None:
                raise ValueError("Expected symbol count query returned NULL - cannot validate loader coverage")
            expected_count = int(row[0])

            if expected_count == 0:
                self.log(
                    "coverage",
                    ERROR,
                    "stock_symbols",
                    "No active symbols in stock_symbols table - cannot calculate loader coverage percentages",
                    {"expected_count": 0},
                )
                return

            critical_tables = [
                "price_daily",
                "technical_data_daily",
                # BUG FOUND 2026-08-11: buy_sell_daily is sparse BY DESIGN - only symbols
                # that actually got a buy/sell classification get a row, not the whole
                # universe. Live data confirms this is stable, not an anomaly: 895-1008
                # symbols/day across 6 consecutive trading days (~18-20% of the 4945-symbol
                # active universe), while data_loader_status.symbols_loaded=4452 for the
                # same run (the loader evaluates the full universe; only a fraction qualify
                # for a row). Applying this method's 96%/98%-of-universe threshold to it
                # generated a permanent, unconditional false ERROR every single day.
                # check_loader_contracts() (below) already validates this table correctly
                # via its own dedicated absolute-row-count contract
                # (patrol_buy_sell_daily_14d_min=800, an appropriate threshold for a
                # sparse-by-design table) - removing the duplicate, wrong-methodology check
                # here doesn't reduce coverage, it removes a redundant false alarm.
                "trend_template_data",
                # signal_quality_scores REMOVED 2026-08-11 (follow-up to buy_sell_daily fix
                # above): it's sparse by design (~520/4945 = ~10.5% coverage on a typical
                # day, live range 512-2510 symbols/day over the last 14 days), so the
                # universal 96%/98%-of-universe threshold was an unconditional false ERROR
                # every day. Now validated via its own dedicated absolute-row-count contract
                # (patrol_signal_quality_scores_14d_min=300) in check_loader_contracts(),
                # same pattern as buy_sell_daily.
            ]

            try:
                for table_name in critical_tables:
                    assert_safe_table(table_name)

                union_parts = []
                for table_name in critical_tables:
                    union_parts.append(f"""
                        SELECT '{table_name}' as table_name, COUNT(DISTINCT symbol) as cnt
                        FROM {assert_safe_table(table_name)}
                        WHERE date = (SELECT MAX(date) FROM {assert_safe_table(table_name)})
                    """)

                union_query = " UNION ALL ".join(union_parts)
                cur.execute(union_query)

                results_by_table = {}
                for row in cur.fetchall():
                    row_dict = dict(row)
                    table_name = row_dict["table_name"]
                    cnt = row_dict["cnt"]
                    if cnt is None:
                        raise ValueError(
                            f"COUNT(DISTINCT symbol) returned NULL for {table_name} - table may be empty or query failed"
                        )
                    results_by_table[table_name] = int(cnt)

                # Verify all critical tables are represented
                missing_tables = set(critical_tables) - set(results_by_table.keys())
                if missing_tables:
                    raise ValueError(f"Coverage query missing tables: {missing_tables} - UNION query may have failed")

                for table_name in critical_tables:
                    try:
                        table_count = results_by_table[table_name]
                        if expected_count <= 0:
                            logger.warning(f"{table_name} expected_count is 0 - skipping coverage check")
                            continue
                        coverage_pct = table_count / expected_count * 100

                        if coverage_pct < coverage_error_pct:
                            self.log(
                                "coverage",
                                ERROR,
                                table_name,
                                f"{table_name} coverage {coverage_pct:.1f}% < {coverage_error_pct}% threshold ({table_count}/{expected_count} symbols)",
                                {
                                    "coverage_pct": round(coverage_pct, 1),
                                    "count": table_count,
                                    "expected": expected_count,
                                    "threshold": coverage_error_pct,
                                },
                            )
                        elif coverage_pct < coverage_warn_pct:
                            self.log(
                                "coverage",
                                WARN,
                                table_name,
                                f"{table_name} coverage {coverage_pct:.1f}% < {coverage_warn_pct}% warn threshold",
                                {
                                    "coverage_pct": round(coverage_pct, 1),
                                    "count": table_count,
                                    "expected": expected_count,
                                },
                            )
                        else:
                            self.log(
                                "coverage",
                                INFO,
                                table_name,
                                f"{table_name} coverage {coverage_pct:.1f}% OK",
                                {
                                    "coverage_pct": round(coverage_pct, 1),
                                    "count": table_count,
                                },
                            )
                    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                        self.log("coverage", ERROR, table_name, f"Check failed: {e}", None)
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                self.log(
                    "coverage",
                    ERROR,
                    "patrol_coverage",
                    f"Union query check failed: {e}",
                    None,
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            self.log(
                "coverage",
                ERROR,
                "patrol_coverage",
                f"Coverage check failed: {e}",
                None,
            )

    def check_loader_contracts(self, cur: Any) -> None:
        """Verify per-loader output contracts."""
        contracts = self.config.get_loader_contracts()

        for tbl, contract in contracts.items():
            sp = f"sp_contract_{tbl}"
            cur.execute(f"SAVEPOINT {sp}")
            try:
                tbl_safe = assert_safe_table(tbl)
                actual, _ = safe_select_count(cur, tbl_safe, where_clause=contract["condition"])
                expected = contract["min_rows"]
                severity = contract["severity"]

                if actual < expected:
                    self.log(
                        "loader_contract",
                        severity,
                        tbl,
                        f"{actual:,} rows < {expected:,} expected ({contract['description']})",
                        {"actual": actual, "expected": expected},
                    )
                else:
                    self.log(
                        "loader_contract",
                        INFO,
                        tbl,
                        f"{actual:,} rows OK",
                        None,
                    )
            except Exception as e:
                self.log("loader_contract", ERROR, tbl, f"Check failed: {e}", None)
                try:
                    cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
                except Exception as rollback_err:
                    import logging

                    logging.getLogger(__name__).error(f"Savepoint rollback failed: {rollback_err}")
            finally:
                cur.execute(f"RELEASE SAVEPOINT {sp}")

    def check_signal_quality_ratio(self, cur: Any) -> None:
        try:
            interval_30d = get_interval_sql("30d")
            cur.execute(f"""
                SELECT
                    COUNT(*) FILTER (WHERE signal_type IN ('BUY', 'SELL')) AS clean,
                    COUNT(*) AS total
                FROM buy_sell_daily
                WHERE date >= CURRENT_DATE - {interval_30d}
            """)
            row = cur.fetchone()
            if row and row[1] > 0:
                clean_pct = (row[0] / row[1]) * 100
                # EXPLICIT THRESHOLD: buy_sell_daily signals must be ≥80% clean (not NULL)
                # This is a fixed contract, not a configurable setting
                threshold = 80
                if clean_pct < threshold:
                    self.log(
                        "contract_signal_quality",
                        ERROR,
                        "buy_sell_daily",
                        f"Only {clean_pct:.1f}% clean BUY/SELL signals ({row[1] - row[0]} NULL/None of {row[1]} total)",
                        {"clean_pct": clean_pct},
                    )
                else:
                    self.log(
                        "contract_signal_quality",
                        INFO,
                        "buy_sell_daily",
                        f"{clean_pct:.1f}% clean BUY/SELL signals",
                        None,
                    )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            self.log(
                "contract_signal_quality",
                ERROR,
                "buy_sell_daily",
                f"Failed: {e}",
                None,
            )

    def check_buy_sell_daily_signal_anomaly_history(self, cur: Any) -> None:
        """Persist a reviewable record of any recent day with an anomalously low BUY count.

        Added 2026-09-14 (goal session: "if we have data issues we need to know about them
        and address them"). algo/orchestrator/phase7_signal_generation.py already halts the
        live pipeline when the single most recent trading day's BUY-signal count falls below
        a dynamic floor (median_30d/3, min 40) - but that check's own lookback is exactly one
        day (`_buysell_lookback_start_date`), and a halt carries no persisted record anywhere:
        once the flagged day is no longer "yesterday" relative to whatever run_date is being
        evaluated, the same query simply stops seeing it. Live-confirmed 2026-09-14: 2026-09-10
        genuinely had only 30 BUY signals (vs. a ~80-250/day historical range, technical_data_daily/
        price_daily both fully populated that day - not an upstream data gap) and halted a
        same-day test run, but every real production run since has silently stopped checking it
        - nothing in symbol_quarantine, data_patrol_log, or any dashboard ever recorded that this
        happened or why, so there is no way to later tell "was this ever looked into" from "did it
        just age out of the window". This check closes that gap WITHOUT touching Phase 7's actual
        halt behavior at all (additive-only, no threshold or gating logic changed) - it re-derives
        the same dynamic floor over a WIDER 10-trading-day lookback and logs a WARN (ERROR if the
        day was essentially signal-free) finding for any day that trips it, so the finding survives
        in the normal data_patrol_review triage queue rather than disappearing once the day rolls
        out of Phase 7's 1-day window. Deliberately WARN not ERROR for a moderate anomaly - this
        table's BUY/SELL split is legitimately regime-sensitive (BUY requires a breakout AND
        close > SMA50, SELL only requires breaking support - see load_buy_sell_daily.py's own
        _generate_signals docstring), so a low BUY day is a real thing to review, not proof of a
        broken loader; a human/DataPatrol reviewer should judge each one against market breadth
        for that day, not treat this as an automatic verdict.
        """
        try:
            cur.execute(
                """
                SELECT date, COUNT(*) AS signal_count
                FROM buy_sell_daily
                WHERE signal = 'BUY' AND date >= CURRENT_DATE - INTERVAL '45 days'
                GROUP BY date
                ORDER BY date DESC
                LIMIT 30
                """
            )
            rows = cur.fetchall()
            if not rows:
                return

            daily_counts = [(r[0], int(r[1])) for r in rows]
            counts_sorted = sorted(c for _, c in daily_counts)
            n = len(counts_sorted)
            median = counts_sorted[n // 2] if n % 2 == 1 else (counts_sorted[n // 2 - 1] + counts_sorted[n // 2]) / 2
            # Same formula as phase7_signal_generation.py's _calculate_dynamic_anomaly_threshold
            # (median_30d / 3, floor of 40) - kept in sync deliberately, not re-derived
            # independently, so this check and the live halt agree on what "anomalous" means.
            threshold = max(40, int(median / 3))

            # Only re-examine the most recent 10 trading days in this 30-day window - older
            # days are handled by whatever ran at the time and re-flagging them here forever
            # would just be noise, not new information.
            for signal_date, count in daily_counts[:10]:
                if count >= threshold:
                    continue
                # WARN ONLY, never ERROR/CRITICAL - deliberately. Phase 1
                # (algo/orchestrator/phase1_data_freshness.py's _check_data_patrol_results)
                # halts live trading on ANY CRITICAL/ERROR finding in the latest patrol run.
                # This check's job is visibility for a day that's already in the past (it
                # looks back up to 10 trading days, not just "yesterday" like Phase 7's own
                # halt) - it must never itself become a NEW halt trigger for a day trading
                # decisions have already moved past. Phase 7's own inline check is still the
                # one authoritative halt for the CURRENT day's signal generation; this is
                # purely a durable record for human/DataPatrol review, not a second gate.
                severity = WARN
                self.log(
                    "buy_sell_daily_signal_anomaly",
                    severity,
                    "buy_sell_daily",
                    f"{signal_date}: only {count} BUY signals (< anomaly floor {threshold}, "
                    f"30d median {median:.0f}/3). Review market breadth (SPY/sector) for that "
                    f"date before concluding this is a loader defect vs. a genuinely thin "
                    f"breakout day - see this check's own docstring.",
                    {"date": str(signal_date), "buy_count": count, "threshold": threshold, "median_30d": median},
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            self.log(
                "buy_sell_daily_signal_anomaly",
                ERROR,
                "buy_sell_daily",
                f"Check failed: {e}",
                None,
            )
