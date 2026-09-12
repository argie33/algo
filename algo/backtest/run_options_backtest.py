#!/usr/bin/env python3
"""Backtest: CSP + covered-call wheel strategy (options-strategy plan phase 3).

Written against `steering/OPTIONS_STRATEGY_SPEC.md` (phase 2) - this is the "positive net
edge after realistic costs" check that spec's go/no-go gate §7.1 requires before any
execution code (phase 5+) can be written.

**CRITICAL DATA LIMITATION - read before trusting any number this script prints.**
`options_chains`/`iv_history` (the real vendor-quoted options data phase 1 wired a daily
loader for) only started accumulating today (2026-09-12, ~25 symbols/day rotating sample) -
there is no historical options-chain or implied-vol history in this database to replay, and
there will not be meaningful depth for years at the current sample rate. A real "replay actual
historical vendor quotes" backtest is not possible with what this system has. This script
instead prices every hypothetical option with Black-Scholes (`utils/options/black_scholes.py`)
using **trailing realized volatility of the underlying, scaled by an explicit volatility-risk-
premium multiplier, as a synthetic proxy for implied volatility** - this is a common technique
for backtesting options strategies without a historical IV surface, but it is a PROXY, not
observed market data. It cannot capture volatility skew/smile, event-driven IV spikes (the
real reason elevated-IV-rank premium exists), or actual historical bid/ask spreads. A result
from this script is evidence about whether the MECHANICAL construction (delta band, DTE,
assignment/roll rules) has a plausible edge over cash - it is NOT the same evidence a real
historical-quote backtest would produce, and should not be the sole basis for a live go/no-go
decision. Treat a clean result here as "worth the cost of getting real historical options data
to confirm," not as confirmation itself.

**v1 SCOPE, explicit** (mirrors run_backtest.py's own phased fixed/live_trail precedent -
ship the simpler mode first, document what it doesn't cover, add complexity once the simpler
result justifies it): settlement is EXPIRATION-ONLY. The spec's §5 early-close-at-50%-profit,
DTE<=7 roll, and >15%-underlying-drop stop rules are NOT simulated here - v1 only answers
"does selling 0.15-0.30 delta puts/calls at 30-45 DTE on this universe, held to expiration,
generate positive edge net of assignment risk and costs" using the synthetic-IV pricing above.
Those three rules are all risk-management refinements that improve Sharpe/reduce tail risk,
not the core edge sign - the right next increment once THIS result justifies more engineering
effort, not before.

**Eligibility scope gap, also explicit**: `stock_scores` has no historical date dimension (see
run_backtest.py's own docstring for the identical, older gap) - this backtest cannot apply the
spec's §2 composite-score eligibility filter without look-ahead bias, so it does not attempt
to; it filters only on what IS computable historically (price, liquidity, sector). Real
options-chain open-interest/volume liquidity (spec §2) also isn't available historically, so
liquidity uses a price_daily dollar-volume proxy instead.

Universe/underlying selection, sizing, pricing assumptions (commission, spread haircut, VRP
multiplier) are all explicit CLI flags with documented defaults below - none are hidden.

Usage:
    python -m algo.backtest.run_options_backtest --limit 30 --start-date 2022-01-01
    python -m algo.backtest.run_options_backtest --symbols AAPL,MSFT,KO --dry-run
"""

from __future__ import annotations

import argparse
import logging
import statistics
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import pandas as pd
import psycopg2

from utils.db.context import DatabaseContext
from utils.options.black_scholes import call_delta, call_price, put_delta, put_price

logger = logging.getLogger(__name__)

TRADING_DAYS_PER_YEAR = 252
DELTA_LOW = 0.15
DELTA_HIGH = 0.30
DELTA_TARGET = 0.225  # midpoint of the band - matches OPTIONS_STRATEGY_SPEC.md §3
TARGET_DTE_DAYS = 37  # midpoint of the spec's 30-45 DTE window
VOL_WINDOW_DAYS = 20  # trailing realized-vol window, same convention as iv_rank_signal's peers
MIN_HISTORY_DAYS = VOL_WINDOW_DAYS + 5

# Explicit, documented assumption (NOT calibrated to this account's real execution history -
# same "visible estimate, not silent zero-cost" posture as run_backtest.py's
# DEFAULT_SLIPPAGE_BPS). Realized vol is a lower-bound proxy for IV in most regimes (options
# markets typically price in a premium over subsequently-realized vol); 1.15x is a
# deliberately conservative multiplier - understating the synthetic premium understates this
# script's own edge estimate, which is the safer direction to be wrong in for a go/no-go check.
DEFAULT_VRP_MULTIPLIER = 1.15
DEFAULT_COMMISSION_PER_CONTRACT = 0.65
# Bid/ask haircut on the theoretical mid price - real OTM equity-option spreads on liquid
# names commonly run a few percent of premium; treated as an explicit assumption, not
# calibrated to real fills (no real options fills exist in this system yet).
DEFAULT_SPREAD_HAIRCUT_PCT = 3.0
DEFAULT_RISK_FREE_RATE = 0.045  # matches options_data_loader.py's own documented fallback


