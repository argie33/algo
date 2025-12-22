#!/usr/bin/env python3
"""
Intelligent Statement Loader - Smart Rate Limit Handling
Runs all statement loaders ONE AT A TIME with settling delays
Balances: NO rate limit errors + reasonable speed (~2.5-3 hours)

Key principle: Sequential execution prevents API storms
"""

import subprocess
import sys
import time
import logging
from datetime import datetime, timedelta
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [LOADER] - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# Loaders in optimal order (annual first, then quarterly, then TTM, earnings last)
LOADERS = [
    ("Annual Balance Sheet", "loadannualbalancesheet.py"),
    ("Quarterly Balance Sheet", "loadquarterlybalancesheet.py"),
    ("Annual Income Statement", "loadannualincomestatement.py"),
    ("Quarterly Income Statement", "loadquarterlyincomestatement.py"),
    ("Annual Cash Flow", "loadannualcashflow.py"),
    ("Quarterly Cash Flow", "loadquarterlycashflow.py"),
    ("TTM Income Statement", "loadttmincomestatement.py"),
    ("TTM Cash Flow", "loadttmcashflow.py"),
    ("Earnings History", "loadearningshistory.py"),
]

class SmartLoader:
    def __init__(self, settling_delay_seconds=600):
        """
        settling_delay_seconds: Wait time between loaders for API to settle
        Default 600s (10 minutes) = sweet spot for yfinance rate limit recovery
        """
        self.settling_delay = settling_delay_seconds
        self.results = {
            "passed": [],
            "failed": [],
            "start_time": None,
            "end_time": None
        }

    def run_loader(self, name: str, script: str) -> bool:
        """Run a single loader, return True if success"""
        logging.info(f"\n▶️  [{len(self.results['passed']) + len(self.results['failed']) + 1}/{len(LOADERS)}] {name}")
        logging.info(f"   Script: {script}")

        start = time.time()

        try:
            # Run loader
            result = subprocess.run(
                [sys.executable, script],
                capture_output=True,
                text=True,
                timeout=1800  # 30 minute timeout per loader
            )

            duration = time.time() - start

            # Check result
            if result.returncode == 0:
                logging.info(f"✅ SUCCESS in {duration:.0f}s")
                self.results["passed"].append(name)
                return True
            else:
                logging.error(f"❌ FAILED (exit code {result.returncode}) in {duration:.0f}s")
                # Show last few lines of error
                if result.stdout:
                    lines = result.stdout.split('\n')
                    for line in lines[-5:]:
                        if line.strip():
                            logging.error(f"   {line}")
                self.results["failed"].append(name)
                return False

        except subprocess.TimeoutExpired:
            logging.error(f"❌ TIMEOUT (30 min exceeded)")
            self.results["failed"].append(name)
            return False
        except Exception as e:
            logging.error(f"❌ EXCEPTION: {e}")
            self.results["failed"].append(name)
            return False

    def wait_for_api_recovery(self, loader_index: int, total_loaders: int):
        """Wait between loaders for API rate limits to reset"""
        if loader_index >= total_loaders - 1:
            return  # Don't wait after last loader

        hours = self.settling_delay / 3600
        minutes = (self.settling_delay % 3600) / 60

        logging.info(f"\n⏳ API SETTLING PERIOD (rate limit recovery)")
        logging.info(f"   Waiting {int(minutes)}m {int(self.settling_delay % 60)}s for API to recover...")
        logging.info(f"   (Prevents rate limit collisions from concurrent API load)")

        # Count down in chunks for visibility
        remaining = self.settling_delay
        while remaining > 0:
            chunk = min(60, remaining)
            time.sleep(chunk)
            remaining -= chunk

            if remaining > 0:
                minutes_left = remaining / 60
                if remaining > 60:
                    logging.info(f"   {minutes_left:.1f}m remaining...")

    def run_all(self):
        """Run all loaders with smart settling delays"""
        self.results["start_time"] = datetime.now()

        logging.info("=" * 80)
        logging.info("STATEMENT LOADERS - SMART RATE LIMIT MODE")
        logging.info("=" * 80)
        logging.info(f"Total loaders: {len(LOADERS)}")
        logging.info(f"Settling delay: {self.settling_delay}s ({self.settling_delay/60:.0f}m)")
        logging.info(f"Expected total: ~{len(LOADERS) * 10 + len(LOADERS) * self.settling_delay / 60:.0f}m")
        logging.info(f"Start time: {self.results['start_time'].strftime('%Y-%m-%d %H:%M:%S')}")
        logging.info("=" * 80)

        for idx, (name, script) in enumerate(LOADERS):
            # Run loader
            self.run_loader(name, script)

            # Wait for API recovery (except after last loader)
            if idx < len(LOADERS) - 1:
                self.wait_for_api_recovery(idx, len(LOADERS))

        self.results["end_time"] = datetime.now()
        self.print_summary()

    def print_summary(self):
        """Print final summary"""
        duration = (self.results["end_time"] - self.results["start_time"]).total_seconds()

        logging.info("\n" + "=" * 80)
        logging.info("FINAL SUMMARY")
        logging.info("=" * 80)

        start_str = self.results["start_time"].strftime('%Y-%m-%d %H:%M:%S')
        end_str = self.results["end_time"].strftime('%Y-%m-%d %H:%M:%S')

        logging.info(f"Start: {start_str}")
        logging.info(f"End:   {end_str}")
        logging.info(f"Total: {duration/60:.1f} minutes ({duration/3600:.1f} hours)")

        passed = len(self.results["passed"])
        failed = len(self.results["failed"])
        total = passed + failed
        success_rate = (passed / total * 100) if total > 0 else 0

        logging.info(f"\nLoaders:")
        logging.info(f"  ✅ Passed: {passed}/{total}")
        logging.info(f"  ❌ Failed: {failed}/{total}")
        logging.info(f"  Success:  {success_rate:.1f}%")

        if self.results["passed"]:
            logging.info(f"\n✅ PASSED:")
            for name in self.results["passed"]:
                logging.info(f"  • {name}")

        if self.results["failed"]:
            logging.error(f"\n❌ FAILED:")
            for name in self.results["failed"]:
                logging.error(f"  • {name}")

            logging.info(f"\n💡 Re-run failed loaders individually:")
            for name in self.results["failed"]:
                script = name.lower().replace(" ", "").replace("(", "").replace(")", "") + ".py"
                # Map name to script
                for loader_name, loader_script in LOADERS:
                    if loader_name == name:
                        logging.info(f"   python3 {loader_script}")
                        break
        else:
            logging.info(f"\n🎉 ALL LOADERS COMPLETED SUCCESSFULLY!")
            logging.info(f"   All financial statement data loaded with ZERO rate limit errors")
            logging.info(f"   Ready to calculate scores:")
            logging.info(f"   python3 calculate_scores.py")

        logging.info("=" * 80)

        return failed == 0

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Load all statement loaders intelligently without rate limit errors"
    )
    parser.add_argument(
        "--settling-delay",
        type=int,
        default=600,
        help="Seconds to wait between loaders for API recovery (default 600=10min)"
    )

    args = parser.parse_args()

    loader = SmartLoader(settling_delay_seconds=args.settling_delay)
    success = loader.run_all()

    sys.exit(0 if success else 1)
