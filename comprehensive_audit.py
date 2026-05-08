#!/usr/bin/env python3
"""
COMPREHENSIVE SYSTEM AUDIT
Find ALL data quality, calculation, and logic issues.
"""

import psycopg2
import os
from pathlib import Path
from dotenv import load_dotenv

env_file = Path('.env.local')
if env_file.exists():
    load_dotenv(env_file)

DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'user': os.getenv('DB_USER', 'stocks'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME', 'stocks'),
}

issues = []

def log_issue(category, severity, issue):
    """Log an issue for final report."""
    issues.append({
        'category': category,
        'severity': severity,  # CRITICAL, MAJOR, MINOR
        'issue': issue
    })
    print(f"[{severity:8}] {category:25} {issue}")

def audit_signal_generation():
    """Audit signal generation logic."""
    print("\n" + "="*80)
    print("AUDIT: SIGNAL GENERATION")
    print("="*80)

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Issue 1: NULL entry prices
    cur.execute("SELECT COUNT(*) FROM buy_sell_daily WHERE signal='BUY' AND entry_price IS NULL")
    null_entry = cur.fetchone()[0]
    if null_entry > 0:
        log_issue("Signal Generation", "MAJOR", f"{null_entry} BUY signals missing entry_price")

    # Issue 2: NaN/invalid RSI
    cur.execute("SELECT COUNT(*) FROM buy_sell_daily WHERE signal='BUY' AND rsi IS NOT NULL AND (rsi < 0 OR rsi > 100)")
    bad_rsi = cur.fetchone()[0]
    if bad_rsi > 0:
        log_issue("Signal Generation", "MINOR", f"{bad_rsi} BUY signals have NaN/invalid RSI (expected for early data)")

    # Issue 3: Entry price > high or < low
    cur.execute("""
        SELECT COUNT(*) FROM buy_sell_daily b
        WHERE signal='BUY' AND entry_price IS NOT NULL
        AND (entry_price > high OR entry_price < low)
    """)
    bad_entry = cur.fetchone()[0]
    if bad_entry > 0:
        log_issue("Signal Generation", "CRITICAL", f"{bad_entry} BUY signals have entry_price outside daily range [low, high]")

    # Issue 4: Entry price not matching close
    cur.execute("""
        SELECT COUNT(*) FROM buy_sell_daily b
        WHERE signal='BUY' AND entry_price IS NOT NULL
        AND ABS(entry_price - close) > close * 0.01
    """)
    close_mismatch = cur.fetchone()[0]
    if close_mismatch > 0:
        log_issue("Signal Generation", "MAJOR", f"{close_mismatch} BUY signals have entry_price != close (>1% diff)")

    # Issue 5: Insufficient volume for entry
    cur.execute("""
        SELECT COUNT(*) FROM buy_sell_daily b
        WHERE signal='BUY' AND volume = 0
    """)
    zero_vol = cur.fetchone()[0]
    if zero_vol > 0:
        log_issue("Signal Generation", "MAJOR", f"{zero_vol} BUY signals on zero-volume days")

    cur.close()
    conn.close()

def audit_trade_execution():
    """Audit trade execution logic."""
    print("\n" + "="*80)
    print("AUDIT: TRADE EXECUTION")
    print("="*80)

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Issue 1: Same-day entry/exit
    cur.execute("""
        SELECT COUNT(*) FROM algo_trades
        WHERE status IN ('CLOSED', 'EXITED')
        AND signal_date = exit_date
    """)
    same_day = cur.fetchone()[0]
    if same_day > 0:
        total_closed = cur.execute("""
            SELECT COUNT(*) FROM algo_trades WHERE status IN ('CLOSED', 'EXITED')
        """)
        cur.execute("SELECT COUNT(*) FROM algo_trades WHERE status IN ('CLOSED', 'EXITED')")
        total = cur.fetchone()[0]
        log_issue("Trade Execution", "CRITICAL", f"{same_day}/{total} closed trades enter/exit same day (impossible)")

    # Issue 2: Entry/exit price at extreme high/low (skip - no high/low in algo_trades)
    # Skipped - algo_trades doesn't have high/low columns

    # Issue 3: Negative P&L on closed trades
    cur.execute("""
        SELECT COUNT(*) FROM algo_trades
        WHERE status IN ('CLOSED', 'EXITED') AND profit_loss_pct < 0
    """)
    negative_pnl = cur.fetchone()[0]
    if negative_pnl > 0:
        log_issue("Trade Execution", "MAJOR", f"{negative_pnl} closed trades with negative P&L (possible stop-loss hits)")

    # Issue 4: Position size issues
    cur.execute("""
        SELECT COUNT(*) FROM algo_trades
        WHERE position_size_pct IS NULL OR position_size_pct <= 0 OR position_size_pct > 100
    """)
    bad_position = cur.fetchone()[0]
    if bad_position > 0:
        log_issue("Trade Execution", "MAJOR", f"{bad_position} trades with invalid position_size_pct")

    # Issue 5: Bracket order consistency
    cur.execute("""
        SELECT COUNT(*) FROM algo_trades
        WHERE bracket_order = true
        AND (target_1_price IS NULL OR target_1_r_multiple IS NULL OR stop_loss_price IS NULL)
    """)
    bad_bracket = cur.fetchone()[0]
    if bad_bracket > 0:
        log_issue("Trade Execution", "MAJOR", f"{bad_bracket} bracket orders missing target/stop prices")

    # Issue 6: Exit without reason
    cur.execute("""
        SELECT COUNT(*) FROM algo_trades
        WHERE status IN ('CLOSED', 'EXITED') AND (exit_reason IS NULL OR exit_reason = '')
    """)
    no_reason = cur.fetchone()[0]
    if no_reason > 0:
        log_issue("Trade Execution", "MINOR", f"{no_reason} closed trades missing exit_reason")

    cur.close()
    conn.close()

