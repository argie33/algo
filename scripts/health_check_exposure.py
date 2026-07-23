#!/usr/bin/env python3
"""Comprehensive exposure score health check - verify all 12 factors load correctly."""

import logging
from datetime import date
from utils.db import DatabaseContext

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

eval_date = date(2026, 7, 23)
print("=" * 80)
print("COMPREHENSIVE EXPOSURE SCORE HEALTH CHECK")
print("=" * 80)
print(f"Eval Date: {eval_date}")
print()

# Step 1: Check database connectivity and data availability
print("STEP 1: DATABASE CONNECTIVITY")
print("-" * 80)
try:
    with DatabaseContext('read') as cur:
        cur.execute('SELECT 1')
        print("OK: Database connection OK")

        tables = {
            'price_daily': 'SPY price data',
            'technical_data_daily': 'Moving averages',
            'market_health_daily': 'Breadth/A-D line data',
            'aaii_sentiment': 'AAII sentiment',
            'naaim': 'NAAIM exposure',
            'economic_data': 'Macro data (VIX, credit spreads, yield curve)',
        }

        for table, desc in tables.items():
            cur.execute(f'SELECT COUNT(*) FROM {table}')
            count = cur.fetchone()[0]
            print(f"OK: {table:25s}: {count:7d} rows ({desc})")
except Exception as e:
    print(f"FAIL: Database error: {e}")
    exit(1)

print()

# Step 2: Check data freshness for eval_date
print("STEP 2: DATA FRESHNESS FOR 2026-07-23")
print("-" * 80)
with DatabaseContext('read') as cur:
    checks = [
        ('price_daily (SPY)', "SELECT MAX(date) FROM price_daily WHERE symbol='SPY'"),
        ('technical_data_daily', "SELECT MAX(date) FROM technical_data_daily"),
        ('market_health_daily', "SELECT MAX(date) FROM market_health_daily"),
        ('aaii_sentiment', "SELECT MAX(date) FROM aaii_sentiment"),
        ('naaim', "SELECT MAX(date) FROM naaim"),
        ('economic_data (latest)', "SELECT MAX(date) FROM economic_data"),
    ]

    for label, query in checks:
        cur.execute(query)
        row = cur.fetchone()
        latest_date = row[0] if row and row[0] else None
        status = "OK" if latest_date and latest_date >= eval_date else "STALE"
        print(f"{status:5s}: {label:30s}: {latest_date}")

print()

# Step 3: Compute exposure score step by step
print("STEP 3: EXPOSURE SCORE COMPUTATION (12 FACTORS)")
print("-" * 80)

from algo.risk.market_exposure import MarketExposure

me = MarketExposure()

