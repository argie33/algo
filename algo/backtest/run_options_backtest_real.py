#!/usr/bin/env python3
"""Backtest: CSP + covered-call wheel strategy priced with REAL Alpaca historical options
quotes (options-strategy plan phase 3, real-data follow-up to `run_options_backtest.py`).

Written against `steering/OPTIONS_STRATEGY_SPEC.md` go/no-go gate §7 item 1, which the
Black-Scholes-proxy backtest (`run_options_backtest.py`) explicitly does NOT satisfy - that
script's own docstring says real historical options-quote data is required to actually confirm
the edge. This script is that follow-up, added once Alpaca credentials became resolvable from
this local session (2026-09-15) - previously blocked, see MEMORY.md
`options_sleeve_status_20260915`.

**What's real vs. still modeled - read before trusting any number this prints.**
- **Real**: the premium collected at entry for every simulated CSP/covered-call is the actual
  historical closing print of the real, listed OCC option contract on Alpaca's options data API
  (`/v1beta1/options/bars`, 15-min-delayed OPRA-derived free "indicative" feed - same account
  already funded and options-approved, see `check_options_approval_status.py`). Assignment/
  called-away outcomes are determined by the real underlying `price_daily` close on the real
  contract's actual expiration date vs. the real strike - already fully real in the proxy
  backtest, unchanged here.
- **Still modeled, not real**: which STRIKE to target is still selected via the same
  Black-Scholes delta calculation the proxy backtest uses (`realized_vol x VRP multiplier` as
  an IV input to `_find_strike_by_delta`) - Alpaca's historical bars endpoint returns OHLC for a
  contract you already know the symbol for, not a historical options chain with greeks, so
  there is no source of real historical delta to select against. This means the "0.15-0.30
  delta" targeting criterion in spec §3 is still a model output, not an observed value, even
  though the resulting contract's PRICE is real. Documented explicitly rather than silently
  blurring "real backtest" into "every input is real."
- **Data coverage floor, Feb 2024**: Alpaca's historical options data starts February 2024 -
  does not reach the 2020 COVID crash or 2022 bear market spec §7.1 names as reference regimes.
  Default window here is 2024-02-05 (first Monday with data) through today.

Reuses the proxy backtest's universe selection, price-series loading, delta-targeting
strike-selection math, and standard-expiration-day settlement logic verbatim
(`_select_universe`, `_load_price_series`, `_find_strike_by_delta`, `_risk_free_rate_asof`
imported from `run_options_backtest.py`, not re-implemented) - only the premium/price source
changes, per the module's own scope.

Where a real quote for the selected contract can't be found (contract too illiquid, or the
OCC-symbol construction doesn't match what Alpaca actually lists - both possible failure modes,
see `_occ_symbol`'s docstring), the cycle is SKIPPED, never silently backfilled with the
proxy's Black-Scholes price - mixing real and synthetic premiums in one result would make the
result's evidentiary value ambiguous. `real_quote_coverage_pct` in the output reports what
fraction of attempted cycles actually got a real fill.

Usage:
    python -m algo.backtest.run_options_backtest_real --limit 20
    python -m algo.backtest.run_options_backtest_real --symbols AAPL,MSFT,KO --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import pandas as pd
import psycopg2
import requests

from algo.backtest.run_options_backtest import (
    DEFAULT_COMMISSION_PER_CONTRACT,
    DEFAULT_SPREAD_HAIRCUT_PCT,
    DEFAULT_VRP_MULTIPLIER,
    TARGET_DTE_DAYS,
    _find_strike_by_delta,
    _load_price_series,
    _nearest_row_on_or_after,
    _risk_free_rate_asof,
    _select_universe,
)
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

ALPACA_OPTIONS_DATA_URL = "https://data.alpaca.markets/v1beta1/options"
# Free/Basic plan documented limit is 200/min (same figure utils/external/alpaca_market_data.py
# already relies on for equity bars) - throttled well under that since this script also shares
# the account/IP with whatever else may be running.
MIN_REQUEST_INTERVAL_SEC = 0.35
MIN_REAL_DATA_START = date(2024, 2, 5)  # Alpaca historical options data floor
# Standard strike increments by underlying price band - approximate, real listed strikes vary
# by name/liquidity; only used to round a BS-targeted strike to something plausibly listed.
_STRIKE_INCREMENTS = [(25.0, 0.5), (100.0, 1.0), (200.0, 2.5), (float("inf"), 5.0)]


@dataclass
class RealCycleResult:
    symbol: str
    cycle_type: str
    entry_date: date
    exit_date: date
    strike: float
    spot_entry: float
    spot_exit: float
    premium_net: float
    collateral: float
    assigned_or_called: bool
    pnl_dollars: float
    return_on_collateral_pct: float


@dataclass
class SymbolSimResult:
    symbol: str
    cycles: list[RealCycleResult] = field(default_factory=list)
    skipped_no_strike: int = 0
    skipped_no_quote: int = 0


class _RateLimiter:
    def __init__(self, min_interval_sec: float) -> None:
        self.min_interval_sec = min_interval_sec
        self._last_call = 0.0

    def wait(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self.min_interval_sec:
            time.sleep(self.min_interval_sec - elapsed)
        self._last_call = time.monotonic()


def _round_to_standard_strike(strike: float) -> float:
    for band_ceiling, increment in _STRIKE_INCREMENTS:
        if strike < band_ceiling:
            return round(strike / increment) * increment
    return round(strike)


def _third_friday(year: int, month: int) -> date:
    """Standard monthly equity-options expiration (3rd Friday). Weeklies exist for liquid
    names too, but monthly is the safer construction to assume lists across the full
    Feb-2024-present window for a broad universe."""
    d = date(year, month, 1)
    first_friday_offset = (4 - d.weekday()) % 7
    return d + timedelta(days=first_friday_offset + 14)


def _nearest_monthly_expiration(target: date, dte_low: int, dte_high: int, entry_date: date) -> date | None:
    """Return the monthly 3rd-Friday expiration closest to `target` whose DTE from
    `entry_date` still falls in [dte_low, dte_high], or None if no such month exists."""
    candidates = []
    for month_offset in (-1, 0, 1, 2):
        year = target.year + (target.month - 1 + month_offset) // 12
        month = (target.month - 1 + month_offset) % 12 + 1
        exp = _third_friday(year, month)
        dte = (exp - entry_date).days
        if dte_low <= dte <= dte_high:
            candidates.append((abs((exp - target).days), exp))
    if not candidates:
        return None
    candidates.sort(key=lambda t: t[0])
    return candidates[0][1]


def _occ_symbol(underlying: str, expiration: date, option_type: str, strike: float) -> str:
    """Construct the standard OCC option symbol: SYMBOL + YYMMDD + C/P + strike*1000 zero-
    padded to 8 digits. Deterministic - Alpaca has no historical chain-discovery endpoint, so
    this is derived directly rather than looked up (verified live against a known contract
    2026-09-15: AAPL240621P00190000 returned real bars)."""
    cp = "C" if option_type == "call" else "P"
    strike_code = f"{round(strike * 1000):08d}"
    return f"{underlying}{expiration.strftime('%y%m%d')}{cp}{strike_code}"


def _fetch_real_close(
    session: requests.Session,
    headers: dict[str, str],
    limiter: _RateLimiter,
    occ_symbol: str,
    target_date: date,
) -> float | None:
    """Real historical closing print for one contract on (or the nearest trading day at/after)
    target_date, within a small lookahead window. Returns None (never a fallback price) if no
    bar exists - illiquid contract or a wrong OCC construction, both real possibilities."""
    limiter.wait()
    try:
        resp = session.get(
            f"{ALPACA_OPTIONS_DATA_URL}/bars",
            headers=headers,
            params={
                "symbols": occ_symbol,
                "timeframe": "1Day",
                "start": target_date.isoformat(),
                "end": (target_date + timedelta(days=5)).isoformat(),
                "limit": 5,
            },
            timeout=15,
        )
    except requests.RequestException as e:
        logger.warning(f"[OPTIONS-BACKTEST-REAL] request failed for {occ_symbol}: {e}")
        return None
    if resp.status_code != 200:
        return None
    bars = resp.json().get("bars", {}).get(occ_symbol)
    if not bars:
        return None
    return float(bars[0]["c"])


def _simulate_symbol_wheel_real(
    session: requests.Session,
    headers: dict[str, str],
    limiter: _RateLimiter,
    cur: Any,
    symbol: str,
    df: pd.DataFrame,
    start_date: date,
    end_date: date,
    vrp_multiplier: float,
    commission: float,
    spread_haircut_pct: float,
    max_cycles: int,
) -> SymbolSimResult:
    result = SymbolSimResult(symbol=symbol)
    phase = "csp"
    cost_basis: float | None = None
    current_date = max(start_date, MIN_REAL_DATA_START)

    for _ in range(max_cycles):
        entry_row = _nearest_row_on_or_after(df, current_date)
        if entry_row is None:
            break
        entry_date = entry_row["date"]
        target_exit = entry_date + timedelta(days=TARGET_DTE_DAYS)
        if target_exit > end_date:
            break

        realized_vol = entry_row["realized_vol"]
        if realized_vol is None or pd.isna(realized_vol) or realized_vol <= 0:
            current_date = entry_date + timedelta(days=TARGET_DTE_DAYS)
            result.skipped_no_strike += 1
            continue
        iv = float(realized_vol) * vrp_multiplier
        spot_entry = float(entry_row["price"])
        r = _risk_free_rate_asof(cur, entry_date)

        expiration = _nearest_monthly_expiration(target_exit, 27, 48, entry_date)
        if expiration is None:
            current_date = entry_date + timedelta(days=TARGET_DTE_DAYS)
            result.skipped_no_strike += 1
            continue
        time_to_expiry = max((expiration - entry_date).days, 1) / 365.0

        exit_row = _nearest_row_on_or_after(df, expiration)
        if exit_row is None:
            break
        spot_exit = float(exit_row["price"])

        if phase == "csp":
            found = _find_strike_by_delta(spot_entry, time_to_expiry, r, iv, is_put=True)
            if found is None:
                current_date = expiration + timedelta(days=1)
                result.skipped_no_strike += 1
                continue
            raw_strike, _ = found
            strike = _round_to_standard_strike(raw_strike)
            occ = _occ_symbol(symbol, expiration, "put", strike)
            premium_mid = _fetch_real_close(session, headers, limiter, occ, entry_date)
            if premium_mid is None:
                current_date = expiration + timedelta(days=1)
                result.skipped_no_quote += 1
                continue
            premium_net = premium_mid * 100 * (1 - spread_haircut_pct / 100) - commission
            collateral = strike * 100
            assigned = spot_exit < strike
            if assigned:
                pnl_dollars = premium_net - (strike - spot_exit) * 100
                cost_basis = strike - premium_net / 100
            else:
                pnl_dollars = premium_net
            result.cycles.append(
                RealCycleResult(
                    symbol=symbol,
                    cycle_type="csp",
                    entry_date=entry_date,
                    exit_date=expiration,
                    strike=strike,
                    spot_entry=spot_entry,
                    spot_exit=spot_exit,
                    premium_net=premium_net,
                    collateral=collateral,
                    assigned_or_called=assigned,
                    pnl_dollars=pnl_dollars,
                    return_on_collateral_pct=pnl_dollars / collateral * 100,
                )
            )
            phase = "covered_call" if assigned else "csp"

        else:  # covered_call
            assert cost_basis is not None
            found = _find_strike_by_delta(spot_entry, time_to_expiry, r, iv, is_put=False, min_strike=cost_basis)
            if found is None:
                current_date = expiration + timedelta(days=1)
                result.skipped_no_strike += 1
                continue
            raw_strike, _ = found
            strike = max(_round_to_standard_strike(raw_strike), _round_to_standard_strike(cost_basis))
            occ = _occ_symbol(symbol, expiration, "call", strike)
            premium_mid = _fetch_real_close(session, headers, limiter, occ, entry_date)
            if premium_mid is None:
                current_date = expiration + timedelta(days=1)
                result.skipped_no_quote += 1
                continue
            premium_net = premium_mid * 100 * (1 - spread_haircut_pct / 100) - commission
            collateral = cost_basis * 100
            called_away = spot_exit >= strike
            pnl_dollars = premium_net + (strike - cost_basis) * 100 if called_away else premium_net
            result.cycles.append(
                RealCycleResult(
                    symbol=symbol,
                    cycle_type="covered_call",
                    entry_date=entry_date,
                    exit_date=expiration,
                    strike=strike,
                    spot_entry=spot_entry,
                    spot_exit=spot_exit,
                    premium_net=premium_net,
                    collateral=collateral,
                    assigned_or_called=called_away,
                    pnl_dollars=pnl_dollars,
                    return_on_collateral_pct=pnl_dollars / collateral * 100,
                )
            )
            if called_away:
                phase = "csp"
                cost_basis = None

        current_date = expiration + timedelta(days=1)

    return result


def run_options_backtest_real(
    symbols: list[str] | None,
    limit: int,
    start_date: date,
    end_date: date,
    vrp_multiplier: float = DEFAULT_VRP_MULTIPLIER,
    commission: float = DEFAULT_COMMISSION_PER_CONTRACT,
    spread_haircut_pct: float = DEFAULT_SPREAD_HAIRCUT_PCT,
    max_cycles_per_symbol: int = 40,
) -> dict[str, Any]:
    key_id = os.environ.get("APCA_API_KEY_ID")
    secret = os.environ.get("APCA_API_SECRET_KEY")
    if not key_id or not secret:
        raise RuntimeError(
            "APCA_API_KEY_ID / APCA_API_SECRET_KEY not resolvable from the environment - "
            "this script makes real Alpaca options-data API calls and cannot proxy/fallback."
        )
    headers = {"APCA-API-KEY-ID": key_id, "APCA-API-SECRET-KEY": secret}
    session = requests.Session()
    limiter = _RateLimiter(MIN_REQUEST_INTERVAL_SEC)

    with DatabaseContext("read") as cur:
        universe = [{"symbol": s, "sector": "Unknown"} for s in symbols] if symbols else _select_universe(cur, limit)

        all_cycles: list[RealCycleResult] = []
        skipped_symbols: list[str] = []
        skipped_no_strike_total = 0
        skipped_no_quote_total = 0

        for entry in universe:
            symbol = entry["symbol"]
            df = _load_price_series(cur, symbol, start_date, end_date)
            if df is None:
                skipped_symbols.append(symbol)
                continue
            sim = _simulate_symbol_wheel_real(
                session,
                headers,
                limiter,
                cur,
                symbol,
                df,
                start_date,
                end_date,
                vrp_multiplier,
                commission,
                spread_haircut_pct,
                max_cycles_per_symbol,
            )
            all_cycles.extend(sim.cycles)
            skipped_no_strike_total += sim.skipped_no_strike
            skipped_no_quote_total += sim.skipped_no_quote

    attempted = len(all_cycles) + skipped_no_quote_total
    coverage_pct = (len(all_cycles) / attempted * 100) if attempted else 0.0

    if not all_cycles:
        return {
            "num_cycles": 0,
            "skipped_symbols": skipped_symbols,
            "skipped_no_strike": skipped_no_strike_total,
            "skipped_no_quote": skipped_no_quote_total,
            "real_quote_coverage_pct": coverage_pct,
            "cycles": [],
        }

    pnls = [c.pnl_dollars for c in all_cycles]
    returns_on_collateral = [c.return_on_collateral_pct for c in all_cycles]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    return {
        "num_cycles": len(all_cycles),
        "num_symbols_simulated": len({c.symbol for c in all_cycles}),
        "skipped_symbols": skipped_symbols,
        "skipped_no_strike": skipped_no_strike_total,
        "skipped_no_quote": skipped_no_quote_total,
        "real_quote_coverage_pct": coverage_pct,
        "total_pnl_dollars": sum(pnls),
        "win_rate_pct": len(wins) / len(pnls) * 100,
        "avg_return_on_collateral_pct": statistics.mean(returns_on_collateral),
        "stdev_return_on_collateral_pct": (
            statistics.stdev(returns_on_collateral) if len(returns_on_collateral) > 1 else 0.0
        ),
        "avg_win_dollars": statistics.mean(wins) if wins else 0.0,
        "avg_loss_dollars": statistics.mean(losses) if losses else 0.0,
        "num_csp_cycles": sum(1 for c in all_cycles if c.cycle_type == "csp"),
        "num_covered_call_cycles": sum(1 for c in all_cycles if c.cycle_type == "covered_call"),
        "num_assignments": sum(1 for c in all_cycles if c.cycle_type == "csp" and c.assigned_or_called),
        "cycles": all_cycles,
    }


def save_results(results: dict[str, Any], start_date: date, end_date: date, dry_run: bool) -> int | None:
    if dry_run or results["num_cycles"] == 0:
        return None
    run_name = f"options_wheel_alpaca_real_{start_date}_{end_date}"
    try:
        with DatabaseContext("write") as cur:
            cur.execute(
                """
                INSERT INTO backtest_runs (
                    run_name, strategy_name, start_date, end_date,
                    initial_capital, final_value, total_return, annual_return,
                    max_drawdown, sharpe_ratio, win_rate, profit_factor,
                    num_trades, num_winning_trades, num_losing_trades,
                    avg_win, avg_loss, largest_win, largest_loss
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING run_id
                """,
                (
                    run_name,
                    # "_alpaca_real" suffix distinguishes this from run_id=2's
                    # "_synthetic_bs" strategy_name - never to be confused as the same evidence.
                    "options_csp_covered_call_wheel_alpaca_real",
                    start_date,
                    end_date,
                    0.0,
                    results["total_pnl_dollars"],
                    None,
                    None,
                    None,
                    None,
                    results["win_rate_pct"] / 100.0,
                    (
                        abs(results["avg_win_dollars"] / results["avg_loss_dollars"])
                        if results["avg_loss_dollars"]
                        else None
                    ),
                    results["num_cycles"],
                    sum(1 for c in results["cycles"] if c.pnl_dollars > 0),
                    sum(1 for c in results["cycles"] if c.pnl_dollars <= 0),
                    results["avg_win_dollars"],
                    results["avg_loss_dollars"],
                    max((c.pnl_dollars for c in results["cycles"]), default=None),
                    min((c.pnl_dollars for c in results["cycles"]), default=None),
                ),
            )
            row = cur.fetchone()
            if row is None or row[0] is None:
                raise RuntimeError("options real-data backtest run insert failed: no run_id returned")
            run_id = int(row[0])

        with DatabaseContext("write") as cur:
            for c in results["cycles"]:
                cur.execute(
                    """
                    INSERT INTO backtest_trades (
                        run_id, symbol, entry_date, exit_date,
                        entry_price, exit_price, quantity,
                        entry_value, exit_value,
                        profit_loss, profit_loss_percent,
                        trade_outcome, holding_days
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        run_id,
                        c.symbol,
                        c.entry_date,
                        c.exit_date,
                        round(c.premium_net / 100, 4),
                        round(c.strike, 4),
                        1,
                        round(c.premium_net, 2),
                        round(c.collateral, 2),
                        round(c.pnl_dollars, 2),
                        round(c.return_on_collateral_pct / 100, 4),
                        "win" if c.pnl_dollars > 0 else "loss",
                        (c.exit_date - c.entry_date).days,
                    ),
                )
        logger.info(f"[OPTIONS-BACKTEST-REAL] Saved to DB: run_id={run_id}, {results['num_cycles']} cycles written")
        return run_id
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        raise RuntimeError(f"Operation failed: {e}") from e


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--symbols", type=str, default=None, help="Comma-separated symbols (overrides --limit)")
    parser.add_argument("--limit", type=int, default=20, help="Universe size by liquidity (default 20)")
    parser.add_argument("--start-date", type=str, default=None, help="YYYY-MM-DD (default: 2024-02-05, data floor)")
    parser.add_argument("--end-date", type=str, default=None, help="YYYY-MM-DD (default: today)")
    parser.add_argument("--vrp-multiplier", type=float, default=DEFAULT_VRP_MULTIPLIER)
    parser.add_argument("--commission", type=float, default=DEFAULT_COMMISSION_PER_CONTRACT)
    parser.add_argument("--spread-haircut-pct", type=float, default=DEFAULT_SPREAD_HAIRCUT_PCT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    end_date = date.fromisoformat(args.end_date) if args.end_date else date.today()
    start_date = date.fromisoformat(args.start_date) if args.start_date else MIN_REAL_DATA_START
    symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else None

    results = run_options_backtest_real(
        symbols=symbols,
        limit=args.limit,
        start_date=start_date,
        end_date=end_date,
        vrp_multiplier=args.vrp_multiplier,
        commission=args.commission,
        spread_haircut_pct=args.spread_haircut_pct,
    )

    print(f"\n{'=' * 70}\nOPTIONS WHEEL BACKTEST (REAL Alpaca historical option quotes)\n{'=' * 70}")
    print(f"Period: {start_date} to {end_date}  (Alpaca options data floor: {MIN_REAL_DATA_START})")
    print(f"Symbols skipped (insufficient price history): {len(results.get('skipped_symbols', []))}")
    print(f"Cycles skipped (no valid delta-band strike): {results.get('skipped_no_strike', 0)}")
    print(f"Cycles skipped (no real quote found for contract): {results.get('skipped_no_quote', 0)}")
    print(f"Real-quote coverage: {results.get('real_quote_coverage_pct', 0.0):.1f}%")

    if results["num_cycles"] == 0:
        print("\nNo cycles simulated with real quotes - nothing to report.")
        return 1

    print(f"\nSymbols simulated: {results['num_symbols_simulated']}")
    print(
        f"Total cycles: {results['num_cycles']} (CSP: {results['num_csp_cycles']}, "
        f"covered call: {results['num_covered_call_cycles']})"
    )
    print(f"Assignments: {results['num_assignments']}")
    print(f"Total P&L: ${results['total_pnl_dollars']:,.2f}")
    print(f"Win rate: {results['win_rate_pct']:.1f}%")
    print(
        f"Avg return on collateral per cycle: {results['avg_return_on_collateral_pct']:.2f}% "
        f"(stdev {results['stdev_return_on_collateral_pct']:.2f}%)"
    )
    print(f"Avg win: ${results['avg_win_dollars']:,.2f}  Avg loss: ${results['avg_loss_dollars']:,.2f}")

    run_id = save_results(results, start_date, end_date, args.dry_run)
    if run_id:
        print(f"\nSaved as backtest_runs.run_id={run_id} (strategy_name=options_csp_covered_call_wheel_alpaca_real)")
    elif args.dry_run:
        print("\n--dry-run: not saved to DB")

    return 0


if __name__ == "__main__":
    sys.exit(main())
