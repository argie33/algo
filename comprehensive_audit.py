from credential_manager import get_credential_manager
credential_manager = get_credential_manager()

﻿#!/usr/bin/env python3
"""
Comprehensive Algo Audit - Deep dive into data, logic, and execution
"""

import os, sys, psycopg2, json
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

def _get_db_config():
    """Lazy-load DB config at runtime instead of module import time."""
    return {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": credential_manager.get_db_credentials()["password"],
    "database": os.getenv("DB_NAME", "stocks"),
    }

class ComprehensiveAudit:
    def __init__(self):
        self.conn = None
        self.cur = None
        self.issues = []

    def connect(self):
        self.conn = psycopg2.connect(**_get_db_config())
        self.cur = self.conn.cursor()

    def disconnect(self):
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()

    def section(self, title):
        print(f"\n{'='*80}\n {title}\n{'='*80}")

    def check(self, condition, title, details=""):
        status = "[OK]" if condition else "[FAIL]"
        print(f"{status} {title}")
        if details:
            print(f"     {details}")
        if not condition:
            self.issues.append({'title': title, 'details': details})

    def run(self):
        try:
            self.connect()
            print(f"\n{'='*80}\n COMPREHENSIVE ALGO SYSTEM AUDIT\n {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{'='*80}")

            # 1. Database state
            self.section("1. DATABASE STATE")
            self.cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status='open'")
            open_pos = self.cur.fetchone()[0]
            self.cur.execute("SELECT COUNT(*) FROM algo_trades WHERE status='open'")
            open_trades = self.cur.fetchone()[0]
            self.cur.execute("SELECT COUNT(*) FROM algo_trades WHERE status='closed'")
            closed_trades = self.cur.fetchone()[0]
            
            print(f"\nPositions: {open_pos} open")
            print(f"Trades: {open_trades} open, {closed_trades} closed")
            
            # 2. Data Quality
            self.section("2. DATA QUALITY")
            self.cur.execute("SELECT COUNT(*) FROM price_daily WHERE close IS NULL OR close <= 0 OR volume <= 0")
            bad_prices = self.cur.fetchone()[0]
            self.check(bad_prices == 0, "Price data integrity", f"Bad: {bad_prices}")
            
            self.cur.execute("SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date >= CURRENT_DATE - INTERVAL '1 day'")
            recent_count = self.cur.fetchone()[0]
            print(f"Recent price data: {recent_count} symbols from last 24h")
            
            # 3. Signals
            self.section("3. SIGNAL PIPELINE")
            self.cur.execute("SELECT MAX(date) FROM buy_sell_daily")
            latest_signal = self.cur.fetchone()[0]
            self.cur.execute("SELECT signal, COUNT(*) FROM buy_sell_daily WHERE date=%s GROUP BY signal", (latest_signal,))
            signals = dict(self.cur.fetchall()) if latest_signal else {}
            
            print(f"Latest signals: {latest_signal}")
            for sig, count in signals.items():
                print(f"  {sig}: {count}")
            
            # 4. Filter results
            self.section("4. FILTER PIPELINE RESULTS")
            self.cur.execute("""
                SELECT COUNT(*),
                  SUM(CASE WHEN tier1_pass THEN 1 ELSE 0 END),
                  SUM(CASE WHEN tier3_pass THEN 1 ELSE 0 END),
                  SUM(CASE WHEN tier5_pass THEN 1 ELSE 0 END),
                  SUM(CASE WHEN advanced_pass THEN 1 ELSE 0 END)
                FROM algo_signals_evaluated
                WHERE eval_date=(SELECT MAX(date) FROM algo_signals_evaluated)
                AND signal='BUY'
            """)
            result = self.cur.fetchone()
            if result and result[0]:
                total, t1, t3, t5, adv = result
                print(f"\nLatest evaluation (total={total}):")
                print(f"  T1 (data): {t1}")
                print(f"  T3 (trend): {t3}")
                print(f"  T5 (portfolio): {t5}")
                print(f"  Adv (filters): {adv}")
            
            # 5. Trade execution
            self.section("5. RECENT TRADES")
            self.cur.execute("""
                SELECT symbol, entry_price, entry_date, status FROM algo_trades
                ORDER BY entry_date DESC LIMIT 10
            """)
            trades = self.cur.fetchall()
            for sym, entry, date, status in trades:
                print(f"  {sym}: ${entry:.2f} on {date} [{status}]")
            
            # 6. Issues
            self.section("6. VALIDATION CHECKS")
            self.cur.execute("SELECT COUNT(*) FROM algo_trades WHERE stop_loss_price >= entry_price")
            bad_stops = self.cur.fetchone()[0]
            self.check(bad_stops == 0, "Stop loss < entry price", f"Bad: {bad_stops}")
            
            self.cur.execute("SELECT COUNT(*) FROM algo_trades WHERE entry_date < signal_date")
            bad_timing = self.cur.fetchone()[0]
            self.check(bad_timing == 0, "Entry date >= signal date", f"Bad: {bad_timing}")
            
            # Summary
            self.section("SUMMARY")
            print(f"Total issues: {len(self.issues)}")
            if self.issues:
                for issue in self.issues:
                    print(f"  - {issue['title']}: {issue['details']}")

        finally:
            self.disconnect()

if __name__ == '__main__':
    audit = ComprehensiveAudit()
    audit.run()