try:
    result = me.compute(eval_date, force_recompute=True)

    print(f"Raw Score: {result['raw_score']:.1f}/100")
    print(f"Capped Score: {result['exposure_pct']:.1f}%")
    print(f"Regime: {result['regime']}")
    print()
    print("FACTOR BREAKDOWN:")
    print("-" * 80)

    factor_order = [
        'trend_30wk', 'spy_momentum', 'breadth_200dma', 'distribution_days',
        'vix_regime', 'credit_spread', 'put_call_ratio', 'new_highs_lows',
        'ad_line', 'breadth_50dma', 'naaim', 'aaii_sentiment'
    ]

    all_ok = True
    for factor_name in factor_order:
        factor = result['factors'].get(factor_name, {})

        # Check if factor has required fields
        if 'pts' not in factor:
            print(f"FAIL: {factor_name:20s}: MISSING POINTS FIELD")
            all_ok = False
            continue

        if 'max' not in factor:
            print(f"FAIL: {factor_name:20s}: MISSING MAX FIELD")
            all_ok = False
            continue

        # CRITICAL: pts and max are required fields for all factors
        # Defaulting to 0 masks incomplete factor data and makes the health check pass when it should fail
        if 'pts' not in factor:
            print(f"FAIL: {factor_name:20s}: MISSING PTS FIELD (required for all factors)")
            all_ok = False
            continue

        pts = factor['pts']
        max_pts = factor['max']
        score = factor.get('score')

        # Check for data_unavailable flag
        if factor.get('data_unavailable'):
            print(f"FAIL: {factor_name:20s}: DATA UNAVAILABLE ({factor.get('reason', 'unknown')})")
            all_ok = False
            continue

        # Check for reasonable values
        if score is None:
            print(f"FAIL: {factor_name:20s}: SCORE IS NONE")
            all_ok = False
            continue

        if not (0 <= pts <= max_pts):
            print(f"FAIL: {factor_name:20s}: Points {pts:.1f} outside range [0,{max_pts}]")
            all_ok = False
            continue

        # Display factor (using ASCII-safe characters)
        bar_fill = int((pts / max_pts * 12)) if max_pts > 0 else 0
        bar = "[" + "=" * bar_fill + "-" * (12 - bar_fill) + "]"

        # Get detail value for display
        detail = ""
        if factor_name == 'trend_30wk':
            v = factor.get('price_vs_ma_pct')
            detail = f" ({v:+.1f}%)" if v is not None else ""
        elif factor_name in ['breadth_50dma', 'breadth_200dma']:
            v = factor.get('value')
            detail = f" ({v:.0f}%)" if v is not None else ""
        elif factor_name == 'aaii_sentiment':
            bull = factor.get('bullish_pct')
            bear = factor.get('bearish_pct')
            detail = f" (B{bull:.0f}%/Be{bear:.0f}%)" if bull and bear else ""
        elif factor_name == 'vix_regime':
            v = factor.get('value')
            detail = f" (VIX {v:.1f})" if v is not None else ""
        elif factor_name == 'credit_spread':
            v = factor.get('value')
            detail = f" ({v:.2f}%)" if v is not None else ""

        print(f"OK:   {factor_name:20s}: {bar} {pts:5.1f}/{max_pts:>3} {detail}")

    print()
    if result['halt_reasons']:
        print(f"HALT REASONS (hard vetoes):")
        for reason in result['halt_reasons']:
            print(f"  - {reason}")
    else:
        print("OK: No hard vetoes active - entry allowed")

    print()
    if all_ok:
        print("OK: ALL 12 FACTORS PRESENT AND VALID")
    else:
        print("FAIL: SOME FACTORS MISSING OR INVALID")

except Exception as e:
    print(f"FAIL: Computation failed: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

print()

# Step 4: Verify persistence
print("STEP 4: PERSISTENCE CHECK")
print("-" * 80)
with DatabaseContext('read') as cur:
    cur.execute('''
        SELECT exposure_pct, raw_score, regime, data_unavailable
        FROM market_exposure_daily
        WHERE date = %s
    ''', (eval_date,))
    row = cur.fetchone()
    if row:
        exp_pct, raw_score, regime, data_unavail = row
        print(f"OK: Persisted to market_exposure_daily")
        print(f"   exposure_pct: {exp_pct}%")
        print(f"   raw_score: {raw_score}")
        print(f"   regime: {regime}")
        print(f"   data_unavailable: {data_unavail}")
        if data_unavail:
            print(f"   WARNING: data_unavailable flag is TRUE")
    else:
        print(f"FAIL: Not persisted to database")

print()

# Step 5: Check for any weird fallbacks or defaults
print("STEP 5: FALLBACK/CHEAT DETECTION")
print("-" * 80)
weird_count = 0

for factor_name in factor_order:
    factor = result['factors'].get(factor_name, {})

    score = factor.get('score')
    if score is None:
        print(f"CHEAT DETECTED: {factor_name}: score is None (should fail-fast)")
        weird_count += 1

    if score == 0 and factor_name not in ['put_call_ratio']:
        if 'reason' in factor and 'unavailable' in factor.get('reason', '').lower():
            print(f"CHEAT DETECTED: {factor_name}: scored 0 due to unavailable data")
            weird_count += 1

    actual_max = factor.get('max')
    expected_max = {
        'trend_30wk': 15, 'spy_momentum': 10, 'breadth_200dma': 10,
        'distribution_days': 10, 'vix_regime': 10, 'credit_spread': 10,
        'put_call_ratio': 8, 'new_highs_lows': 7, 'ad_line': 6,
        'breadth_50dma': 6, 'naaim': 5, 'aaii_sentiment': 3
    }
    if actual_max != expected_max.get(factor_name):
        print(f"CHEAT DETECTED: {factor_name}: max={actual_max}, expected {expected_max.get(factor_name)}")
        weird_count += 1

if weird_count == 0:
    print("OK: No fallbacks, defaults, or cheats detected")
else:
    print(f"CHEAT DETECTED: {weird_count} potential issues detected")

print()
print("=" * 80)
print("HEALTH CHECK COMPLETE")
print("=" * 80)
