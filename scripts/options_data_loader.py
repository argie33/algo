#!/usr/bin/env python3
"""Options data loader - CSP/covered-call candidate screener (POC data pipeline).

Goal session 2026-09-12: builds the options data foundation validated live that session
(spot price, full contract chain, self-computed Black-Scholes IV/delta all work on the free
yfinance feed with zero paid subscription) into an actual, runnable, idempotent loader -
replacing `loaders/load_options_chains.py`, deleted 2026-07-11 (commit 7896f85a9) as
"unfinished". That loader had two real, structural bugs this one fixes rather than repeats:

1. Its `_insert_iv_history` queried `iv_history` for 252 days of PRIOR history before ever
   inserting a row - a chicken-and-egg bug that made the table permanently unbuildable from
   a cold start (day 1 always raised before any row was written). This loader instead
   upserts today's current_iv first, then recomputes iv_52w_high/iv_52w_low from whatever
   history now exists (just today's row, on day 1) - genuinely bootstraps over time instead
   of requiring history it can never create.
2. Its options_chains INSERT only ever wrote (symbol, option_type, strike_price, volume,
   quote_date) - 5 of the table's 12 columns - despite the schema already anticipating
   bid/ask/last_price/open_interest/expiration_date/contract_symbol/iv/days_to_expiration
   (confirmed live: the frozen 2026-06-20 snapshot it left behind has every one of those
   NULL on all 2,422 rows). This loader captures the full quote.

Time-alignment (the one real engineering lesson from this session's live validation): spot
price and option quotes must come from the SAME session close, or deep-ITM strikes get a
fake negative time value (a stray after-hours stock tick compared against options frozen at
the prior 4pm close - options don't trade extended hours, the underlying does). This loader
uses the daily bar's own closing price/date as `quote_date`, not a live/fast_info tick.

Direct in-process `yf.Ticker(...).options` / `.option_chain(...)` calls, protected by the
generic OPTIONAL CircuitBreaker (utils.loaders.helpers.create_circuit_breaker) - the same
pattern loaders/market_health_fetchers.py's PutCallRatioFetcher already uses live in
production for this exact SPY-options call shape, NOT the process-isolated
_YfinanceAttrProcessWorker other yfinance call sites in this codebase were hardened onto
(utils/external/yfinance_analyst_ratings.py / yfinance_financials.py) - that worker only
supports zero-argument attribute fetches (`getattr(ticker, attr)`), it cannot call
`option_chain(expiration_str)`, which takes a required argument.

Scheduling (added goal session 2026-09-12, options-strategy planning phase 1): this is a
daily-rotating-sample periodic script - like scripts/xbrl_yfinance_crosscheck.py, NOT a
critical/gating production loader - deliberately kept OUT of loaders/runner.py's
OptimalLoader base class, LOADER_TABLES, and the Step-Functions-gated pipeline
(terraform/modules/pipeline/main.tf). It shares the exact same rationale as
scripts/xbrl_second_opinion_daily.py: it makes live outbound yfinance calls with
unpredictable latency and shared-IP rate-limit exposure
(yfinance_validation_calls_self_triggered_ban_during_reload_20260903 in MEMORY.md), so it
gets its own independent EventBridge-triggered ECS task
(terraform/modules/loaders/main.tf's `options_data_loader` resources), never folded into
anything Phase 1 gates on. `_select_symbols()`'s `ORDER BY md5(symbol || CURRENT_DATE::text)`
rotates the sample by calendar date - the same daily-accumulation mechanism as the xbrl
second-opinion layers - so running it daily (not weekly) is what actually cycles through
the full market_constituents universe in a reasonable number of months rather than years.
**Caveat, matching this repo's own honesty elsewhere: writing this terraform is not the
same as applying it** - run `terraform plan`/`apply` in `terraform/` to actually turn the
schedule on; until then this script is still manual-only in practice. Promoting it further,
to a critical/gating loader, is a separate, later decision once real strategy execution
that depends on same-day freshness exists (a written strategy spec + backtest validation
must land first - see the phased options-strategy plan, not yet a checked-in doc as of this
commit) - this phase only fixes "depends on a human remembering to run it."

Risk-free rate: 3-month Treasury (economic_data.DGS3MO) - the right tenor for the
30-45-day-DTE options this is meant to screen, not the 10-year rate load_sec_valuations.py's
DCF work uses for equity discount rates. Falls back to a static 4.5% default when no recent
reading exists, same convention as loaders/helpers/sec_valuations_dcf.py's
DCF_DEFAULT_RISK_FREE_RATE.

Usage:
    python scripts/options_data_loader.py --symbols AAPL,MSFT
    python scripts/options_data_loader.py --limit 50
    python scripts/options_data_loader.py --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MAX_EXPIRATIONS = 2  # nearest N expirations only - keeps per-symbol call count bounded
NEAR_MONEY_BAND = 0.05  # within 5% of spot counts toward the iv_history current_iv sample
RATE_LIMIT_SLEEP_SEC = 0.5
DEFAULT_RISK_FREE_RATE = 0.045
IV_HISTORY_LOOKBACK_DAYS = 252


def _select_symbols(cur: Any, limit: int) -> list[str]:
    """Daily-rotating pseudo-random sample of liquid, optionable symbols.

    Restricted to market_constituents (S&P 500 / NASDAQ 100 / etc.) for the same reason the
    deleted loader gave: penny stocks and micro-caps rarely have real options liquidity, and
    fetching them wastes yfinance calls this codebase's shared rate limit can't spare (see
    MEMORY.md yfinance_validation_calls_self_triggered_ban_during_reload_20260903).
    """
    cur.execute(
        """
        SELECT DISTINCT symbol FROM market_constituents
        WHERE symbol IS NOT NULL
        ORDER BY md5(symbol || CURRENT_DATE::text)
        LIMIT %s
        """,
        (limit,),
    )
    return [row[0] for row in cur.fetchall()]


def _get_risk_free_rate(cur: Any) -> float:
    cur.execute(
        """
        SELECT value FROM economic_data
        WHERE series_id = 'DGS3MO' AND date >= CURRENT_DATE - INTERVAL '10 days' AND value IS NOT NULL
        ORDER BY date DESC LIMIT 1
        """
    )
    row = cur.fetchone()
    if row is not None and row[0] is not None:
        return float(row[0]) / 100.0
    return DEFAULT_RISK_FREE_RATE


def _time_aligned_spot(ticker: Any) -> tuple[float, date]:
    """Last completed session's close + its date - NOT fast_info's live/after-hours tick.

    This is the exact fix for the fake negative-time-value bug found live this session:
    options are frozen at the prior 4pm close, so spot must come from that same close, not
    a stray extended-hours print on the underlying.
    """
    hist = ticker.history(period="5d", interval="1d")
    if hist.empty:
        raise RuntimeError("No daily price history returned - cannot determine a time-aligned spot price")
    last_close = float(hist["Close"].iloc[-1])
    last_date = hist.index[-1].date()
    if last_close <= 0:
        raise RuntimeError(f"Invalid last close price: {last_close}")
    return last_close, last_date


def _load_symbol(cur: Any, breaker: Any, symbol: str, risk_free_rate: float, dry_run: bool) -> dict[str, Any]:
    from utils.external.yfinance_symbol import to_yfinance_symbol
    from utils.options.black_scholes import call_delta, put_delta

    def _fetch() -> dict[str, Any] | None:
        import yfinance as yf

        yf_symbol = to_yfinance_symbol(symbol)
        ticker = yf.Ticker(yf_symbol)
        spot, quote_date = _time_aligned_spot(ticker)

        expirations = ticker.options
        if not expirations:
            return {"chain_rows": [], "iv_samples": [], "spot": spot, "quote_date": quote_date}

        chain_rows: list[dict[str, Any]] = []
        iv_samples: list[float] = []

        for exp_str in expirations[:MAX_EXPIRATIONS]:
            exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
            days_to_exp = (exp_date - quote_date).days
            if days_to_exp <= 0:
                continue
            t_years = days_to_exp / 365.0

            chain = ticker.option_chain(exp_str)
            for option_type, df in (("call", chain.calls), ("put", chain.puts)):
                for _, opt_row in df.iterrows():
                    strike = opt_row.get("strike")
                    iv = opt_row.get("impliedVolatility")
                    if strike is None or iv is None or iv != iv or iv <= 0:  # iv != iv is NaN check
                        continue
                    strike = float(strike)
                    iv = float(iv)

                    delta: float | None
                    try:
                        delta = (
                            call_delta(spot, strike, t_years, risk_free_rate, iv)
                            if option_type == "call"
                            else put_delta(spot, strike, t_years, risk_free_rate, iv)
                        )
                    except ValueError:
                        delta = None

                    bid = opt_row.get("bid")
                    ask = opt_row.get("ask")
                    chain_rows.append(
                        {
                            "contract_symbol": opt_row.get("contractSymbol"),
                            "option_type": option_type,
                            "strike_price": strike,
                            "expiration_date": exp_date,
                            "bid": float(bid) if bid == bid and bid is not None else None,
                            "ask": float(ask) if ask == ask and ask is not None else None,
                            "last_price": float(opt_row.get("lastPrice"))
                            if opt_row.get("lastPrice") == opt_row.get("lastPrice")
                            else None,
                            "volume": int(opt_row.get("volume"))
                            if opt_row.get("volume") == opt_row.get("volume")
                            else None,
                            "open_interest": int(opt_row.get("openInterest"))
                            if opt_row.get("openInterest") == opt_row.get("openInterest")
                            else None,
                            "iv": iv,
                            "days_to_expiration": days_to_exp,
                            "delta": delta,
                        }
                    )

                    if abs(strike - spot) / spot < NEAR_MONEY_BAND:
                        iv_samples.append(iv)

        return {"chain_rows": chain_rows, "iv_samples": iv_samples, "spot": spot, "quote_date": quote_date}

    result = breaker.execute(fetch_func=_fetch, fallback_value=None)
    if result is None:
        return {"symbol": symbol, "status": "unavailable", "reason": "circuit breaker open or fetch failed"}

    chain_rows, iv_samples, spot, quote_date = (
        result["chain_rows"],
        result["iv_samples"],
        result["spot"],
        result["quote_date"],
    )

    if dry_run:
        logger.info(
            f"[DRY-RUN] {symbol}: spot={spot} quote_date={quote_date} "
            f"chain_rows={len(chain_rows)} iv_samples={len(iv_samples)}"
        )
        return {"symbol": symbol, "status": "dry_run", "chain_rows": len(chain_rows), "iv_samples": len(iv_samples)}

    if not chain_rows:
        return {"symbol": symbol, "status": "no_options"}

    # Idempotent re-run: replace this symbol/date's chain wholesale rather than upserting
    # row-by-row (no natural per-row unique key exists across re-fetches - strikes/expirations
    # can shift between runs on the same day if yfinance's chain composition changes).
    cur.execute("DELETE FROM options_chains WHERE symbol = %s AND quote_date = %s", (symbol, quote_date))
    for row in chain_rows:
        cur.execute(
            """
            INSERT INTO options_chains
            (symbol, contract_symbol, option_type, strike_price, expiration_date,
             bid, ask, last_price, volume, open_interest, quote_date, iv, days_to_expiration, delta)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                symbol,
                row["contract_symbol"],
                row["option_type"],
                row["strike_price"],
                row["expiration_date"],
                row["bid"],
                row["ask"],
                row["last_price"],
                row["volume"],
                row["open_interest"],
                quote_date,
                row["iv"],
                row["days_to_expiration"],
                row["delta"],
            ),
        )

    if iv_samples:
        current_iv = sum(iv_samples) / len(iv_samples)
        # Bootstrap-safe write, unlike the deleted loader: insert/update today's row FIRST,
        # then recompute the 52w range from whatever history now exists (just today, on a
        # symbol's very first run) - never requires history that only this code can create.
        cur.execute(
            """
            INSERT INTO iv_history (symbol, date, current_iv, iv_52w_high, iv_52w_low)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (symbol, date) DO UPDATE SET current_iv = EXCLUDED.current_iv
            """,
            (symbol, quote_date, current_iv, current_iv, current_iv),
        )
        cur.execute(
            f"""
            UPDATE iv_history SET iv_52w_high = sub.hi, iv_52w_low = sub.lo
            FROM (
                SELECT MAX(current_iv) AS hi, MIN(current_iv) AS lo FROM iv_history
                WHERE symbol = %s AND date >= %s - INTERVAL '{IV_HISTORY_LOOKBACK_DAYS} days'
            ) sub
            WHERE symbol = %s AND date = %s
            """,
            (symbol, quote_date, symbol, quote_date),
        )

    return {"symbol": symbol, "status": "ok", "chain_rows": len(chain_rows), "iv_samples": len(iv_samples)}


