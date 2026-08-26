#!/usr/bin/env python3
"""
Historical backtest of signal_quality_score's predictive power, reconstructed from
price_daily across many years - NOT limited to buy_sell_daily's live history (which only
covers the CURRENT formula since 2026-08-20, ~1 month as of 2026-08-26; see
[[signal_quality_score_validation_formula_regime_bug_fixed_20260826]]).

WHY THIS IS POSSIBLE: every input to compute_signal_quality_components() except
institutional_ownership and vcp_strength (both optional - the formula already excludes
missing components from its denominator) is a deterministic function of OHLCV price data
alone: RSI, MACD, Minervini trend score, Weinstein stage, and distance from 52-week high.
price_daily has decades of history for liquid symbols. This script recomputes those inputs
with the SAME formulas production uses (reusing loaders/technical_indicators.py's
compute_rsi/compute_macd/compute_atr directly; replicating load_trend_analysis.py's
Minervini/Weinstein formulas exactly, since that loader only ever computes the last 10
days and has no "give me the whole history" mode), replays the exact same BUY-trigger
logic production uses (algo/signals/buy_signal_generator.py::BuySignalGenerator - the
single source of truth "Used by: loaders/load_buy_sell_daily.py, orchestrator Phase 7,
backtesting"), scores every historical BUY with the exact same
compute_signal_quality_components() Phase 7/8 use, and runs a genuine Fama-MacBeth-style
monthly cross-sectional check (many independent months, not a pooled panel) - the same
rigor bar this codebase's stock_scores pillar audits already use.

NOTE ON algo/signals/vectorized.py::VectorizedSignalGenerator: deliberately NOT used here.
Its compute_weinstein_stage_parallel() uses a DIFFERENT formula (close vs sma200 + 30wk MA
slope sign) than load_trend_analysis.py (close vs sma200 AND sma50 vs sma200, no slope) -
confirmed dead code (only self-referenced from algo/signals/__init__.py, no test coverage,
no caller in phase7/orchestrator/loaders) so not a live divergence bug, but using it here
would have silently tested a formula nothing live has ever used. load_trend_analysis.py's
formula is the one that actually reaches trend_template_data -> signal_quality_score.

Usage:
    python -m algo.research.signal_quality_score_historical_backtest [--start-date DATE]
        [--end-date DATE] [--universe-size N] [--horizons 5,10,20]
"""

import argparse
import logging
from datetime import date, timedelta

import numpy as np
import pandas as pd

from algo.signals.buy_signal_generator import BuySignalGenerator
from loaders.signal_quality_scorer import compute_signal_quality_components
from loaders.technical_indicators import (
    compute_atr,
    compute_macd,
    compute_moving_averages,
    compute_rsi,
    detect_and_adjust_splits,
)
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

MIN_ROBUST_MONTHS = 6
_UNIVERSE_EXCLUDE = {"SPY", "QQQ", "IWM", "DIA", "VTI"}  # index ETFs - production trades equities only


def select_universe(size: int, min_history_start: str) -> list[str]:
    with DatabaseContext("read") as cur:
        cur.execute(
            """
            WITH long_history AS (
                SELECT symbol FROM price_daily
                WHERE COALESCE(data_unavailable,false)=false AND date >= %(min_start)s
                GROUP BY symbol
                HAVING COUNT(*) > 2400 AND MAX(date) >= '2026-08-01' AND MIN(date) <= %(cutoff)s
            ),
            recent_liquidity AS (
                SELECT symbol, AVG(close*volume) AS avg_dollar_vol
                FROM price_daily
                WHERE date >= '2026-06-01' AND COALESCE(data_unavailable,false)=false
                GROUP BY symbol
            )
            SELECT lh.symbol
            FROM long_history lh JOIN recent_liquidity rl ON rl.symbol = lh.symbol
            WHERE lh.symbol != ALL(%(exclude)s)
            ORDER BY rl.avg_dollar_vol DESC
            LIMIT %(size)s
            """,
            {
                "min_start": min_history_start,
                "cutoff": (pd.Timestamp(min_history_start) + pd.Timedelta(days=180)).date(),
                "exclude": list(_UNIVERSE_EXCLUDE),
                "size": size,
            },
        )
        return [r[0] for r in cur.fetchall()]


