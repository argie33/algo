#!/usr/bin/env python3
"""
Data Pipeline Orchestrator
Manages the complete data loading pipeline: local loading → AWS deployment

Coordinates all loaders and auto-triggers next steps when dependencies complete:
1. loaddailycompanydata.py → loads positioning metrics for all symbols
2. loadmomentum.py → calculates momentum metrics in parallel
3. loadpositioning.py → calculates derived positioning scores
4. loadstockscores.py → refreshes all stock scores
5. deploy_to_aws.sh → syncs data to AWS RDS (manual trigger or auto)

Author: Data Pipeline Manager
Updated: 2025-10-25
"""

import logging
import os
import sys
import subprocess
import time
from datetime import datetime
import psycopg2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

class DataPipelineOrchestrator:
    def __init__(self):
        self.db_host = "localhost"
        self.db_port = 5432
        self.db_user = "postgres"
        self.db_password = "password"
        self.db_name = "stocks"
        
    def get_db_connection(self):
        """Get PostgreSQL connection"""
        try:
            conn = psycopg2.connect(
                host=self.db_host,
                port=self.db_port,
                user=self.db_user,
                password=self.db_password,
                database=self.db_name
            )
            return conn
        except Exception as e:
            logging.error(f"Failed to connect to database: {e}")
            return None
    
    def get_table_count(self, table_name):
        """Get row count for a table"""
        try:
            conn = self.get_db_connection()
            if not conn:
                return 0
            cur = conn.cursor()
            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cur.fetchone()[0]
            cur.close()
            conn.close()
            return count
        except Exception as e:
            logging.warning(f"Could not get count for {table_name}: {e}")
            return 0
    
    def is_process_running(self, script_name):
        """Check if a script is currently running"""
        try:
            result = subprocess.run(
                ["pgrep", "-f", script_name],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except:
            return False
    
    def report_status(self):
        """Print detailed pipeline status"""
        print("\n" + "="*80)
        print("                    DATA PIPELINE STATUS REPORT")
        print("="*80)
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        # Running processes
        print("🔄 RUNNING PROCESSES:")
        daily_running = self.is_process_running("loaddailycompanydata")
        momentum_running = self.is_process_running("loadmomentum")
        positioning_running = self.is_process_running("loadpositioning")
        scores_running = self.is_process_running("loadstockscores")
        
        if daily_running:
            print("  ✅ loaddailycompanydata.py - Loading positioning metrics")
        if momentum_running:
            print("  ✅ loadmomentum.py - Calculating momentum metrics")
        if positioning_running:
            print("  ✅ loadpositioning.py - Calculating positioning scores")
        if scores_running:
            print("  ✅ loadstockscores.py - Refreshing stock scores")
        
        if not any([daily_running, momentum_running, positioning_running, scores_running]):
            print("  ℹ️  No loaders currently running")
        
        # Database status
        print("\n📊 DATABASE COUNTS:")
        positioning_count = self.get_table_count("positioning_metrics")
        momentum_count = self.get_table_count("momentum_metrics")
        scores_count = self.get_table_count("stock_scores")
        
        print(f"  positioning_metrics: {positioning_count} rows")
        print(f"  momentum_metrics: {momentum_count} rows")
        print(f"  stock_scores: {scores_count} rows")
        
        # Pipeline status
        print("\n📈 PIPELINE PROGRESS:")
        if positioning_count > 0:
            print(f"  ✅ Positioning data loaded: {positioning_count} symbols")
        else:
            print(f"  ⏳ Positioning data: Waiting for load")
        
        if momentum_count > 0:
            pct = (momentum_count / 5307) * 100
            print(f"  🔄 Momentum metrics: {momentum_count}/5307 ({pct:.1f}%)")
        else:
            print(f"  ⏳ Momentum metrics: Not started")
        
        if scores_count >= 5000:
            print(f"  ✅ Stock scores: Loaded and refreshed")
        else:
            print(f"  ⏳ Stock scores: Awaiting refresh")
        
        # Next steps
        print("\n🎯 NEXT STEPS:")
        if daily_running or momentum_running:
            print("  1. 🔄 Waiting for current loaders to complete")
        if positioning_count > 0 and not positioning_running:
            print("  2. ✅ Positioning metrics ready for score calculation")
        if momentum_count >= 5307 and not scores_running:
            print("  3. ✅ Ready to refresh stock scores")
        if positioning_count > 0 and momentum_count >= 5307 and scores_count >= 5000:
            print("  4. ✅ All local data ready - Deploy to AWS when ready")
            print("       Run: bash /home/stocks/algo/deploy_to_aws.sh")
        
        print("\n" + "="*80)
    
    def run(self):
        """Main orchestration loop"""
        logging.info("Data Pipeline Orchestrator started")
        
        while True:
            try:
                self.report_status()
                
                # Check if we should auto-trigger next steps
                daily_running = self.is_process_running("loaddailycompanydata")
                momentum_running = self.is_process_running("loadmomentum")
                positioning_running = self.is_process_running("loadpositioning")
                scores_running = self.is_process_running("loadstockscores")
                
                # If momentum is done and scores aren't running, prepare to refresh
                if momentum_running == False and scores_running == False:
                    momentum_count = self.get_table_count("momentum_metrics")
                    if momentum_count >= 5307:
                        logging.info("Momentum loading complete - all data ready for final steps")
                
                # Wait before next status check
                time.sleep(60)
                
            except KeyboardInterrupt:
                logging.info("Orchestrator interrupted by user")
                break
            except Exception as e:
                logging.error(f"Orchestrator error: {e}")
                time.sleep(60)

def main():
    orchestrator = DataPipelineOrchestrator()
    orchestrator.run()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Stopped by user")
        sys.exit(0)
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        sys.exit(1)