@dataclass
class CycleResult:
    symbol: str
    cycle_type: str  # "csp" or "covered_call"
    entry_date: date
    exit_date: date
    strike: float
    spot_entry: float
    spot_exit: float
    iv_used: float
    premium_net: float
    collateral: float
    assigned_or_called: bool
    pnl_dollars: float
    return_on_collateral_pct: float


@dataclass
class SymbolSimResult:
    symbol: str
    cycles: list[CycleResult] = field(default_factory=list)
    skipped_cycles: int = 0


def _risk_free_rate_asof(cur: Any, as_of: date) -> float:
    try:
        cur.execute(
            "SELECT value::float FROM economic_data WHERE series_id = 'DGS3MO' "
            "AND date <= %s AND value IS NOT NULL ORDER BY date DESC LIMIT 1",
            (as_of,),
        )
        row = cur.fetchone()
        if row is not None and row[0] is not None:
            return float(row[0]) / 100.0
    except (psycopg2.DatabaseError, psycopg2.OperationalError):
        pass
    return DEFAULT_RISK_FREE_RATE


def _select_universe(cur: Any, limit: int) -> list[dict[str, Any]]:
    """Liquid names by trailing 60-day avg dollar volume, joined to sector. No historical
    composite_score/options-liquidity filter applied - see module docstring."""
    cur.execute(
        """
        WITH recent AS (
            SELECT symbol, close, volume
            FROM price_daily
            WHERE date >= CURRENT_DATE - INTERVAL '90 days'
                  AND close IS NOT NULL AND volume IS NOT NULL AND close > 5
        ),
        ranked AS (
            SELECT symbol, AVG(close * volume) AS avg_dollar_volume
            FROM recent
            GROUP BY symbol
            HAVING COUNT(*) >= 40
        )
        SELECT r.symbol, COALESCE(cp.sector, 'Unknown') AS sector
        FROM ranked r
        LEFT JOIN company_profile cp ON cp.symbol = r.symbol
        ORDER BY r.avg_dollar_volume DESC
        LIMIT %s
        """,
        (limit,),
    )
    return [{"symbol": row[0], "sector": row[1]} for row in cur.fetchall()]


def _load_price_series(cur: Any, symbol: str, start: date, end: date) -> pd.DataFrame | None:
    cur.execute(
        """
        SELECT date, adj_close FROM price_daily
        WHERE symbol = %s AND date <= %s AND adj_close IS NOT NULL AND adj_close > 0
        ORDER BY date
        """,
        (symbol, end),
    )
    rows = cur.fetchall()
    if len(rows) < MIN_HISTORY_DAYS:
        return None
    df = pd.DataFrame(rows, columns=["date", "price"])
    df["price"] = df["price"].astype(float)
    df["log_return"] = df["price"].apply(lambda x: x).pipe(lambda s: (s / s.shift(1)).apply(_safe_log))
    df["realized_vol"] = df["log_return"].rolling(VOL_WINDOW_DAYS).std() * (TRADING_DAYS_PER_YEAR**0.5)
    return df


def _safe_log(ratio: float) -> float:
    import math

    if ratio is None or ratio <= 0:
        return float("nan")
    return math.log(ratio)


def _find_strike_by_delta(
    spot: float,
    time_to_expiry_years: float,
    r: float,
    iv: float,
    is_put: bool,
    min_strike: float | None = None,
) -> tuple[float, float] | None:
    """Scan strikes in 1% increments of spot, return (strike, delta) closest to DELTA_TARGET
    within [DELTA_LOW, DELTA_HIGH], honoring min_strike (covered-call cost-basis floor)."""
    best: tuple[float, float] | None = None
    best_dist = float("inf")
    if is_put:
        strike_range = [spot * (1 - pct / 100) for pct in range(1, 41)]  # 1%..40% OTM
    else:
        strike_range = [spot * (1 + pct / 100) for pct in range(1, 41)]

    for strike in strike_range:
        if strike <= 0:
            continue
        if min_strike is not None and strike < min_strike:
            continue
        try:
            d = (
                put_delta(spot, strike, time_to_expiry_years, r, iv)
                if is_put
                else call_delta(spot, strike, time_to_expiry_years, r, iv)
            )
        except ValueError:
            continue
        abs_d = abs(d)
        if DELTA_LOW <= abs_d <= DELTA_HIGH:
            dist = abs(abs_d - DELTA_TARGET)
            if dist < best_dist:
                best_dist = dist
                best = (strike, d)
    return best