_SPIKE_RATIO = 8.0  # matches the live-verified detection query in [[price_daily_sequence_check_never_fired_daily_loads_fixed_20260826]]


def _scrub_reverting_spikes(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Defense-in-depth against the price_daily data-integrity bug fixed in
    loaders/price_transformer.py (2026-08-26): a bad print that entered the DB before that
    fix landed is still sitting in history - this fix only stops NEW ones. Same signature
    used to find and quantify that bug: a single day's close jumps >8x from the day before
    AND reverts >8x by the day after (a real move doesn't undo itself on the very next
    print). Carries the prior day's OHLC forward for that one row rather than dropping it,
    to keep the trading-day index intact for rolling-window indicators.
    """
    close = df["close"]
    prev_close = close.shift(1)
    next_close = close.shift(-1)
    is_spike = (
        (prev_close > 0)
        & (next_close > 0)
        & ((close / prev_close) > _SPIKE_RATIO)
        & ((close / next_close) > _SPIKE_RATIO)
    )
    n_spikes = int(is_spike.sum())
    if n_spikes == 0:
        return df
    logger.warning(
        f"[BACKTEST] {symbol}: scrubbing {n_spikes} reverting-spike row(s) "
        "(price_daily data-integrity bug - see price_daily_sequence_check_never_fired_daily_loads_fixed_20260826)"
    )
    df = df.copy()
    spike_idx = df.index[is_spike]
    for col in ("open", "high", "low", "close"):
        df.loc[spike_idx, col] = df[col].shift(1).loc[spike_idx]
    return df


def fetch_price_history(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Raw OHLCV, then detect_and_adjust_splits() back-adjusts ALL of open/high/low/close
    (not just close) for stock splits - the same function loaders/load_technical_indicators.py
    uses before computing indicators, reused here for identical treatment. Confirmed
    necessary: an early smoke test using only adj_close (close-only adjustment) produced a
    +80% mean 10-day forward return in one quintile, a stock-split artifact (this universe
    includes NVDA/AAPL/AVGO-class names with real multi-for-1 splits in the backtest window).
    Adjusting close alone while leaving high/low raw would also corrupt swing-pivot
    detection and ATR right at split boundaries, not just the forward return.
    """
    with DatabaseContext("read") as cur:
        cur.execute(
            """
            SELECT date, open, high, low, close, volume
            FROM price_daily
            WHERE symbol = %s AND date >= %s AND date <= %s AND COALESCE(data_unavailable, false) = false
            ORDER BY date ASC
            """,
            (symbol, start_date, end_date),
        )
        rows = cur.fetchall()
    if not rows:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = df[c].astype(float)
    df = _scrub_reverting_spikes(df, symbol)
    return detect_and_adjust_splits(df)


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Attach every signal_quality_score/BUY-trigger input, using production's exact
    formulas (loaders/technical_indicators.py's shared functions; load_trend_analysis.py's
    Minervini/Weinstein criteria, vectorized here instead of "last 10 days only")."""
    close, high, low = df["close"], df["high"], df["low"]

    mas = compute_moving_averages(close)
    df["sma_50"] = mas["sma_50"]
    df["sma_200"] = mas["sma_200"]
    df["ema_21"] = mas["ema_21"]
    df["rsi"] = compute_rsi(close)
    macd_line, signal_line = compute_macd(close)
    df["macd"] = macd_line
    df["macd_signal"] = signal_line
    df["atr"] = compute_atr(high, low, close, 14)

    roc_20 = close.pct_change(20) * 100
    roc_60 = close.pct_change(60) * 100
    roc_252 = close.pct_change(252) * 100

    # Minervini score (0-8) - exact criteria from loaders/load_trend_analysis.py
    c1 = (close > df["sma_200"]).astype(float)
    c2 = (close > df["sma_50"]).astype(float)
    c3 = (df["sma_50"] > df["sma_200"]).astype(float)
    c4 = (roc_60 > 0).astype(float)
    c5 = (roc_252 > 10).astype(float)
    c6 = (df["rsi"] > 50).astype(float)
    c7 = (close > df["sma_200"] * 1.10).astype(float)
    c8 = (roc_20 > 0).astype(float)
    valid_minervini = df["sma_200"].notna() & df["sma_50"].notna() & roc_60.notna() & roc_252.notna() & roc_20.notna()
    df["minervini_trend_score"] = np.where(valid_minervini, c1 + c2 + c3 + c4 + c5 + c6 + c7 + c8, np.nan)

    # Weinstein stage (1-4) - exact criteria from loaders/load_trend_analysis.py
    above200 = close > df["sma_200"]
    sma50_above_sma200 = df["sma_50"] > df["sma_200"]
    valid_weinstein = close.notna() & df["sma_200"].notna() & df["sma_50"].notna()
    stage = pd.Series(np.nan, index=df.index)
    stage[valid_weinstein & above200 & sma50_above_sma200] = 2
    stage[valid_weinstein & above200 & ~sma50_above_sma200] = 3
    stage[valid_weinstein & ~above200 & sma50_above_sma200] = 1
    stage[valid_weinstein & ~above200 & ~sma50_above_sma200] = 4
    df["weinstein_stage"] = stage

    # percent_from_52w_high - same definition load_signal_quality_scores.py uses
    high_52w = high.rolling(252, min_periods=1).max()
    df["percent_from_52w_high"] = np.where(high_52w > 0, (close - high_52w) / high_52w * 100, np.nan)

    return df


def to_generator_rows(df: pd.DataFrame) -> list[dict[str, object]]:
    rows = []
    for r in df.itertuples(index=False):
        rows.append(
            {
                "date": r.date,
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
                "sma_50": None if pd.isna(r.sma_50) else float(r.sma_50),
                "sma_200": None if pd.isna(r.sma_200) else float(r.sma_200),
                "ema_21": None if pd.isna(r.ema_21) else float(r.ema_21),
                "atr": None if pd.isna(r.atr) else float(r.atr),
                "rsi": None if pd.isna(r.rsi) else float(r.rsi),
                "macd": None if pd.isna(r.macd) else float(r.macd),
                "macd_signal": None if pd.isna(r.macd_signal) else float(r.macd_signal),
                "adx": None,
                "mansfield_rs": None,
            }
        )
    return rows


def generate_historical_buy_signals(symbol: str, df: pd.DataFrame) -> list[dict[str, object]]:
    """BUY trigger via the actual production single source of truth
    (algo/signals/buy_signal_generator.py), then signal_quality_score via the actual
    production single source of truth (loaders/signal_quality_scorer.py)."""
    rows = to_generator_rows(df)
    generator = BuySignalGenerator()
    try:
        signals = generator.run(symbol, rows)
    except (RuntimeError, ValueError) as e:
        # Not an error for the overall backtest run: one symbol's signal generation failing
        # (e.g. insufficient indicator history) means no candidates for this symbol only -
        # already surfaced via the warning above, run() continues to the rest of the universe.
        logger.warning(f"[BACKTEST] {symbol}: signal generation failed, skipping - {e}")
        return []

    by_date = {r["date"]: r for r in df.to_dict("records")}
    buys = []
    for sig in signals:
        if sig["signal"] != "BUY":
            continue
        ind = by_date.get(sig["date"])
        if ind is None:
            continue
        components = compute_signal_quality_components(
            signal_type="BUY",
            rsi=ind.get("rsi"),
            macd=ind.get("macd"),
            macd_signal=ind.get("macd_signal"),
            minervini_score=ind.get("minervini_trend_score"),
            weinstein_stage=(int(ind["weinstein_stage"]) if pd.notna(ind.get("weinstein_stage")) else None),
            percent_from_52w_high=ind.get("percent_from_52w_high"),
            institutional_ownership=None,  # not reconstructable from price history alone
            vcp_strength=None,  # not reconstructable from price history alone
        )
        buys.append(
            {
                "symbol": symbol,
                "date": sig["date"],
                "entry_close": sig["close"],
                "signal_quality_score": components["composite_sqs"],
                "data_completeness": components["data_completeness"],
                # base_quality_score is a hardcoded constant (always 50 for BUY - see
                # loaders/signal_quality_scorer.py::BuySignalScorer.calculate_base_quality_score) -
                # deliberately excluded here, it cannot correlate with anything by construction.
                "volume_confirmation_score": components["volume_confirmation_score"],
                "trend_template_score": components["trend_template_score"],
                "distance_from_high_score": components["distance_from_high_score"],
                "market_stage_score": components["market_stage_score"],
            }
        )
    return buys


def attach_forward_returns(
    buys_df: pd.DataFrame, price_by_symbol: dict[str, pd.DataFrame], horizons: list[int]
) -> pd.DataFrame:
    spy_df = price_by_symbol.get("SPY")
    for h in horizons:
        rets = []
        spy_rets = []
        for row in buys_df.itertuples(index=False):
            pdf = price_by_symbol[row.symbol]
            idx = pdf.index[pdf["date"] == row.date]
            if len(idx) == 0 or idx[0] + h >= len(pdf):
                rets.append(np.nan)
            else:
                entry = pdf["close"].iloc[idx[0]]
                fwd = pdf["close"].iloc[idx[0] + h]
                rets.append(fwd / entry - 1.0 if entry else np.nan)
            if spy_df is not None:
                sidx = spy_df.index[spy_df["date"] == row.date]
                if len(sidx) == 0 or sidx[0] + h >= len(spy_df):
                    spy_rets.append(np.nan)
                else:
                    s_entry = spy_df["close"].iloc[sidx[0]]
                    s_fwd = spy_df["close"].iloc[sidx[0] + h]
                    spy_rets.append(s_fwd / s_entry - 1.0 if s_entry else np.nan)
            else:
                spy_rets.append(np.nan)
        buys_df[f"fwd_ret_{h}"] = rets
        buys_df[f"spy_fwd_ret_{h}"] = spy_rets
    return buys_df


def fama_macbeth_monthly(df: pd.DataFrame, score_col: str, horizon: int) -> dict[str, float]:
    """Real monthly cross-sectional Fama-MacBeth: one Pearson correlation per calendar
    month (pooled panels double-count within-month correlation; this doesn't), then a
    one-sample t-test of the mean monthly correlation against zero across months.
    Generic over score_col so each signal_quality_score COMPONENT can be tested
    individually, not just the composite - a composite null result doesn't prove every
    component is uninformative; it could mean real signal in one component is being
    diluted/offset by noise in others once summed together."""
    sub = df[["month", score_col, f"fwd_ret_{horizon}"]].dropna()
    monthly_corrs = []
    for _month, g in sub.groupby("month"):
        if len(g) < 10 or g[score_col].std() == 0:
            continue
        r = g[score_col].corr(g[f"fwd_ret_{horizon}"])
        if pd.notna(r):
            monthly_corrs.append(r)
    n_months = len(monthly_corrs)
    if n_months < 2:
        return {"n_months": n_months, "mean_corr": float("nan"), "t_stat": float("nan")}
    arr = np.array(monthly_corrs)
    mean_corr = arr.mean()
    se = arr.std(ddof=1) / np.sqrt(n_months)
    t_stat = mean_corr / se if se > 0 else float("nan")
    return {"n_months": n_months, "mean_corr": mean_corr, "t_stat": t_stat}


def run(start_date: str, end_date: str, universe_size: int, horizons: list[int]) -> None:
    symbols = select_universe(universe_size, start_date)
    if "SPY" not in symbols:
        symbols = [*symbols, "SPY"]
    print(f"Universe: {len(symbols)} symbols, {start_date} to {end_date}")

    price_by_symbol: dict[str, pd.DataFrame] = {}
    all_buys = []
    for i, symbol in enumerate(symbols):
        df = fetch_price_history(symbol, start_date, end_date)
        if len(df) < 300:
            continue
        df = compute_indicators(df)
        price_by_symbol[symbol] = df[["date", "close"]].reset_index(drop=True)
        if symbol == "SPY":
            continue  # SPY itself isn't a tradeable BUY candidate here, only the benchmark
        buys = generate_historical_buy_signals(symbol, df)
        all_buys.extend(buys)
        if (i + 1) % 25 == 0:
            print(f"  ...processed {i + 1}/{len(symbols)} symbols, {len(all_buys)} BUY signals so far")

    if not all_buys:
        print("No historical BUY signals reconstructed - nothing to validate.")
        return

    buys_df = pd.DataFrame(all_buys)
    print(f"\nTotal reconstructed historical BUY signals: {len(buys_df)}")
    buys_df["month"] = pd.to_datetime(buys_df["date"]).dt.to_period("M")
    month_counts = buys_df.groupby("month").size()
    robust_months = (month_counts >= 30).sum()
    print(
        f"Distinct months with >= 30 signals: {robust_months} (span: {month_counts.index.min()} to {month_counts.index.max()})\n"
    )

    buys_df = attach_forward_returns(buys_df, price_by_symbol, horizons)

    component_cols = [
        "signal_quality_score",
        "volume_confirmation_score",
        "trend_template_score",
        "distance_from_high_score",
        "market_stage_score",
    ]

    for h in horizons:
        print(f"=== {h}-day forward return: Fama-MacBeth monthly cross-sectional check ===")
        print("  Component breakdown (base_quality_score excluded - hardcoded constant, can't correlate):")
        for col in component_cols:
            fm = fama_macbeth_monthly(buys_df, col, h)
            label = "COMPOSITE" if col == "signal_quality_score" else col
            print(
                f"    {label:28s} n_months={fm['n_months']:<4d} mean_corr={fm['mean_corr']:+.4f}  t={fm['t_stat']:+.2f}"
            )

        sub = buys_df[["signal_quality_score", f"fwd_ret_{h}"]].dropna()
        if len(sub) >= 10:
            quint = sub.assign(q=pd.qcut(sub["signal_quality_score"], 5, labels=False, duplicates="drop"))
            print("  Composite quintile breakdown (0=lowest sqs, 4=highest), pooled across full period:")
            for q, g in quint.groupby("q"):
                print(f"    Q{int(q)}: mean_fwd_ret={g[f'fwd_ret_{h}'].mean():+.4%}  n={len(g)}")
            monotonic = quint.groupby("q")[f"fwd_ret_{h}"].mean().is_monotonic_increasing
            print(f"  Monotonic (higher score -> higher forward return)? {monotonic}")

        pooled_ret = buys_df[f"fwd_ret_{h}"].mean()
        win_rate = (buys_df[f"fwd_ret_{h}"] > 0).mean()
        spy_ret = buys_df[f"spy_fwd_ret_{h}"].mean()
        print(
            f"  Pooled avg BUY forward return: {pooled_ret:+.4%}  (win rate {win_rate:.1%})  "
            f"vs. avg contemporaneous SPY forward return: {spy_ret:+.4%}\n"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    default_end = (date.today() - timedelta(days=35)).isoformat()  # leave room for 20d fwd returns to resolve
    parser.add_argument("--start-date", default="2016-01-01")
    parser.add_argument("--end-date", default=default_end)
    parser.add_argument("--universe-size", type=int, default=150)
    parser.add_argument("--horizons", default="5,10,20")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
    horizons = [int(h) for h in args.horizons.split(",")]
    run(args.start_date, args.end_date, args.universe_size, horizons)


if __name__ == "__main__":
    main()
