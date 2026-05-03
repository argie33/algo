#!/usr/bin/env python3
"""
Swing Trader Scores Loader — Batch full-universe runner.

Computes the research-weighted swing trader score for every symbol in the
universe and persists to swing_trader_scores. The score itself is defined
in algo_swing_score.SwingTraderScore (Minervini SEPA + O'Neil CAN SLIM
+ Bulkowski pattern stats + Connors backtests + Bassal multi-timeframe).

Component weights (sum = 100):
    SETUP QUALITY     25   base type + breakout proximity + VCP + pivot + power + 3WT + HTF
    TREND QUALITY     20   Minervini 8-pt + Stage-2 phase + 30wk MA slope
    MOMENTUM / RS     20   RS percentile + 1m/3m/6m return blend
    VOLUME            12   breakout volume + accumulation days
    FUNDAMENTALS      10   EPS / revenue growth + ROE
    SECTOR/INDUSTRY    8   industry rank + sector rank + RS acceleration
    MULTI-TIMEFRAME    5   weekly + monthly buy_sell alignment

Hard gates applied BEFORE scoring (eliminates ~80% of universe):
    - Trend Template score < 7
    - Stage != 2
    - More than 25% from 52w high
    - Base count >= 4
    - Wide-and-loose base or quality D
    - Industry rank > 100 (bottom half)
    - Earnings within 5 trading days

USAGE:
    python3 loadswingscores.py                # full universe, today
    python3 loadswingscores.py --date 2026-04-24
    python3 loadswingscores.py --symbols AAPL,NVDA   # subset for testing
    python3 loadswingscores.py --min-completeness 70 # data-quality threshold

This loader is the source of truth that backs:
    - /api/algo/swing-scores endpoint
    - The "Swing Candidates" frontend page
    - The filter pipeline's primary ranking field

It should be run after EOD loaders (price_daily, trend_template_data,
industry_ranking, sector_ranking, growth_metrics) — orchestrated via
run_eod_loaders.sh / EventBridge.
"""

import argparse
import os
import sys
import time
from datetime import datetime, date as _date
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

sys.path.insert(0, str(Path(__file__).parent))
from algo_swing_score import SwingTraderScore  # noqa: E402

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "stocks"),
}


def _get_universe(cur, symbol_filter=None, min_completeness=70):
    """Universe = symbols with sufficient data coverage that have a company profile."""
    if symbol_filter:
        return list(symbol_filter)

    cur.execute(
        """
        SELECT DISTINCT cp.ticker
        FROM company_profile cp
        JOIN data_completeness_scores dcs ON dcs.symbol = cp.ticker
        WHERE dcs.composite_completeness_pct >= %s
          AND cp.ticker IS NOT NULL
          AND cp.ticker !~ '[^A-Za-z0-9.\\-]'
        ORDER BY cp.ticker
        """,
        (min_completeness,),
    )
    return [r[0] for r in cur.fetchall()]


def _get_profile(cur, symbol):
    cur.execute(
        "SELECT sector, industry FROM company_profile WHERE ticker = %s LIMIT 1",
        (symbol,),
    )
    r = cur.fetchone()
    return (r[0], r[1]) if r else (None, None)


def _persist_fail(cur, symbol, eval_date, fail_reason):
    """Persist a row even when the symbol fails gates so the UI can show why."""
    try:
        cur.execute(
            """
            INSERT INTO swing_trader_scores
                (symbol, eval_date, swing_score, grade,
                 setup_pts, trend_pts, momentum_pts, volume_pts,
                 fundamentals_pts, sector_pts, multi_tf_pts,
                 pass_gates, fail_reason, components)
            VALUES (%s, %s, 0, 'F', 0, 0, 0, 0, 0, 0, 0, FALSE, %s, '{}'::jsonb)
            ON CONFLICT (symbol, eval_date) DO UPDATE SET
                swing_score = 0,
                grade = 'F',
                setup_pts = 0, trend_pts = 0, momentum_pts = 0, volume_pts = 0,
                fundamentals_pts = 0, sector_pts = 0, multi_tf_pts = 0,
                pass_gates = FALSE,
                fail_reason = EXCLUDED.fail_reason,
                created_at = CURRENT_TIMESTAMP
            """,
            (symbol, eval_date, fail_reason),
        )
    except Exception:
        pass


