#!/usr/bin/env python3
"""Price sanity checks - extreme moves, corporate actions, sequence continuity."""

import logging
from typing import Any

import psycopg2

from algo.infrastructure.config.sql_intervals import get_interval_sql

from ..base import BaseCheck, CheckResult
from ..config import ERROR, INFO, WARN

logger = logging.getLogger(__name__)


class PriceSanityChecker(BaseCheck):
    def run(self, cur: Any) -> list[CheckResult]:
        """Execute all price sanity checks."""
        self.results = []

        self.check_price_moves(cur)
        self.check_corporate_actions(cur)
        self.check_sequence_continuity(cur)
        self.check_isolated_spike_corruption(cur)

        return self.results

    def check_price_moves(self, cur: Any) -> None:
        try:
            price_cfg = self.config.get_price_sanity_config()
            max_move_pct = price_cfg["max_daily_move_pct"]

            cur.execute(
                """
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
                  AND ABS(close - prev) / NULLIF(prev, 0) > %s
                  AND date = (SELECT MAX(date) FROM price_daily)
                ORDER BY pct_change DESC
                LIMIT 20
            """,
                (max_move_pct,),
            )
            extreme = cur.fetchall()

            if len(extreme) > 10:
                samples = []
                for r in extreme[:5]:
                    pct_change = r.get("pct_change") if isinstance(r, dict) else (r[4] if len(r) > 4 else None)
                    if pct_change is not None:
                        try:
                            symbol = r.get("symbol") if isinstance(r, dict) else r[0]
                            samples.append({"symbol": symbol, "pct_change": float(pct_change)})
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Invalid pct_change {pct_change} for {r}: {e}")
                            samples.append(
                                {"symbol": r.get("symbol") if isinstance(r, dict) else r[0], "pct_change": None}
                            )
                self.log(
                    "price_sanity",
                    WARN,
                    "price_daily",
                    f"{len(extreme)} symbols with >{max_move_pct * 100:.0f}% day-over-day move",
                    {
                        "count": len(extreme),
                        "samples": samples,
                    },
                )
            elif extreme:
                samples = []
                for r in extreme[:5]:
                    pct_change = r.get("pct_change") if isinstance(r, dict) else (r[4] if len(r) > 4 else None)
                    if pct_change is not None:
                        try:
                            symbol = r.get("symbol") if isinstance(r, dict) else r[0]
                            samples.append({"symbol": symbol, "pct_change": float(pct_change)})
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Invalid pct_change {pct_change} for {r}: {e}")
                            samples.append(
                                {"symbol": r.get("symbol") if isinstance(r, dict) else r[0], "pct_change": None}
                            )
                self.log(
                    "price_sanity",
                    INFO,
                    "price_daily",
                    f"{len(extreme)} extreme moves (likely real events)",
                    {"samples": samples},
                )
            else:
                self.log(
                    "price_sanity",
                    INFO,
                    "price_daily",
                    "No extreme moves detected",
                    None,
                )
        except (ValueError, ZeroDivisionError, TypeError) as e:
            self.log("price_sanity", ERROR, "price_daily", f"Check failed: {e}", None)

    def check_corporate_actions(self, cur: Any) -> None:
        """Detect likely corporate actions (splits, halts, delistings)."""
        try:
            corp_cfg = self.config.get_corporate_actions_config()
            lookback_days = corp_cfg["lookback_days"]
            drop_ratio = corp_cfg["drop_ratio"]

            # BUG FOUND 2026-08-11: `date = prev_date + 1 calendar day` required the LAG'd
            # previous row to be exactly one calendar day earlier. LAG(...) OVER (PARTITION BY
            # symbol ORDER BY date) already correctly returns each symbol's immediately
            # preceding row regardless of weekends/holidays/per-symbol data gaps - this extra
            # filter then silently discarded every comparison that crossed a weekend/holiday
            # (Friday->Monday, 3 calendar days apart) or a per-symbol gap day. Live-verified:
            # on this Monday's data, 7 symbols had a genuine >30% Friday-close-to-Monday-close
            # drop that this filter was excluding entirely - the check was blind to the most
            # recent trading day's movers on every Monday/post-holiday run, the opposite
            # failure mode of a false alarm (a real signal silently never surfacing).
            cur.execute(f"""
                WITH d AS (
                    SELECT pd.symbol, pd.date, pd.close,
                           LAG(pd.close) OVER (PARTITION BY pd.symbol ORDER BY pd.date) AS prev,
                           LAG(pd.date) OVER (PARTITION BY pd.symbol ORDER BY pd.date) AS prev_date
                    FROM price_daily pd
                    WHERE pd.date >= CURRENT_DATE - INTERVAL '{lookback_days} days'
                )
                SELECT symbol, date, close, prev,
                       (close - prev) / NULLIF(prev, 0) * 100 AS pct_change
                FROM d
                WHERE prev IS NOT NULL
                  AND (close - prev) / NULLIF(prev, 0) < {drop_ratio}
                ORDER BY pct_change ASC
                LIMIT 50
            """)
            extreme_drops = cur.fetchall()

            if extreme_drops:
                samples = []
                for r in extreme_drops[:10]:
                    try:
                        symbol = r.get("symbol") if isinstance(r, dict) else r[0]
                        date = r.get("date") if isinstance(r, dict) else r[1]
                        pct_change = r.get("pct_change") if isinstance(r, dict) else r[4]
                        samples.append(
                            {
                                "symbol": symbol,
                                "date": str(date),
                                "pct_drop": round(pct_change, 1) if pct_change is not None else None,
                            }
                        )
                    except (TypeError, KeyError, IndexError) as e:
                        logger.warning(f"Could not extract sample from {r}: {e}")
                self.log(
                    "corporate_action",
                    WARN,
                    "price_daily",
                    f"{len(extreme_drops)} symbols with >{drop_ratio * -100:.0f}% single-day drop (likely corporate action)",
                    {
                        "count": len(extreme_drops),
                        "samples": samples,
                    },
                )
            else:
                self.log(
                    "corporate_action",
                    INFO,
                    "price_daily",
                    "No extreme drops detected (no obvious corporate actions)",
                    None,
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            self.log("corporate_action", ERROR, "price_daily", f"Check failed: {e}", None)

    def check_sequence_continuity(self, cur: Any) -> None:
        try:
            interval_60d = get_interval_sql("60d")
            cur.execute(f"""
                WITH d AS (
                    SELECT date, LAG(date) OVER (ORDER BY date) AS prev
                    FROM price_daily
                    WHERE symbol = 'SPY'
                      AND date >= CURRENT_DATE - {interval_60d}
                )
                SELECT date, prev, (date - prev) AS gap_days
                FROM d
                WHERE prev IS NOT NULL AND (date - prev) > 4
                ORDER BY date DESC
                LIMIT 5
            """)
            gaps = cur.fetchall()

            if gaps:
                gap_list = []
                for r in gaps:
                    try:
                        gap_date = r.get("date") if hasattr(r, "get") else r[0]
                        gap_days = r.get("gap_days") if hasattr(r, "get") else r[2]
                        gap_list.append({"date": str(gap_date), "days": int(gap_days)})
                    except (KeyError, IndexError, TypeError) as e:
                        logger.warning(f"Could not extract gap data from row {r}: {e}")
                self.log(
                    "sequence",
                    WARN,
                    "price_daily",
                    f"{len(gaps)} sequence gaps in SPY (last 60 days)",
                    {"gaps": gap_list},
                )
            else:
                self.log(
                    "sequence",
                    INFO,
                    "price_daily",
                    "SPY price sequence contiguous",
                    None,
                )
        except (ValueError, ZeroDivisionError, TypeError) as e:
            self.log("sequence", ERROR, "price_daily", f"Check failed: {e}", None)

    # Isolated-spike batch-corruption signature (volume<=0-10, data_source='yfinance',
    # >100x away from a real bracketing neighbor). Root-caused to a pre-2026-08-26
    # PriceTransformer bug (fixed in 8f8537816) that let historical-backfill batches skip
    # sequence/gap/split-ratio validation entirely; 38,311 already-corrupted rows across 161
    # symbols were cleaned up in a one-off forensic pass (see memory:
    # price_daily_retroactive_corruption_never_cleaned_up_20260913) using a standalone script
    # that was never wired into any recurring check - promoted here so a regression (a new
    # backfill path bypassing the ingestion fix, or the fix itself regressing) surfaces on the
    # next DataPatrol run instead of requiring another ad-hoc dig.
    _ISOLATED_SPIKE_RATIO = 100.0
    _SPIKE_VOLUME_THRESHOLD = 10

    def check_isolated_spike_corruption(self, cur: Any) -> None:
        try:
            cur.execute(
                """
                SELECT DISTINCT symbol FROM price_daily
                WHERE volume <= %(threshold)s AND data_source = 'yfinance'
                """,
                {"threshold": self._SPIKE_VOLUME_THRESHOLD},
            )
            candidate_symbols = [r[0] if not isinstance(r, dict) else r["symbol"] for r in cur.fetchall()]

            confirmed: list[dict[str, Any]] = []
            for symbol in candidate_symbols:
                cur.execute(
                    "SELECT date, close, volume, data_source FROM price_daily WHERE symbol = %(symbol)s ORDER BY date",
                    {"symbol": symbol},
                )
                rows = cur.fetchall()
                is_batch = [
                    (r[2] if not isinstance(r, dict) else r["volume"]) is not None
                    and (r[2] if not isinstance(r, dict) else r["volume"]) <= self._SPIKE_VOLUME_THRESHOLD
                    and (r[3] if not isinstance(r, dict) else r["data_source"]) == "yfinance"
                    for r in rows
                ]

                def _close(r: Any) -> float:
                    return float(r[1] if not isinstance(r, dict) else r["close"])

                def _date(r: Any) -> Any:
                    return r[0] if not isinstance(r, dict) else r["date"]

                i, n = 0, len(rows)
                while i < n:
                    if not is_batch[i]:
                        i += 1
                        continue
                    j = i
                    while j < n and is_batch[j]:
                        j += 1
                    run = rows[i:j]
                    prev_close = _close(rows[i - 1]) if i > 0 else None
                    next_close = _close(rows[j]) if j < n else None
                    run_min = min(_close(r) for r in run)

                    confirmed_bad = (
                        prev_close and prev_close > 0 and run_min / prev_close > self._ISOLATED_SPIKE_RATIO
                    ) or (next_close and next_close > 0 and run_min / next_close > self._ISOLATED_SPIKE_RATIO)
                    if confirmed_bad:
                        confirmed.append(
                            {
                                "symbol": symbol,
                                "start": str(_date(run[0])),
                                "end": str(_date(run[-1])),
                                "rows": len(run),
                            }
                        )
                    i = j

            if confirmed:
                total_rows = sum(r["rows"] for r in confirmed)
                self.log(
                    "isolated_spike_corruption",
                    ERROR,
                    "price_daily",
                    f"{total_rows} confirmed-corrupted row(s) across {len(confirmed)} symbol(s) "
                    f"(batch-tagged volume<={self._SPIKE_VOLUME_THRESHOLD} run bracketed by a real "
                    f">{self._ISOLATED_SPIKE_RATIO:.0f}x-away neighbor) - see "
                    "scripts/check_price_daily_isolated_spikes.py for detail/remediation",
                    {"count": total_rows, "symbols": len(confirmed), "samples": confirmed[:10]},
                )
            else:
                self.log(
                    "isolated_spike_corruption",
                    INFO,
                    "price_daily",
                    "No isolated-spike batch corruption detected",
                    None,
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError, ValueError, ZeroDivisionError, TypeError) as e:
            self.log("isolated_spike_corruption", ERROR, "price_daily", f"Check failed: {e}", None)
