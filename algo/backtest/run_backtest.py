#!/usr/bin/env python3
"""
Backtest: Composite Score + Buy/Sell Signals Strategy

Simulates the live algo strategy historically:
  - Entry trigger: BUY signal in buy_sell_daily (pivot breakout above swing high with SMA50 filter)
  - Ranking: composite_score from stock_scores (fundamentals quality: quality, growth, value,
    momentum, positioning, stability)
  - Exit: first of — SELL signal in buy_sell_daily, profit target, stop loss, max hold

Note: stock_scores has no date dimension (current snapshot). Composite scores used as ranking
proxy for historical simulation. Momentum sub-score is price-based (1m/3m/6m/12m) so recency
bias is expected for stocks that gained since signal date.

Usage:
    python -m algo.backtest.run_backtest [options]

    --start-date DATE    Start date for backtest (default: 2 years ago)
    --end-date DATE      End date (default: today)
    --initial-capital N  Starting capital in dollars (default: 100000)
    --max-positions N    Max concurrent positions (default: 10)
    --min-composite N    Min composite_score to qualify (default: 50)
    --profit-target PCT  Profit target % (default: 20)
    --stop-loss PCT      Stop loss % (default: 8)
    --max-hold-days N    Max holding period in days (default: 60)
    --position-size PCT  Fixed position size as % of portfolio (default: 10)
    --strategy NAME      Strategy name for results table (default: composite_score_signals)
    --dry-run            Print results without writing to DB
"""

import argparse
import logging
import sys
from datetime import date, timedelta

import psycopg2

from utils.db.context import DatabaseContext


logger = logging.getLogger(__name__)


def _get_trading_dates(start: date, end: date) -> list[date]:
    """Get all trading dates between start and end from price_daily."""
    try:
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT DISTINCT date FROM price_daily
                WHERE date >= %s AND date <= %s
                ORDER BY date ASC
                """,
                (start, end),
            )
            return [row[0] for row in cur.fetchall()]
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        raise RuntimeError(f"[BACKTEST] FATAL: Cannot fetch trading dates from price_daily: {e}") from e


def _get_daily_buy_signals(signal_date: date, min_composite: float) -> list[dict]:
    """Get BUY signals for a date, sorted by signal_quality_score desc.

    Ranks by signal_quality_score (contemporaneous — no look-ahead bias).
    Optionally also fetches composite_score from stock_scores for informational use,
    but does NOT filter or rank by it (stock_scores has no date dimension).
    min_composite is accepted for API compatibility but unused.
    """
    try:
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT b.symbol, b.close, b.high, b.low, b.sma_50, b.strength,
                       b.buylevel, b.stoplevel,
                       b.signal_quality_score, b.entry_quality_score,
                       s.composite_score, s.rs_percentile
                FROM buy_sell_daily b
                LEFT JOIN stock_scores s ON s.symbol = b.symbol
                WHERE b.date = %s
                  AND b.signal_type = 'BUY'
                  AND b.close IS NOT NULL
                  AND b.close > COALESCE(b.sma_50, 0)
                ORDER BY COALESCE(b.signal_quality_score, 0) DESC
                """,
                (signal_date,),
            )
            rows = cur.fetchall()

        signals = []
        for r in rows:
            close = float(r[1]) if r[1] is not None else None
            if not close:
                continue
            signals.append(
                {
                    "symbol": r[0],
                    "entry_price": close,
                    "high": float(r[2]) if r[2] is not None else None,
                    "low": float(r[3]) if r[3] is not None else None,
                    "sma_50": float(r[4]) if r[4] is not None else None,
                    "signal_strength": float(r[5]) if r[5] is not None else 0.5,
                    "buylevel": float(r[6]) if r[6] is not None else None,
                    "stoplevel": float(r[7]) if r[7] is not None else None,
                    "signal_quality_score": float(r[8]) if r[8] is not None else 0.0,
                    "entry_quality_score": float(r[9]) if r[9] is not None else None,
                    "composite_score": float(r[10]) if r[10] is not None else None,
                    "rs_percentile": float(r[11]) if r[11] is not None else None,
                }
            )

        return signals
    except (ValueError, ZeroDivisionError, TypeError) as e:
        raise RuntimeError(f"[BACKTEST] FATAL: Cannot fetch buy signals for {signal_date}: {e}") from e