def run(limit: int, symbols_override: list[str] | None, dry_run: bool) -> dict[str, Any]:
    from utils.db.connection import get_db_connection
    from utils.loaders.helpers import create_circuit_breaker

    conn = get_db_connection(max_retries=2, timeout=30)
    cur = conn.cursor()

    symbols = symbols_override or _select_symbols(cur, limit)
    risk_free_rate = _get_risk_free_rate(cur)
    logger.info(f"[OPTIONS_DATA] {len(symbols)} symbol(s), risk_free_rate={risk_free_rate:.4f}: {symbols}")

    breaker = create_circuit_breaker("yfinance_options_data_loader", importance_name="OPTIONAL")
    results = []
    for symbol in symbols:
        try:
            res = _load_symbol(cur, breaker, symbol, risk_free_rate, dry_run)
        except Exception as e:
            logger.error(f"[OPTIONS_DATA] {symbol} failed: {e}")
            res = {"symbol": symbol, "status": "error", "error": str(e)}
        results.append(res)
        if not dry_run:
            conn.commit()
        time.sleep(RATE_LIMIT_SLEEP_SEC)

    cur.close()
    conn.close()
    ok_count = sum(1 for r in results if r["status"] in ("ok", "dry_run"))
    return {"symbols_processed": len(results), "ok": ok_count, "results": results}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--limit",
        type=int,
        default=25,
        help="How many symbols to sample this run (default 25 - matches the xbrl_yfinance_crosscheck.py "
        "precedent's daily-rotating-sample size for the same shared-rate-limit reasons)",
    )
    parser.add_argument("--symbols", help="Comma-separated explicit symbol list, overrides --limit sampling")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and print, don't write to the database")
    args = parser.parse_args()

    symbols_override = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else None
    result = run(args.limit, symbols_override, args.dry_run)
    logger.info(f"[OPTIONS_DATA] Done: {result['ok']}/{result['symbols_processed']} symbols ok")
    for r in result["results"]:
        logger.info(f"  {r}")


if __name__ == "__main__":
    main()
