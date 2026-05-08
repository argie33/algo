#!/usr/bin/env python3
"""Real-time safeguard monitoring dashboard for paper trading.

Tracks:
- Earnings blocks (entries rejected due to earnings window)
- Liquidity blocks (entries rejected due to illiquidity)
- Margin status (account leverage)
- Economic gates (entry blocks due to releases)
"""

import os
import sys
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from datetime import date, datetime, timedelta
import logging
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "stocks"),
}


def get_earnings_calendar_status():
    """Get upcoming earnings dates."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        cur.execute("""
            SELECT symbol, earnings_date, earnings_time
            FROM earnings_calendar
            WHERE earnings_date >= %s AND earnings_date <= %s
            ORDER BY earnings_date
            LIMIT 10
        """, (date.today(), date.today() + timedelta(days=30)))

        rows = cur.fetchall()
        cur.close()
        conn.close()

        return rows
    except Exception as e:
        logger.warning(f"Failed to fetch earnings: {e}")
        return []


def get_margin_status():
    """Get current margin status."""
    try:
        from algo_margin_monitor import MarginMonitor
        mm = MarginMonitor()
        info = mm.get_margin_usage()
        return info
    except Exception as e:
        logger.warning(f"Margin check failed: {e}")
        return None


def get_economic_events():
    """Get upcoming high-impact economic events."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        cur.execute("""
            SELECT event_name, scheduled_time, impact
            FROM economic_calendar
            WHERE impact IN ('high', 'High')
            AND scheduled_time >= NOW()
            AND scheduled_time <= NOW() + INTERVAL '7 days'
            ORDER BY scheduled_time
        """)

        rows = cur.fetchall()
        cur.close()
        conn.close()

        return rows
    except Exception as e:
        logger.warning(f"Failed to fetch economic calendar: {e}")
        return []


def get_position_summary():
    """Get current portfolio positions."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        # Try to fetch positions - may not have actual data
        cur.execute("""
            SELECT symbol, quantity, price, created_at
            FROM algo_positions
            WHERE status = 'OPEN'
            ORDER BY created_at DESC
            LIMIT 10
        """)

        rows = cur.fetchall()
        cur.close()
        conn.close()

        return rows
    except Exception:
        # Table may not exist or have different schema in dev environment
        return []


def print_dashboard():
    """Print real-time safeguard monitoring dashboard."""

    print("\n" + "="*80)
    print(f"SAFEGUARD MONITORING DASHBOARD - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)

    # Margin Status
    print("\n[ACCOUNT STATUS]")
    margin = get_margin_status()
    if margin:
        margin_pct = margin['margin_usage_pct']
        equity = margin['equity']
        cash = margin['cash']

        # Color coding
        if margin_pct > 80:
            status = "CRITICAL"
        elif margin_pct > 70:
            status = "WARNING"
        else:
            status = "HEALTHY"

        print(f"  Status:   [{status:8s}] Margin {margin_pct:.1f}%")
        print(f"  Equity:   ${equity:>15,.2f}")
        print(f"  Cash:     ${cash:>15,.2f}")
    else:
        print("  [OFFLINE] Alpaca API unavailable")

    # Earnings Calendar
    print("\n[EARNINGS CALENDAR - Next 30 Days]")
    earnings = get_earnings_calendar_status()
    if earnings:
        print(f"  {len(earnings)} upcoming earnings:\n")
        for symbol, earnings_date, earnings_time in earnings[:5]:
            days_away = (earnings_date - date.today()).days
            if days_away <= 7:
                marker = "[BLACKOUT]"
            elif days_away <= 14:
                marker = "[CAUTION ]"
            else:
                marker = "[OK      ]"
            print(f"    {marker} {symbol:6s} on {earnings_date} ({days_away:2d} days)")
    else:
        print("  No earnings data available")

    # Economic Events
    print("\n[ECONOMIC CALENDAR - Next 7 Days]")
    events = get_economic_events()
    if events:
        print(f"  {len(events)} high-impact events:\n")
        for event_name, scheduled_time, impact in events[:5]:
            minutes_away = (scheduled_time.replace(tzinfo=None) - datetime.now()).total_seconds() / 60
            if minutes_away < 60:
                marker = "[HALT    ]"
            elif minutes_away < 1440:  # < 1 day
                marker = "[CAUTION ]"
            else:
                marker = "[WATCH   ]"
            print(f"    {marker} {event_name:25s} in {minutes_away:>6.0f} min")
    else:
        print("  No high-impact events scheduled")

    # Positions
    print("\n[OPEN POSITIONS]")
    positions = get_position_summary()
    if positions:
        print(f"  {len(positions)} open positions:\n")
        for symbol, quantity, price, created_at in positions[:5]:
            days_held = (date.today() - created_at.date()).days
            print(f"    {symbol:6s} {quantity:>6.0f} sh @ ${float(price):>7.2f} ({days_held} days)")
    else:
        print("  No open positions")

    # Recommendations
    print("\n[RECOMMENDATIONS]")
    if margin and margin['margin_usage_pct'] > 70:
        print("  WARNING: Margin usage high. Consider closing positions.")

    if earnings:
        near_earnings = [e for e in earnings if (e[1] - date.today()).days <= 7]
        if near_earnings:
            symbols = ", ".join([e[0] for e in near_earnings[:3]])
            print(f"  CAUTION: Earnings approaching ({symbols}). Safeguards active.")

    if events:
        near_events = [e for e in events if (e[1].replace(tzinfo=None) - datetime.now()).total_seconds() < 86400]
        if near_events:
            print(f"  CAUTION: Economic releases within 24h. Entry gates may be active.")

    print("\n" + "="*80)


def main():
    """Main monitoring loop."""
    import time

    try:
        while True:
            print_dashboard()
            print("\nPress Ctrl+C to exit. Refreshing every 5 minutes...\n")
            time.sleep(300)  # Refresh every 5 minutes
    except KeyboardInterrupt:
        print("\n\nMonitoring stopped.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
