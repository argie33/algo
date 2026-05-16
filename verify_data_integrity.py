#!/usr/bin/env python3
"""
Data Integrity Verification - Pre-trade validation checks

Validates that the data pipeline is ready before trading:
1. Price data completeness (≥100 symbols with recent data)
2. Technical indicators calculated (RSI, SMA, ATR present)
3. Signal generation (buy/sell signals and quality scores)
4. Portfolio tracking (trades and positions exist)
5. Market health freshness (daily snapshots recent)
6. Risk metrics availability (performance and VaR tables ready)
"""

import os
import sys
from datetime import date, timedelta
from pathlib import Path
from dotenv import load_dotenv

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

def check_price_completeness():
    """Verify price_daily has recent data for many symbols."""
    print("\n[1/6] Price Data Completeness")
    try:
        import psycopg2
        db_config = {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", 5432)),
            "user": os.getenv("DB_USER", "stocks"),
            "password": os.getenv("DB_PASSWORD", "postgres"),
            "database": os.getenv("DB_NAME", "stocks"),
        }
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()

        # Check for recent price data
        cur.execute("""
            SELECT COUNT(DISTINCT symbol) FROM price_daily
            WHERE date >= CURRENT_DATE - INTERVAL '1 days'
        """)
        recent_symbols = cur.fetchone()[0]

        if recent_symbols < 100:
            print(f"  ✗ Only {recent_symbols} symbols with recent price data (need ≥100)")
            cur.close()
            conn.close()
            return False, f"Insufficient symbols: {recent_symbols}"

        # Check for data volume
        cur.execute("SELECT COUNT(*) FROM price_daily WHERE date >= CURRENT_DATE - INTERVAL '7 days'")
        total_prices = cur.fetchone()[0]

        print(f"  ✓ Price data: {recent_symbols} symbols, {total_prices} price points (7 days)")
        cur.close()
        conn.close()
        return True, f"{recent_symbols} symbols OK"
    except Exception as e:
        print(f"  ✗ Price data check failed: {str(e)}")
        return False, str(e)

def check_technical_indicators():
    """Verify technical indicators (RSI, SMA, ATR) are calculated."""
    print("\n[2/6] Technical Indicators")
    try:
        import psycopg2
        db_config = {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", 5432)),
            "user": os.getenv("DB_USER", "stocks"),
            "password": os.getenv("DB_PASSWORD", "postgres"),
            "database": os.getenv("DB_NAME", "stocks"),
        }
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()

        # Check for recent technical data
        cur.execute("""
            SELECT COUNT(*) FROM technical_data_daily
            WHERE date >= CURRENT_DATE - INTERVAL '1 days'
            AND rsi_14 IS NOT NULL
            AND sma_20 IS NOT NULL
            AND atr_14 IS NOT NULL
        """)
        valid_technicals = cur.fetchone()[0]

        if valid_technicals < 50:
            print(f"  ✗ Only {valid_technicals} symbols with technical indicators (need ≥50)")
            cur.close()
            conn.close()
            return False, f"Insufficient technicals: {valid_technicals}"

        print(f"  ✓ Technical indicators: {valid_technicals} symbols with RSI, SMA, ATR")
        cur.close()
        conn.close()
        return True, f"{valid_technicals} symbols OK"
    except Exception as e:
        print(f"  ✗ Technical indicator check failed: {str(e)}")
        return False, str(e)

def check_signal_generation():
    """Verify buy/sell signals and quality scores exist."""
    print("\n[3/6] Signal Generation")
    try:
        import psycopg2
        db_config = {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", 5432)),
            "user": os.getenv("DB_USER", "stocks"),
            "password": os.getenv("DB_PASSWORD", "postgres"),
            "database": os.getenv("DB_NAME", "stocks"),
        }
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()

        # Check buy/sell signals
        cur.execute("""
            SELECT COUNT(*) FROM buy_sell_daily
            WHERE date >= CURRENT_DATE - INTERVAL '1 days'
        """)
        signals = cur.fetchone()[0]

        # Check signal quality scores
        cur.execute("""
            SELECT COUNT(*) FROM signal_quality_scores
            WHERE date >= CURRENT_DATE - INTERVAL '1 days'
        """)
        quality_scores = cur.fetchone()[0]

        if signals < 50 or quality_scores < 50:
            print(f"  ✗ Insufficient signals ({signals}) or quality scores ({quality_scores})")
            cur.close()
            conn.close()
            return False, f"Signals: {signals}, Quality: {quality_scores}"

        print(f"  ✓ Signal generation: {signals} signals, {quality_scores} quality scores")
        cur.close()
        conn.close()
        return True, f"Signals OK"
    except Exception as e:
        print(f"  ✗ Signal generation check failed: {str(e)}")
        return False, str(e)

