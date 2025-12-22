#!/usr/bin/env python3
"""
Monitored Statement Loader Execution
Runs statement loaders with real-time monitoring for rate limit errors
Automatically adjusts strategy if issues detected
"""

import subprocess
import sys
import time
import logging
from datetime import datetime
import re

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [MONITOR] - %(levelname)s - %(message)s",
    stream=sys.stdout
)

class LoaderMonitor:
    """Monitor loader execution and detect/handle errors"""

    def __init__(self, mode="standard"):
        self.mode = mode
        self.rate_limit_errors = 0
        self.timeout_errors = 0
        self.other_errors = 0
        self.loader_outputs = []

    def detect_errors_in_output(self, output: str) -> dict:
        """Scan output for known error patterns"""
        errors = {
            "rate_limit": 0,
            "timeout": 0,
            "database": 0,
            "other": 0
        }

        # Rate limit patterns
        if re.search(r"429|Too Many Requests|Rate limit", output, re.IGNORECASE):
            errors["rate_limit"] += 1

        # Timeout patterns
        if re.search(r"timeout|read timed out|ConnectTimeout", output, re.IGNORECASE):
            errors["timeout"] += 1

        # Database errors
        if re.search(r"psycopg2|database|connection refused", output, re.IGNORECASE):
            errors["database"] += 1

        return errors

    def should_increase_delay(self, error_count: int) -> bool:
        """Decide if we should increase delays based on error frequency"""
        return error_count >= 3

    def run_loader_monitored(self, script_name: str, loader_name: str) -> bool:
        """
        Run a single loader with detailed monitoring
        Returns: True if successful, False if failed
        """
        logging.info(f"\n▶️  STARTING: {loader_name}")
        logging.info(f"   Script: {script_name}")

        start_time = time.time()

        try:
            process = subprocess.Popen(
                [sys.executable, script_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )

            output_lines = []
            recent_errors = []

            # Monitor output in real-time
            for line in process.stdout:
                line = line.rstrip()
                output_lines.append(line)

                # Log important lines
                if any(keyword in line.lower() for keyword in ["error", "failed", "rate limit", "timeout", "warning"]):
                    logging.warning(f"   {line}")
                    recent_errors.append(line)
                elif any(keyword in line.lower() for keyword in ["successfully", "✓", "processed"]):
                    logging.info(f"   {line}")

            process.wait()
            full_output = "\n".join(output_lines)

            # Analyze errors
            errors = self.detect_errors_in_output(full_output)
            self.loader_outputs.append({
                "loader": loader_name,
                "output": full_output,
                "errors": errors,
                "return_code": process.returncode
            })

            duration = time.time() - start_time

            if process.returncode == 0:
                logging.info(f"✅ SUCCESS: {loader_name} completed in {duration:.1f}s")
                return True
            else:
                logging.error(f"❌ FAILED: {loader_name} (exit code: {process.returncode}, {duration:.1f}s)")

                # Report detected errors
                if errors["rate_limit"] > 0:
                    logging.error(f"   ⚠️  Rate limit errors detected: {errors['rate_limit']}")
                if errors["timeout"] > 0:
                    logging.error(f"   ⚠️  Timeout errors detected: {errors['timeout']}")
                if errors["database"] > 0:
                    logging.error(f"   ⚠️  Database errors detected: {errors['database']}")

                return False

        except Exception as e:
            logging.error(f"❌ EXCEPTION running {loader_name}: {e}")
            return False

    def run_all_loaders(self, loaders: list, mode: str = "standard") -> dict:
        """
        Run all loaders with monitoring
        Returns execution summary
        """
        summary = {
            "total": len(loaders),
            "passed": 0,
            "failed": 0,
            "failed_loaders": [],
            "start_time": datetime.now(),
            "end_time": None,
            "total_duration": 0,
            "mode": mode
        }

        logging.info("=" * 80)
        logging.info("STATEMENT LOADERS - MONITORED EXECUTION")
        logging.info("=" * 80)
        logging.info(f"Mode: {mode}")
        logging.info(f"Total loaders: {len(loaders)}")
        logging.info(f"Start time: {summary['start_time'].strftime('%Y-%m-%d %H:%M:%S')}")
        logging.info("=" * 80)

        for idx, loader in enumerate(loaders, 1):
            success = self.run_loader_monitored(loader["script"], loader["name"])

            if success:
                summary["passed"] += 1
            else:
                summary["failed"] += 1
                summary["failed_loaders"].append(loader["name"])

            # Wait before next loader (based on mode)
            if idx < len(loaders):
                delay_map = {"fast": 2, "standard": 3, "safe": 5, "careful": 10}
                delay = delay_map.get(mode, 3)
                logging.info(f"⏳ Waiting {delay}s before next loader...")
                time.sleep(delay)

        summary["end_time"] = datetime.now()
        summary["total_duration"] = (summary["end_time"] - summary["start_time"]).total_seconds()

        return summary

    def print_summary(self, summary: dict):
        """Print detailed execution summary"""
        logging.info("\n" + "=" * 80)
        logging.info("EXECUTION SUMMARY")
        logging.info("=" * 80)

        logging.info(f"Start: {summary['start_time'].strftime('%Y-%m-%d %H:%M:%S')}")
        logging.info(f"End:   {summary['end_time'].strftime('%Y-%m-%d %H:%M:%S')}")
        logging.info(f"Duration: {summary['total_duration'] / 60:.1f} minutes")
        logging.info(f"\nResults:")
        logging.info(f"  Total:   {summary['total']}")
        logging.info(f"  ✅ Passed:  {summary['passed']}")
        logging.info(f"  ❌ Failed:  {summary['failed']}")
        logging.info(f"  Success: {(summary['passed'] / summary['total'] * 100):.1f}%")

        if summary['failed'] > 0:
            logging.error(f"\n⚠️  FAILED LOADERS:")
            for loader in summary['failed_loaders']:
                logging.error(f"  • {loader}")

            logging.info(f"\n💡 RECOMMENDATIONS:")
            logging.info(f"  1. Check rate limit errors in logs above")
            logging.info(f"  2. Re-run in 'safe' or 'careful' mode with longer delays:")
            logging.info(f"     python3 orchestrate_statement_loaders.py --mode safe")
            logging.info(f"  3. Or re-run specific failed loader individually:")
            for loader in summary['failed_loaders']:
                script = loader.lower().replace(" ", "").replace("-", "").replace("(", "").replace(")", "") + ".py"
                logging.info(f"     python3 load{script.lower()}")
        else:
            logging.info(f"\n✅ ALL LOADERS COMPLETED SUCCESSFULLY")
            logging.info(f"   All statement data loaded without errors!")
            logging.info(f"   You can now proceed with score calculations")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Run statement loaders with monitoring and error detection"
    )
    parser.add_argument(
        "--mode",
        choices=["fast", "standard", "safe", "careful"],
        default="standard",
        help="Execution mode with different delays"
    )
    parser.add_argument(
        "--group",
        choices=["annual", "quarterly", "ttm", "earnings"],
        help="Run only specific group of loaders"
    )

    args = parser.parse_args()

    # Define all loaders
    all_loaders = [
        {"name": "Annual Balance Sheet", "script": "loadannualbalancesheet.py", "group": "annual"},
        {"name": "Quarterly Balance Sheet", "script": "loadquarterlybalancesheet.py", "group": "quarterly"},
        {"name": "Annual Income Statement", "script": "loadannualincomestatement.py", "group": "annual"},
        {"name": "Quarterly Income Statement", "script": "loadquarterlyincomestatement.py", "group": "quarterly"},
        {"name": "Annual Cash Flow", "script": "loadannualcashflow.py", "group": "annual"},
        {"name": "Quarterly Cash Flow", "script": "loadquarterlycashflow.py", "group": "quarterly"},
        {"name": "TTM Income Statement", "script": "loadttmincomestatement.py", "group": "ttm"},
        {"name": "TTM Cash Flow", "script": "loadttmcashflow.py", "group": "ttm"},
        {"name": "Earnings History", "script": "loadearningshistory.py", "group": "earnings"},
    ]

    # Filter by group if specified
    if args.group:
        loaders = [l for l in all_loaders if l["group"] == args.group]
    else:
        loaders = all_loaders

    # Run with monitoring
    monitor = LoaderMonitor(mode=args.mode)
    summary = monitor.run_all_loaders(loaders, mode=args.mode)
    monitor.print_summary(summary)

    sys.exit(0 if summary["failed"] == 0 else 1)