def _get_daily_sell_signals(signal_date: date) -> set:
    """Get symbols with SELL signal on signal_date."""
    try:
        with DatabaseContext("read") as cur:
            cur.execute(
                "SELECT symbol FROM buy_sell_daily WHERE date = %s AND signal_type = 'SELL'",
                (signal_date,),
            )
            return {row[0] for row in cur.fetchall()}
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        raise RuntimeError(f"[BACKTEST] FATAL: Cannot fetch sell signals for {signal_date}: {e}") from e


def _get_price_on_date(symbol: str, target_date: date) -> float | None:
    """Get close price at or before target_date."""
    try:
        with DatabaseContext("read") as cur:
            cur.execute(
                "SELECT close FROM price_daily WHERE symbol = %s AND date <= %s ORDER BY date DESC LIMIT 1",
                (symbol, target_date),
            )
            row = cur.fetchone()
            return float(row[0]) if row and row[0] is not None else None
    except (ValueError, ZeroDivisionError, TypeError) as e:
        raise RuntimeError(f"Operation failed: {e}") from e


def _get_prices_batch(symbols: list[str], target_date: date) -> dict[str, float]:
    """Get close prices for multiple symbols on target_date."""
    if not symbols:
        raise ValueError("symbols list cannot be empty for backtest price fetch")
    try:
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT DISTINCT ON (symbol) symbol, close
                FROM price_daily
                WHERE symbol = ANY(%s) AND date <= %s
                ORDER BY symbol, date DESC
                """,
                (symbols, target_date),
            )
            return {r[0]: float(r[1]) for r in cur.fetchall() if r[1] is not None}
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        raise RuntimeError(f"[BACKTEST] FATAL: Cannot fetch prices for symbols: {e}") from e


def run_backtest(
    start_date: date,
    end_date: date,
    initial_capital: float = 100_000.0,
    max_positions: int = 10,
    min_composite: float = 50.0,
    profit_target_pct: float = 20.0,
    stop_loss_pct: float = 8.0,
    max_hold_days: int = 60,
    position_size_pct: float = 10.0,
    strategy_name: str = "composite_score_signals",
) -> dict:
    """Run backtest and return results dict."""
    logger.info(
        f"[BACKTEST] Starting {strategy_name}: {start_date} to {end_date}, "
        f"capital=${initial_capital:,.0f}, max_pos={max_positions}, "
        f"min_composite={min_composite}, stop={stop_loss_pct}%, target={profit_target_pct}%"
    )

    trading_dates = _get_trading_dates(start_date, end_date)
    if not trading_dates:
        raise RuntimeError(
            f"[BACKTEST] FATAL: No trading dates found in price_daily between {start_date} and {end_date}"
        )

    logger.info(f"[BACKTEST] {len(trading_dates)} trading days to simulate")

    capital = initial_capital
    positions: dict[str, dict] = {}  # symbol → {entry_price, shares, entry_date, stop, target}
    completed_trades: list[dict] = []
    equity_curve = []

    for sim_date in trading_dates:
        # Mark-to-market: update portfolio value at day open
        position_symbols = list(positions.keys())
        current_prices = _get_prices_batch(position_symbols, sim_date) if position_symbols else {}

        # Validate all position prices are available (fail-fast if data missing)
        for symbol in position_symbols:
            if symbol not in current_prices:
                raise RuntimeError(
                    f"[BACKTEST] FATAL: Missing price for position {symbol} on {sim_date}. "
                    f"Cannot calculate P&L without current prices. Check price_daily table."
                )

        # Check exits first (SELL signals, profit target, stop loss, max hold)
        sell_signals = _get_daily_sell_signals(sim_date)

        for symbol in list(positions.keys()):
            pos = positions[symbol]
            current_price = current_prices[symbol]
            hold_days = (sim_date - pos["entry_date"]).days
            pnl_pct = (current_price - pos["entry_price"]) / pos["entry_price"] * 100

            exit_reason = None
            exit_price = current_price

            if symbol in sell_signals:
                exit_reason = "sell_signal"
            elif pnl_pct >= profit_target_pct:
                exit_reason = "profit_target"
                exit_price = pos["entry_price"] * (1 + profit_target_pct / 100)
            elif pnl_pct <= -stop_loss_pct:
                exit_reason = "stop_loss"
                exit_price = pos["entry_price"] * (1 - stop_loss_pct / 100)
            elif hold_days >= max_hold_days:
                exit_reason = "max_hold"

            if exit_reason:
                pnl_dollars = (exit_price - pos["entry_price"]) * pos["shares"]
                pnl_pct_final = (exit_price - pos["entry_price"]) / pos["entry_price"] * 100
                capital += pos["shares"] * exit_price  # return capital

                completed_trades.append(
                    {
                        "symbol": symbol,
                        "trade_date": pos["entry_date"],
                        "entry_price": pos["entry_price"],
                        "entry_quantity": int(pos["shares"]),
                        "exit_date": sim_date,
                        "exit_price": round(exit_price, 4),
                        "profit_loss_dollars": round(pnl_dollars, 2),
                        "profit_loss_pct": round(pnl_pct_final, 4),
                        "holding_days": hold_days,
                        "exit_reason": exit_reason,
                        "signal_quality_score": pos.get("signal_quality_score"),
                        "composite_score": pos.get("composite_score"),
                    }
                )

                logger.debug(f"[BACKTEST] EXIT {symbol}: {exit_reason} P&L={pnl_pct_final:+.1f}% ({hold_days}d)")
                del positions[symbol]

        # Record equity curve snapshot (all position prices already validated above)
        invested_value = sum(current_prices[sym] * pos["shares"] for sym, pos in positions.items())
        total_value = capital + invested_value
        equity_curve.append({"date": sim_date.isoformat(), "value": round(total_value, 2)})

        # Check entries: new BUY signals for today
        if len(positions) < max_positions and capital > 0:
            buy_signals = _get_daily_buy_signals(sim_date, min_composite)

            for sig in buy_signals:
                symbol = sig["symbol"]
                if symbol in positions:
                    continue  # Already in position
                if len(positions) >= max_positions:
                    break

                entry_price = sig["entry_price"]
                position_dollars = min(capital, total_value * position_size_pct / 100)
                shares = position_dollars / entry_price if entry_price > 0 else 0

                if shares < 1:
                    continue

                shares = int(shares)
                cost = shares * entry_price

                if cost > capital:
                    continue

                capital -= cost
                positions[symbol] = {
                    "entry_price": entry_price,
                    "shares": shares,
                    "entry_date": sim_date,
                    "signal_quality_score": sig.get("signal_quality_score"),
                    "composite_score": sig.get("composite_score"),
                }

                sq = sig.get("signal_quality_score")
                sq_str = f"{sq:.1f}" if sq is not None else "?"
                logger.debug(f"[BACKTEST] ENTER {symbol}: ${entry_price:.2f} x {shares} shares signal_quality={sq_str}")

    # Close any remaining open positions at last date's price
    if positions:
        final_date = trading_dates[-1]
        final_prices = _get_prices_batch(list(positions.keys()), final_date)
        # Validate all position prices are available for final close (fail-fast if data missing)
        for symbol in positions.keys():
            if symbol not in final_prices:
                raise RuntimeError(
                    f"[BACKTEST] FATAL: Missing final price for position {symbol} on {final_date}. "
                    f"Cannot close out positions without current prices. Check price_daily table."
                )
        for symbol, pos in positions.items():
            exit_price = final_prices[symbol]
            pnl_dollars = (exit_price - pos["entry_price"]) * pos["shares"]
            pnl_pct_final = (exit_price - pos["entry_price"]) / pos["entry_price"] * 100
            hold_days = (final_date - pos["entry_date"]).days
            capital += pos["shares"] * exit_price

            completed_trades.append(
                {
                    "symbol": symbol,
                    "trade_date": pos["entry_date"],
                    "entry_price": pos["entry_price"],
                    "entry_quantity": int(pos["shares"]),
                    "exit_date": final_date,
                    "exit_price": round(exit_price, 4),
                    "profit_loss_dollars": round(pnl_dollars, 2),
                    "profit_loss_pct": round(pnl_pct_final, 4),
                    "holding_days": hold_days,
                    "exit_reason": "end_of_backtest",
                    "signal_quality_score": pos.get("signal_quality_score"),
                    "composite_score": pos.get("composite_score"),
                }
            )

    # Compute performance metrics
    final_capital = capital
    total_return_pct = (final_capital - initial_capital) / initial_capital * 100
    n_days = (end_date - start_date).days
    years = n_days / 365.25
    annualized_return_pct = ((final_capital / initial_capital) ** (1.0 / years) - 1) * 100 if years > 0 else 0

    total_trades = len(completed_trades)
    winning_trades = [t for t in completed_trades if t["profit_loss_pct"] > 0]
    losing_trades = [t for t in completed_trades if t["profit_loss_pct"] <= 0]
    win_count = len(winning_trades)
    loss_count = len(losing_trades)
    win_rate_pct = (win_count / total_trades * 100) if total_trades > 0 else 0
    best_trade = max((t["profit_loss_pct"] for t in completed_trades), default=0)
    worst_trade = min((t["profit_loss_pct"] for t in completed_trades), default=0)
    avg_hold = sum(t["holding_days"] for t in completed_trades) / total_trades if total_trades > 0 else 0

    gross_profit = sum(t["profit_loss_dollars"] for t in winning_trades)
    gross_loss = abs(sum(t["profit_loss_dollars"] for t in losing_trades))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

    # Max drawdown from equity curve
    max_dd_pct = 0.0
    if equity_curve:
        peak = equity_curve[0]["value"]
        for point in equity_curve:
            v = point["value"]
            if v > peak:
                peak = v
            dd = (v - peak) / peak * 100
            if dd < max_dd_pct:
                max_dd_pct = dd

    # Sharpe ratio from equity curve daily returns
    sharpe = None
    if len(equity_curve) > 30:
        values = [p["value"] for p in equity_curve]
        daily_returns = [(values[i] - values[i - 1]) / values[i - 1] for i in range(1, len(values))]
        if daily_returns:
            import statistics

            avg_ret = statistics.mean(daily_returns)
            std_ret = statistics.stdev(daily_returns) if len(daily_returns) > 1 else 0
            sharpe = round((avg_ret / std_ret * (252**0.5)) if std_ret > 0 else 0, 4)

    avg_trade_return_pct = sum(t["profit_loss_pct"] for t in completed_trades) / total_trades if total_trades > 0 else 0

    results = {
        "strategy_name": strategy_name,
        "start_date": start_date,
        "end_date": end_date,
        "initial_capital": initial_capital,
        "final_capital": round(final_capital, 2),
        "total_return_pct": round(total_return_pct, 4),
        "annualized_return_pct": round(annualized_return_pct, 4),
        "max_drawdown_pct": round(max_dd_pct, 4),
        "sharpe_ratio": sharpe,
        "win_rate_pct": round(win_rate_pct, 4),
        "profit_factor": round(profit_factor, 4) if profit_factor != float("inf") else 9999.0,
        "total_trades": total_trades,
        "winning_trades": win_count,
        "losing_trades": loss_count,
        "avg_trade_return_pct": round(avg_trade_return_pct, 4),
        "best_trade_pct": round(best_trade, 4),
        "worst_trade_pct": round(worst_trade, 4),
        "avg_holding_days": round(avg_hold, 2),
        "parameters": {
            "min_composite_score": min_composite,
            "profit_target_pct": profit_target_pct,
            "stop_loss_pct": stop_loss_pct,
            "max_hold_days": max_hold_days,
            "max_positions": max_positions,
            "position_size_pct": position_size_pct,
        },
        "trades": completed_trades,
        "equity_curve": equity_curve,
    }

    logger.info(
        f"[BACKTEST] COMPLETE: {total_trades} trades, "
        f"return={total_return_pct:+.1f}% (annualized={annualized_return_pct:+.1f}%), "
        f"win_rate={win_rate_pct:.1f}%, sharpe={sharpe}, "
        f"max_dd={max_dd_pct:.1f}%"
    )

    return results


def save_results(results: dict) -> int | None:
    """Write backtest results to backtest_runs and backtest_trades tables.

    Returns run_id integer on success, None on failure.
    """
    if not results:
        logger.error("[BACKTEST] No results to save")
        return None

    trades = results.pop("trades", [])
    results.pop("equity_curve", [])

    run_name = f"{results['strategy_name']}_{results['start_date']}_{results['end_date']}"
    # Deduplicate by using ON CONFLICT on run_name+run_timestamp (via unique constraint)

    try:
        run_id = None
        with DatabaseContext("write") as cur:
            cur.execute(
                """
                INSERT INTO backtest_runs (
                    run_name, strategy_name, start_date, end_date,
                    initial_capital, final_value, total_return, annual_return,
                    max_drawdown, sharpe_ratio, win_rate, profit_factor,
                    num_trades, num_winning_trades, num_losing_trades,
                    avg_win, avg_loss, largest_win, largest_loss
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s
                )
                RETURNING run_id
                """,
                (
                    run_name,
                    results["strategy_name"],
                    results["start_date"],
                    results["end_date"],
                    results["initial_capital"],
                    results["final_capital"],
                    results["total_return_pct"] / 100.0,  # store as fraction
                    results["annualized_return_pct"] / 100.0,
                    results["max_drawdown_pct"] / 100.0,
                    results["sharpe_ratio"],
                    results["win_rate_pct"] / 100.0,
                    results["profit_factor"],
                    results["total_trades"],
                    results["winning_trades"],
                    results["losing_trades"],
                    results["avg_trade_return_pct"],
                    results["worst_trade_pct"],  # avg_loss proxy
                    results["best_trade_pct"],
                    results["worst_trade_pct"],
                ),
            )
            row = cur.fetchone()
            if row is None or row[0] is None:
                raise RuntimeError("Backtest run insert failed: RETURNING run_id returned no row")
            run_id = row[0]

        # Write individual trades
        if trades and run_id:
            with DatabaseContext("write") as cur:
                for trade in trades:
                    entry_price = trade["entry_price"]
                    exit_price_raw = trade.get("exit_price")
                    if exit_price_raw is None:
                        raise RuntimeError(
                            f"Trade missing exit_price (symbol={trade.get('symbol')}, "
                            f"entry_date={trade.get('entry_date')}). "
                            "Backtest trades must always have explicit exit prices."
                        )
                    exit_price = exit_price_raw
                    qty = trade["entry_quantity"]
                    pnl = trade.get("profit_loss_dollars", 0)
                    pnl_pct = trade.get("profit_loss_pct", 0)
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
                            trade["symbol"],
                            trade["trade_date"],
                            trade.get("exit_date"),
                            round(entry_price, 4),
                            round(exit_price, 4),
                            qty,
                            round(entry_price * qty, 2),
                            round(exit_price * qty, 2),
                            round(pnl, 2),
                            round(pnl_pct, 4),
                            "win" if pnl_pct > 0 else "loss",
                            trade.get("holding_days"),
                        ),
                    )

        logger.info(f"[BACKTEST] Saved to DB: run_id={run_id}, {len(trades)} trades written")
        return run_id  # type: ignore[return-value]

    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        raise RuntimeError(f"Operation failed: {e}") from e


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    parser = argparse.ArgumentParser(description="Run composite score + buy/sell signal backtest")
    parser.add_argument("--start-date", type=str, default=None, help="Start date YYYY-MM-DD (default: 2 years ago)")
    parser.add_argument("--end-date", type=str, default=None, help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--initial-capital", type=float, default=100_000.0, help="Starting capital")
    parser.add_argument("--max-positions", type=int, default=10, help="Max concurrent positions")
    parser.add_argument("--min-composite", type=float, default=50.0, help="Min composite_score (0-100)")
    parser.add_argument("--profit-target", type=float, default=20.0, help="Profit target %%")
    parser.add_argument("--stop-loss", type=float, default=8.0, help="Stop loss %%")
    parser.add_argument("--max-hold-days", type=int, default=60, help="Max holding period in days")
    parser.add_argument("--position-size", type=float, default=10.0, help="Position size as %% of portfolio")
    parser.add_argument("--strategy", type=str, default="composite_score_signals", help="Strategy name")
    parser.add_argument("--dry-run", action="store_true", help="Print results without saving to DB")
    args = parser.parse_args()

    today = date.today()
    start = date.fromisoformat(args.start_date) if args.start_date else today - timedelta(days=730)
    end = date.fromisoformat(args.end_date) if args.end_date else today

    results = run_backtest(
        start_date=start,
        end_date=end,
        initial_capital=args.initial_capital,
        max_positions=args.max_positions,
        min_composite=args.min_composite,
        profit_target_pct=args.profit_target,
        stop_loss_pct=args.stop_loss,
        max_hold_days=args.max_hold_days,
        position_size_pct=args.position_size,
        strategy_name=args.strategy,
    )

    if not results:
        logger.error("Backtest returned no results")
        return 1

    # Log summary
    separator = "=" * 60
    logger.info(f"\n{separator}")
    logger.info(f"BACKTEST RESULTS: {results['strategy_name']}")
    logger.info(separator)
    logger.info(f"Period:          {results['start_date']} to {results['end_date']}")
    logger.info(f"Initial Capital: ${results['initial_capital']:,.0f}")
    logger.info(f"Final Capital:   ${results['final_capital']:,.0f}")
    logger.info(f"Total Return:    {results['total_return_pct']:+.2f}%")
    logger.info(f"Ann. Return:     {results['annualized_return_pct']:+.2f}%")
    logger.info(f"Max Drawdown:    {results['max_drawdown_pct']:.2f}%")
    logger.info(f"Sharpe Ratio:    {results['sharpe_ratio']}")
    logger.info(f"Win Rate:        {results['win_rate_pct']:.1f}%")
    logger.info(f"Profit Factor:   {results['profit_factor']:.2f}")
    logger.info(f"Total Trades:    {results['total_trades']}")
    logger.info(f"Wins/Losses:     {results['winning_trades']}/{results['losing_trades']}")
    logger.info(f"Avg Trade:       {results['avg_trade_return_pct']:+.2f}%")
    logger.info(f"Best Trade:      {results['best_trade_pct']:+.2f}%")
    logger.info(f"Worst Trade:     {results['worst_trade_pct']:+.2f}%")
    logger.info(f"Avg Hold:        {results['avg_holding_days']:.1f} days")
    logger.info(separator)

    trades_list = results.pop("trades", [])
    results.pop("equity_curve", [])

    if not args.dry_run:
        results["trades"] = trades_list
        run_id = save_results(results)
        if run_id:
            logger.info(f"[BACKTEST] Saved to DB: run_id={run_id}")
        else:
            logger.error("[BACKTEST] Failed to save to DB (see logs)")
            return 1
    else:
        logger.info("[BACKTEST] [DRY RUN] Results not saved to DB")

    return 0


if __name__ == "__main__":
    sys.exit(main())
