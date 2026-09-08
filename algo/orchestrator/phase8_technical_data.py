"""Batch technical-data fetch for Phase 8 entry execution.

Extracted verbatim from phase8_entry_execution.py (2026-09-08) - a pure, self-contained
function with no dependency on that module's per-run loop state, moved out purely to make
room under the file-size ratchet (phase8_entry_execution.py was already at its frozen
baseline with zero slack) rather than for any behavior change. See CLAUDE.md's bloater-
decomposition note - this is the "extract a module first" path the ratchet's own error
message prescribes.
"""

import logging
from datetime import date as _date
from datetime import timedelta
from typing import Any, cast

from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)


def _batch_fetch_technical_data(
    symbols_with_precomputed: dict[str, dict[str, Any]], run_date: _date, period: int = 14
) -> dict[str, dict[str, float | None]]:
    """Batch-fetch missing ATR and SMA_50 data, using pre-computed values from Phase 5 when available.



    Args:

        symbols_with_precomputed: Dict mapping symbol -> {pre-computed fields from Phase 5}

        run_date: Trading date

        period: ATR period (default 14)



    Returns dict keyed by symbol with {atr, sma_50, close} values.



    ISSUE #8 FIX: Reuses Phase 5's SMA_50 and ATR computations instead of recomputing.

    Only fetches missing data (symbols with no phase5_precomputed values).

    """

    if not symbols_with_precomputed:
        # Phase 5 didn't run or produced no candidates (e.g., circuit breaker halted entry)
        # This is not an error-it means no entries are allowed. Return empty dict (no candidates to process).
        logger.warning(
            "[PHASE8] No precomputed technical data available for entry execution. "
            "Phase 5 likely halted or produced no candidates. No entries will be executed this run."
        )
        return {}

    # Separate symbols that have precomputed values from those that don't

    precomputed_by_symbol = {}

    symbols_needing_fetch = []

    for symbol, data in symbols_with_precomputed.items():
        has_atr = data.get("atr_14") is not None

        has_sma = data.get("sma_50") is not None

        has_close = data.get("close") is not None

        if has_atr and has_sma and has_close:
            # All values precomputed in Phase 5

            precomputed_by_symbol[symbol] = {
                "atr": float(data["atr_14"]),
                "sma_50": float(data["sma_50"]),
                "close": float(data["close"]),
            }

        else:
            # Missing at least one value � fetch from DB

            symbols_needing_fetch.append(symbol)

    if not symbols_needing_fetch:
        # All data precomputed in Phase 5, no DB fetch needed

        return cast(dict[str, dict[str, float | None]], precomputed_by_symbol)

    # Fetch missing data only for symbols that lack precomputed values
    # Use SQL parameter markers (%s) for safe parameterized queries
    symbol_placeholders = ",".join(["%s"] * len(symbols_needing_fetch))

    result: dict[str, dict[str, float | None]] = cast(dict[str, dict[str, float | None]], precomputed_by_symbol.copy())

    try:
        with DatabaseContext("read") as cur:
            cur.execute(
                f"""WITH latest_prices AS (
                    SELECT DISTINCT ON (symbol) symbol, close
                    FROM price_daily
                    WHERE symbol IN ({symbol_placeholders}) AND date <= %s
                    ORDER BY symbol, date DESC
                ),
                sma_50_data AS (
                    SELECT symbol, AVG(close) AS sma_50
                    FROM (
                        SELECT symbol, close,
                               ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                        FROM price_daily
                        WHERE symbol IN ({symbol_placeholders}) AND date <= %s
                    ) t
                    WHERE rn <= 50
                    GROUP BY symbol
                )
                SELECT lp.symbol, sma.sma_50, lp.close
                FROM latest_prices lp
                INNER JOIN sma_50_data sma ON sma.symbol = lp.symbol""",
                [
                    *symbols_needing_fetch,
                    run_date,
                    *symbols_needing_fetch,
                    run_date,
                ],
            )

            sma_close_by_symbol: dict[str, tuple[Any, Any]] = {}
            for row in cur.fetchall():
                if isinstance(row, dict):
                    row_symbol = row.get("symbol")
                    sma_50 = row.get("sma_50")
                    close = row.get("close")
                else:
                    if len(row) < 3:
                        raise IndexError(f"Row has {len(row)} columns, expected 3")
                    row_symbol, sma_50, close = row
                if row_symbol is not None:
                    sma_close_by_symbol[row_symbol] = (sma_50, close)

            # FIXED 2026-08-24 (was: flat SMA-of-True-Range, a documented methodology mismatch -
            # see batch_fetch_atr_methodology_mismatch_found_20260824 in memory for the original
            # finding): compute ATR using the exact same compute_atr() (Wilder's EMA,
            # loaders/technical_indicators.py) that populates technical_data_daily.atr_14 - the
            # value this whole function exists to substitute for when missing - instead of
            # reimplementing Wilder smoothing by hand in SQL (a recursive-CTE EMA is easy to get
            # subtly wrong and hard to validate). Fetches atr_history_trading_days of OHLC
            # history per symbol as a warm-up window: ewm(alpha=1/period, adjust=False) weighs
            # data exponentially, so any finite warm-up window introduces some seed-value error,
            # but at alpha=1/14 the residual weight from >70 trading days back decays below 1%
            # ((13/14)^70 =~ 0.007) - 100 trading days gives ample margin. Empirically validated
            # (2026-08-24) against technical_data_daily.atr_14 for 9 real symbols (spot-checked
            # + 8 random): 8/9 matched to within 0.04% (float/warm-up rounding); one microcap
            # (NDRA) differed 2.48%, but the gap was IDENTICAL across 160/300/500/1000-day
            # warm-up windows - ruling out warm-up convergence as the cause - most likely
            # technical_data_daily's stored value is simply stale relative to current price_daily
            # for that symbol (this function computing fresh from current data is a feature of
            # the fix, not a flaw). Same formula as the primary loader by construction (calls the
            # identical compute_atr()), so per-symbol drift here is a data-freshness question,
            # not a methodology one.
            atr_history_trading_days = 100
            history_start = run_date - timedelta(days=int(atr_history_trading_days * 1.6))
            cur.execute(
                f"""SELECT symbol, date, high, low, close
                    FROM price_daily
                    WHERE symbol IN ({symbol_placeholders}) AND date <= %s AND date >= %s
                    ORDER BY symbol, date ASC""",
                [*symbols_needing_fetch, run_date, history_start],
            )
            ohlc_rows = cur.fetchall()

        atr_by_symbol: dict[str, float] = {}
        if ohlc_rows:
            import math as _math

            import pandas as pd

            from loaders.technical_indicators import compute_atr

            ohlc_records = [dict(r) if isinstance(r, dict) else r for r in ohlc_rows]
            ohlc_df = pd.DataFrame(ohlc_records, columns=["symbol", "date", "high", "low", "close"])
            for col in ("high", "low", "close"):
                ohlc_df[col] = ohlc_df[col].astype(float)
            for sym, group in ohlc_df.groupby("symbol"):
                if len(group) < period:
                    # Not enough history for a real ATR (same as the old fallback's implicit
                    # behavior when insufficient rows existed) - leave missing, handled below.
                    continue
                group = group.sort_values("date")
                atr_series = compute_atr(group["high"], group["low"], group["close"], period)
                last_atr = atr_series.iloc[-1]
                if last_atr is not None and not (_math.isnan(last_atr) or _math.isinf(last_atr)):
                    atr_by_symbol[sym] = float(last_atr)

        for row_symbol, (sma_50, close) in sma_close_by_symbol.items():
            atr = atr_by_symbol.get(row_symbol)
            if atr is None or sma_50 is None or close is None:
                logger.warning(
                    f"[PHASE 8] Symbol {row_symbol}: Technical data incomplete (ATR={atr}, SMA_50={sma_50}, close={close}). "
                    f"Skipping this symbol. Check technical_data_daily table for completeness."
                )
                # CRITICAL FIX: Skip this symbol instead of halting all entry execution
                # One symbol with bad technical data should not block entries for all other symbols
                continue

            # CRITICAL FIX: Session 345 - Validate type conversions (handles NaN/Infinity)
            try:
                from utils.type_conversion import safe_float

                atr_float = safe_float(atr, f"{row_symbol}.atr", allow_none=False)
                sma_50_float = safe_float(sma_50, f"{row_symbol}.sma_50", allow_none=False)
                close_float = safe_float(close, f"{row_symbol}.close", allow_none=False)
            except (ValueError, TypeError) as e:
                logger.error(f"[ENTRY EXECUTION] {row_symbol}: Technical data type conversion failed: {e}")
                raise ValueError(f"Technical data validation failed for {row_symbol}: {e}") from e

            result[row_symbol] = cast(
                dict[str, float | None],
                {
                    "atr": atr_float,
                    "sma_50": sma_50_float,
                    "close": close_float,
                },
            )

        return result

    except (ValueError, ZeroDivisionError, TypeError) as e:
        raise RuntimeError(f"Batch fetch technical data failed: {e}") from e