def _nearest_row_on_or_after(df: pd.DataFrame, target_date: date) -> pd.Series | None:
    candidates = df[df["date"] >= target_date]
    if candidates.empty:
        return None
    return candidates.iloc[0]


def _simulate_symbol_wheel(
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
    current_date = start_date

    for _ in range(max_cycles):
        entry_row = _nearest_row_on_or_after(df, current_date)
        if entry_row is None:
            break
        entry_date = entry_row["date"]
        target_exit = entry_date + timedelta(days=TARGET_DTE_DAYS)
        if target_exit > end_date:
            break
        exit_row = _nearest_row_on_or_after(df, target_exit)
        if exit_row is None:
            break
        exit_date = exit_row["date"]

        realized_vol = entry_row["realized_vol"]
        if realized_vol is None or pd.isna(realized_vol) or realized_vol <= 0:
            current_date = entry_date + timedelta(days=TARGET_DTE_DAYS)
            result.skipped_cycles += 1
            continue
        iv = float(realized_vol) * vrp_multiplier
        spot_entry = float(entry_row["price"])
        spot_exit = float(exit_row["price"])
        time_to_expiry = max((exit_date - entry_date).days, 1) / 365.0
        r = _risk_free_rate_asof(cur, entry_date)

        if phase == "csp":
            found = _find_strike_by_delta(spot_entry, time_to_expiry, r, iv, is_put=True)
            if found is None:
                current_date = entry_date + timedelta(days=TARGET_DTE_DAYS)
                result.skipped_cycles += 1
                continue
            strike, _delta_at_entry = found
            try:
                premium_mid = put_price(spot_entry, strike, time_to_expiry, r, iv)
            except ValueError:
                current_date = entry_date + timedelta(days=TARGET_DTE_DAYS)
                result.skipped_cycles += 1
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
                CycleResult(
                    symbol=symbol,
                    cycle_type="csp",
                    entry_date=entry_date,
                    exit_date=exit_date,
                    strike=strike,
                    spot_entry=spot_entry,
                    spot_exit=spot_exit,
                    iv_used=iv,
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
                # No delta-band strike clears the cost-basis floor - fall back to the lowest
                # available strike at/above cost basis regardless of delta (documented in
                # module docstring's covered-call fallback note).
                fallback_strike = max(cost_basis, spot_entry * 1.01)
                try:
                    fallback_delta = call_delta(spot_entry, fallback_strike, time_to_expiry, r, iv)
                except ValueError:
                    current_date = entry_date + timedelta(days=TARGET_DTE_DAYS)
                    result.skipped_cycles += 1
                    continue
                found = (fallback_strike, fallback_delta)
            strike, _ = found
            try:
                premium_mid = call_price(spot_entry, strike, time_to_expiry, r, iv)
            except ValueError:
                current_date = entry_date + timedelta(days=TARGET_DTE_DAYS)
                result.skipped_cycles += 1
                continue
            premium_net = premium_mid * 100 * (1 - spread_haircut_pct / 100) - commission
            collateral = cost_basis * 100
            called_away = spot_exit >= strike
            if called_away:
                pnl_dollars = premium_net + (strike - cost_basis) * 100
            else:
                pnl_dollars = premium_net  # unrealized share P&L not counted in this cycle
            result.cycles.append(
                CycleResult(
                    symbol=symbol,
                    cycle_type="covered_call",
                    entry_date=entry_date,
                    exit_date=exit_date,
                    strike=strike,
                    spot_entry=spot_entry,
                    spot_exit=spot_exit,
                    iv_used=iv,
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

        current_date = exit_date + timedelta(days=1)

    return result


def run_options_backtest(
    symbols: list[str] | None,
    limit: int,
    start_date: date,
    end_date: date,
    vrp_multiplier: float = DEFAULT_VRP_MULTIPLIER,
    commission: float = DEFAULT_COMMISSION_PER_CONTRACT,
    spread_haircut_pct: float = DEFAULT_SPREAD_HAIRCUT_PCT,
    max_cycles_per_symbol: int = 200,
) -> dict[str, Any]:
    with DatabaseContext("read") as cur:
        universe = [{"symbol": s, "sector": "Unknown"} for s in symbols] if symbols else _select_universe(cur, limit)

        all_cycles: list[CycleResult] = []
        skipped_symbols: list[str] = []
        skipped_cycles_total = 0

        for entry in universe:
            symbol = entry["symbol"]
            df = _load_price_series(cur, symbol, start_date, end_date)
            if df is None:
                skipped_symbols.append(symbol)
                continue
            sim = _simulate_symbol_wheel(
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
            skipped_cycles_total += sim.skipped_cycles

    if not all_cycles:
        return {
            "num_cycles": 0,
            "skipped_symbols": skipped_symbols,
            "skipped_cycles": skipped_cycles_total,
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
        "skipped_cycles": skipped_cycles_total,
        "total_pnl_dollars": sum(pnls),
        "win_rate_pct": len(wins) / len(pnls) * 100,
        "avg_return_on_collateral_pct": statistics.mean(returns_on_collateral),
        "stdev_return_on_collateral_pct": (
            statistics.stdev(returns_on_collateral) if len(returns_on_collateral) > 1 else 0.0
        ),
        "avg_win_dollars": statistics.mean(wins) if wins else 0.0,
        "avg_loss_dollars": statistics.mean(losses) if losses else 0.0,
        "avg_iv_used_pct": statistics.mean(c.iv_used for c in all_cycles) * 100,
        "num_csp_cycles": sum(1 for c in all_cycles if c.cycle_type == "csp"),
        "num_covered_call_cycles": sum(1 for c in all_cycles if c.cycle_type == "covered_call"),
        "num_assignments": sum(1 for c in all_cycles if c.cycle_type == "csp" and c.assigned_or_called),
        "cycles": all_cycles,
    }


def save_results(results: dict[str, Any], start_date: date, end_date: date, dry_run: bool) -> int | None:
    if dry_run or results["num_cycles"] == 0:
        return None

    run_name = f"options_wheel_synthetic_bs_{start_date}_{end_date}"
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
                    "options_csp_covered_call_wheel_synthetic_bs",
                    start_date,
                    end_date,
                    # initial_capital/final_value are NOT NULL but don't have real meaning for
                    # this per-symbol/per-cycle collateral-return backtest (no portfolio-level
                    # capital tracking here - see module docstring). Stored as 0/total_pnl
                    # rather than a fabricated "capital allocated" figure; the meaningful
                    # numbers for this run type are avg_return_on_collateral_pct/win_rate,
                    # not these two columns.
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
                raise RuntimeError("options backtest run insert failed: no run_id returned")
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
                        round(c.premium_net / 100, 4),  # premium received per share
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
        logger.info(f"[OPTIONS-BACKTEST] Saved to DB: run_id={run_id}, {results['num_cycles']} cycles written")
        return run_id
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        raise RuntimeError(f"Operation failed: {e}") from e


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--symbols", type=str, default=None, help="Comma-separated symbols (overrides --limit)")
    parser.add_argument("--limit", type=int, default=30, help="Universe size by liquidity (default 30)")
    parser.add_argument("--start-date", type=str, default=None, help="YYYY-MM-DD (default: 2 years ago)")
    parser.add_argument("--end-date", type=str, default=None, help="YYYY-MM-DD (default: today)")
    parser.add_argument("--vrp-multiplier", type=float, default=DEFAULT_VRP_MULTIPLIER)
    parser.add_argument("--commission", type=float, default=DEFAULT_COMMISSION_PER_CONTRACT)
    parser.add_argument("--spread-haircut-pct", type=float, default=DEFAULT_SPREAD_HAIRCUT_PCT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    end_date = date.fromisoformat(args.end_date) if args.end_date else date.today()
    start_date = date.fromisoformat(args.start_date) if args.start_date else end_date - timedelta(days=730)
    symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else None

    results = run_options_backtest(
        symbols=symbols,
        limit=args.limit,
        start_date=start_date,
        end_date=end_date,
        vrp_multiplier=args.vrp_multiplier,
        commission=args.commission,
        spread_haircut_pct=args.spread_haircut_pct,
    )

    print(f"\n{'=' * 70}\nOPTIONS WHEEL BACKTEST (synthetic Black-Scholes IV proxy - see module docstring)\n{'=' * 70}")
    print(f"Period: {start_date} to {end_date}")
    print(f"Symbols skipped (insufficient history): {len(results.get('skipped_symbols', []))}")
    print(f"Cycles skipped (no valid delta-band strike found): {results.get('skipped_cycles', 0)}")

    if results["num_cycles"] == 0:
        print("\nNo cycles simulated - nothing to report.")
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
    print(f"Avg synthetic IV used (realized vol x VRP multiplier): {results['avg_iv_used_pct']:.1f}%")

    run_id = save_results(results, start_date, end_date, args.dry_run)
    if run_id:
        print(f"\nSaved as backtest_runs.run_id={run_id}")
    elif args.dry_run:
        print("\n--dry-run: not saved to DB")

    return 0


if __name__ == "__main__":
    sys.exit(main())