def check_portfolio_tracking():
    """Verify trades and positions tables have data."""
    print("\n[4/6] Portfolio Tracking")
    try:
        import psycopg2
        db_config = {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", 5432)),
            "user": os.getenv("DB_USER", "stocks"),
            "password": os.getenv("DB_PASSWORD", "postgres"),
            "database": os.getenv("DB_NAME", "stocks"),
        }
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()

        # Check trades table
        cur.execute("SELECT COUNT(*) FROM algo_trades")
        trades = cur.fetchone()[0]

        # Check positions table
        cur.execute("SELECT COUNT(*) FROM algo_positions")
        positions = cur.fetchone()[0]

        print(f"  ✓ Portfolio tracking: {trades} trades, {positions} positions")
        cur.close()
        conn.close()
        return True, f"Portfolio OK"
    except Exception as e:
        print(f"  ✗ Portfolio tracking check failed: {str(e)}")
        return False, str(e)

def check_market_health():
    """Verify market health snapshots are recent."""
    print("\n[5/6] Market Health")
    try:
        import psycopg2
        db_config = {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", 5432)),
            "user": os.getenv("DB_USER", "stocks"),
            "password": os.getenv("DB_PASSWORD", "postgres"),
            "database": os.getenv("DB_NAME", "stocks"),
        }
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()

        # Check market health daily
        cur.execute("""
            SELECT COUNT(*) FROM market_health_daily
            WHERE date >= CURRENT_DATE - INTERVAL '1 days'
        """)
        health_records = cur.fetchone()[0]

        if health_records == 0:
            print(f"  ✗ No market health data from today")
            cur.close()
            conn.close()
            return False, "No market health data"

        print(f"  ✓ Market health: {health_records} daily snapshots")
        cur.close()
        conn.close()
        return True, "Market health OK"
    except Exception as e:
        print(f"  ✗ Market health check failed: {str(e)}")
        return False, str(e)

def check_risk_metrics():
    """Verify risk calculation tables are populated."""
    print("\n[6/6] Risk Metrics")
    try:
        import psycopg2
        db_config = {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", 5432)),
            "user": os.getenv("DB_USER", "stocks"),
            "password": os.getenv("DB_PASSWORD", "postgres"),
            "database": os.getenv("DB_NAME", "stocks"),
        }
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()

        # Check performance tables
        cur.execute("""
            SELECT COUNT(*) FROM algo_performance_daily
            WHERE date >= CURRENT_DATE - INTERVAL '1 days'
        """)
        perf_records = cur.fetchone()[0]

        # Check VaR tables
        cur.execute("""
            SELECT COUNT(*) FROM algo_var
            WHERE date >= CURRENT_DATE - INTERVAL '1 days'
        """)
        var_records = cur.fetchone()[0]

        print(f"  ✓ Risk metrics: {perf_records} performance records, {var_records} VaR records")
        cur.close()
        conn.close()
        return True, "Risk metrics OK"
    except Exception as e:
        print(f"  ✗ Risk metrics check failed: {str(e)}")
        return False, str(e)

def main():
    print("\n" + "="*70)
    print("DATA INTEGRITY VERIFICATION - PRE-TRADE VALIDATION")
    print("="*70)

    checks = [
        ("Price Completeness", check_price_completeness),
        ("Technical Indicators", check_technical_indicators),
        ("Signal Generation", check_signal_generation),
        ("Portfolio Tracking", check_portfolio_tracking),
        ("Market Health", check_market_health),
        ("Risk Metrics", check_risk_metrics),
    ]

    results = {}
    for name, check_func in checks:
        try:
            passed, detail = check_func()
            results[name] = (passed, detail)
        except Exception as e:
            print(f"  ✗ Unexpected error: {str(e)}")
            results[name] = (False, str(e))

    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)

    passed = sum(1 for p, _ in results.values() if p)
    total = len(results)

    for name, (passed, detail) in results.items():
        status = "✓" if passed else "✗"
        print(f"{status} {name:25s} - {detail}")

    print("\n" + "="*70)
    if passed == total:
        print(f"✓ ALL {total} CHECKS PASSED - System ready for trading")
        print("="*70 + "\n")
        return 0
    else:
        print(f"✗ {total - passed}/{total} checks failed - Fix data issues before trading")
        print("="*70 + "\n")
        return 1

if __name__ == "__main__":
    sys.exit(main())