def audit_filter_logic():
    """Audit filter tier logic."""
    print("\n" + "="*80)
    print("AUDIT: FILTER LOGIC")
    print("="*80)

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Check if filter table exists
    cur.execute("""
        SELECT EXISTS(
            SELECT 1 FROM information_schema.tables
            WHERE table_name='algo_signals_evaluated'
        )
    """)
    if not cur.fetchone()[0]:
        log_issue("Filter Logic", "CRITICAL", "algo_signals_evaluated table doesn't exist")
        cur.close()
        conn.close()
        return

    # Issue 1: Filter cascade not monotonic
    cur.execute("""
        SELECT filter_tier, COUNT(*) as cnt
        FROM algo_signals_evaluated
        GROUP BY filter_tier
        ORDER BY filter_tier
    """)

    tiers = {}
    for tier, cnt in cur.fetchall():
        tiers[tier] = cnt

    prev_cnt = None
    for tier in sorted(tiers.keys()):
        if prev_cnt is not None and tiers[tier] > prev_cnt:
            log_issue("Filter Logic", "CRITICAL", f"Tier {tier} has MORE signals ({tiers[tier]}) than previous tier ({prev_cnt})")
        prev_cnt = tiers[tier]

    # Issue 2: NULL filter reasons
    cur.execute("SELECT COUNT(*) FROM algo_signals_evaluated WHERE filter_reason IS NULL")
    null_reason = cur.fetchone()[0]
    if null_reason > 0:
        log_issue("Filter Logic", "MINOR", f"{null_reason} signals missing filter_reason")

    # Issue 3: Invalid signal_quality_score
    cur.execute("""
        SELECT COUNT(*) FROM algo_signals_evaluated
        WHERE signal_quality_score IS NOT NULL AND (signal_quality_score < 0 OR signal_quality_score > 100)
    """)
    bad_score = cur.fetchone()[0]
    if bad_score > 0:
        log_issue("Filter Logic", "MAJOR", f"{bad_score} signals have invalid quality_score (not in [0,100])")

    cur.close()
    conn.close()

def audit_price_data():
    """Audit price data consistency."""
    print("\n" + "="*80)
    print("AUDIT: PRICE DATA")
    print("="*80)

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Issue 1: High < Low
    cur.execute("SELECT COUNT(*) FROM price_daily WHERE high < low")
    bad_hl = cur.fetchone()[0]
    if bad_hl > 0:
        log_issue("Price Data", "CRITICAL", f"{bad_hl} price records have high < low (data corruption)")

    # Issue 2: Close out of range
    cur.execute("SELECT COUNT(*) FROM price_daily WHERE close < low OR close > high")
    out_range = cur.fetchone()[0]
    if out_range > 0:
        log_issue("Price Data", "CRITICAL", f"{out_range} price records have close outside [low, high]")

    # Issue 3: NULL prices
    cur.execute("SELECT COUNT(*) FROM price_daily WHERE close IS NULL OR open IS NULL OR volume IS NULL")
    null_prices = cur.fetchone()[0]
    if null_prices > 0:
        log_issue("Price Data", "CRITICAL", f"{null_prices} price records with NULL close/open/volume")

    # Issue 4: Duplicate dates per symbol
    cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT symbol, date, COUNT(*) as cnt
            FROM price_daily
            GROUP BY symbol, date HAVING COUNT(*) > 1
        ) x
    """)
    dupes = cur.fetchone()[0]
    if dupes > 0:
        log_issue("Price Data", "MAJOR", f"{dupes} symbols have duplicate price records for same date")

    # Issue 5: Gaps in price history (more than 5 business days)
    cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT symbol, date,
                   LAG(date) OVER (PARTITION BY symbol ORDER BY date) as prev_date,
                   date - LAG(date) OVER (PARTITION BY symbol ORDER BY date) as gap_days
            FROM price_daily
        ) x
        WHERE gap_days > 10 AND gap_days IS NOT NULL
    """)
    gaps = cur.fetchone()[0]
    if gaps > 0:
        log_issue("Price Data", "MINOR", f"{gaps} symbol-date pairs have gaps > 10 days")

    cur.close()
    conn.close()