def run(eval_date=None, symbol_filter=None, min_completeness=70, batch_size=200,
        verbose=False):
    if eval_date is None:
        eval_date = _date.today()
    elif isinstance(eval_date, str):
        eval_date = _date.fromisoformat(eval_date)

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Make sure most recent trend_template_data <= eval_date is reasonably fresh
    cur.execute("SELECT MAX(date) FROM trend_template_data WHERE date <= %s", (eval_date,))
    latest_trend = cur.fetchone()[0]
    if latest_trend is None:
        print(f"ABORT: no trend_template_data <= {eval_date}. Run loadtrendtemplate first.")
        cur.close(); conn.close()
        return

    if (eval_date - latest_trend).days > 7:
        print(f"WARN: trend_template_data is {(eval_date - latest_trend).days} days "
              f"behind eval_date ({latest_trend} vs {eval_date}). Scores will use stale gates.")

    universe = _get_universe(cur, symbol_filter=symbol_filter, min_completeness=min_completeness)

    print(f"\n{'='*70}")
    print(f"SWING TRADER SCORES — eval_date={eval_date}")
    print(f"  Universe: {len(universe)} symbols (completeness >= {min_completeness}%)")
    print(f"  Trend data latest: {latest_trend}")
    print(f"{'='*70}\n")

    sw = SwingTraderScore(cur=cur)

    grade_counts = {'A+': 0, 'A': 0, 'B': 0, 'C': 0, 'D': 0, 'F': 0}
    pass_count = 0
    fail_count = 0
    fail_reasons = {}
    error_count = 0
    started = time.time()

    for idx, symbol in enumerate(universe, 1):
        try:
            sector, industry = _get_profile(cur, symbol)
            result = sw.compute(symbol, eval_date, sector=sector, industry=industry)

            if result.get('pass'):
                pass_count += 1
                grade_counts[result.get('grade', 'F')] = grade_counts.get(result.get('grade', 'F'), 0) + 1
                if verbose:
                    print(f"  PASS  {symbol:6s}  {result['grade']:>2s}  {result['swing_score']:5.1f}")
            else:
                fail_count += 1
                reason = result.get('reason', 'unknown')
                # Bucket reason for summary
                bucket = reason.split(':')[0].split('(')[0].strip()
                fail_reasons[bucket] = fail_reasons.get(bucket, 0) + 1
                _persist_fail(cur, symbol, eval_date, reason)
        except Exception as e:
            error_count += 1
            if verbose:
                print(f"  ERR   {symbol:6s}  {e}")

        # Periodic commit + progress
        if idx % batch_size == 0:
            conn.commit()
            elapsed = time.time() - started
            rate = idx / elapsed if elapsed > 0 else 0
            eta = (len(universe) - idx) / rate if rate > 0 else 0
            print(f"  [{idx:>5d}/{len(universe)}] pass={pass_count} fail={fail_count} "
                  f"err={error_count}  rate={rate:.1f}/s  eta={int(eta)}s")

    conn.commit()
    elapsed = time.time() - started

    print(f"\n{'='*70}")
    print(f"DONE — {len(universe)} symbols in {int(elapsed)}s ({len(universe)/elapsed:.1f}/s)")
    print(f"  Passed gates: {pass_count}  ({100*pass_count/max(1,len(universe)):.1f}%)")
    print(f"  Failed gates: {fail_count}")
    print(f"  Errors:       {error_count}")
    print(f"\nGrade distribution (passers):")
    for g in ['A+', 'A', 'B', 'C', 'D', 'F']:
        n = grade_counts.get(g, 0)
        bar = '#' * int(n / max(1, max(grade_counts.values())) * 30)
        print(f"  {g:>2s}: {n:>4d}  {bar}")
    print(f"\nTop fail reasons:")
    for r, n in sorted(fail_reasons.items(), key=lambda x: -x[1])[:8]:
        print(f"  {n:>5d}  {r}")
    print(f"{'='*70}\n")

    cur.close()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Batch full-universe swing trader scores')
    parser.add_argument('--date', type=str, default=None,
                        help='Eval date (YYYY-MM-DD). Default = today.')
    parser.add_argument('--symbols', type=str, default=None,
                        help='Comma-separated symbol list (testing).')
    parser.add_argument('--min-completeness', type=int, default=70,
                        help='Minimum data completeness percent to include a symbol.')
    parser.add_argument('--batch-size', type=int, default=200,
                        help='Commit batch size.')
    parser.add_argument('--verbose', action='store_true', help='Per-symbol output.')
    args = parser.parse_args()
    syms = args.symbols.split(',') if args.symbols else None
    run(eval_date=args.date, symbol_filter=syms,
        min_completeness=args.min_completeness, batch_size=args.batch_size,
        verbose=args.verbose)