def audit_calculations():
    """Audit financial calculations."""
    print("\n" + "="*80)
    print("AUDIT: CALCULATIONS")
    print("="*80)

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Issue 1: P&L calculation mismatch
    cur.execute("""
        SELECT trade_id, entry_price, exit_price, profit_loss_pct
        FROM algo_trades
        WHERE status IN ('CLOSED', 'EXITED')
        AND entry_price IS NOT NULL AND exit_price IS NOT NULL AND profit_loss_pct IS NOT NULL
        LIMIT 10
    """)

    calc_errors = 0
    for trade_id, entry, exit_p, pnl in cur.fetchall():
        expected = float(exit_p - entry) / float(entry) * 100 if entry != 0 else 0
        actual = float(pnl) if pnl else 0
        if abs(expected - actual) > 0.1:
            calc_errors += 1

    if calc_errors > 0:
        log_issue("Calculations", "CRITICAL", f"P&L calculation error in {calc_errors} trades")

    # Issue 2: Risk/Reward invalid
    cur.execute("""
        SELECT COUNT(*) FROM algo_trades
        WHERE entry_price > 0 AND stop_loss_price >= entry_price
    """)
    bad_stop = cur.fetchone()[0]
    if bad_stop > 0:
        log_issue("Calculations", "CRITICAL", f"{bad_stop} trades have stop_loss >= entry_price (backwards)")

    # Issue 3: Target prices below entry
    cur.execute("""
        SELECT COUNT(*) FROM algo_trades
        WHERE entry_price > 0 AND target_1_price IS NOT NULL AND target_1_price <= entry_price
    """)
    bad_target = cur.fetchone()[0]
    if bad_target > 0:
        log_issue("Calculations", "CRITICAL", f"{bad_target} trades have target_1_price <= entry_price")

    cur.close()
    conn.close()

def audit_orchestration():
    """Audit orchestration and timing logic."""
    print("\n" + "="*80)
    print("AUDIT: ORCHESTRATION")
    print("="*80)

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Issue 1: Trades on non-trading days
    cur.execute("""
        SELECT COUNT(*) FROM algo_trades t
        LEFT JOIN price_daily p ON t.symbol = p.symbol AND t.signal_date = p.date
        WHERE p.date IS NULL AND t.signal_date IS NOT NULL
        LIMIT 5
    """)
    no_price = cur.fetchone()[0]
    if no_price > 0:
        log_issue("Orchestration", "CRITICAL", f"{no_price} trades entered on dates with no price data")

    # Issue 2: Exit before entry
    cur.execute("""
        SELECT COUNT(*) FROM algo_trades
        WHERE status IN ('CLOSED', 'EXITED')
        AND exit_date < signal_date
    """)
    backwards = cur.fetchone()[0]
    if backwards > 0:
        log_issue("Orchestration", "CRITICAL", f"{backwards} trades exited before they entered")

    # Issue 3: Trade duration unrealistic
    cur.execute("""
        SELECT COUNT(*) FROM algo_trades
        WHERE status IN ('CLOSED', 'EXITED')
        AND (exit_date - signal_date) > 365
    """)
    long_trades = cur.fetchone()[0]
    if long_trades > 0:
        log_issue("Orchestration", "MINOR", f"{long_trades} trades held > 1 year (consider review)")

    cur.close()
    conn.close()

def print_summary():
    """Print final summary."""
    print("\n" + "="*80)
    print("COMPREHENSIVE AUDIT SUMMARY")
    print("="*80)

    if not issues:
        print("\nNo issues found!")
        return

    # Group by severity
    critical = [i for i in issues if i['severity'] == 'CRITICAL']
    major = [i for i in issues if i['severity'] == 'MAJOR']
    minor = [i for i in issues if i['severity'] == 'MINOR']

    print(f"\nCRITICAL ISSUES: {len(critical)}")
    for issue in critical:
        print(f"  - [{issue['category']}] {issue['issue']}")

    print(f"\nMAJOR ISSUES: {len(major)}")
    for issue in major:
        print(f"  - [{issue['category']}] {issue['issue']}")

    print(f"\nMINOR ISSUES: {len(minor)}")
    for issue in minor:
        print(f"  - [{issue['category']}] {issue['issue']}")

    print("\n" + "="*80)
    print(f"TOTAL ISSUES FOUND: {len(issues)}")
    print("="*80)

def main():
    """Run all audits."""
    print("\n" + "="*80)
    print("COMPREHENSIVE SYSTEM AUDIT")
    print("Find ALL issues preventing correct operation")
    print("="*80)

    audit_signal_generation()
    audit_trade_execution()
    audit_filter_logic()
    audit_price_data()
    audit_calculations()
    audit_orchestration()

    print_summary()

if __name__ == "__main__":
    main()
