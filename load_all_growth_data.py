#!/usr/bin/env python3
"""
Master Growth Metrics Data Loader - Load ALL growth data systematically.

STRATEGY:
  1. Run upstream loaders SEQUENTIALLY (one at a time, not parallel)
  2. Each loader processes ALL symbols with batching
  3. Then load all growth metrics from available data
  4. Uses memory management to avoid context window errors

Usage:
  python3 load_all_growth_data.py [--stage 1|2|3|4|all]

  --stage 1   Run annual income statements only
  --stage 2   Run annual + quarterly income statements
  --stage 3   Run all financial statements (+ cash flow, balance sheet)
  --stage 4   Load all growth metrics from available data
  --stage all Run all stages in sequence (RECOMMENDED)

Timeline:
  Full run: ~3-4 hours
  Stage 1: ~45 min
  Stage 2: ~45 min
  Stage 3: ~45 min
  Stage 4: ~30 min
"""

import gc
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Work directory
WORK_DIR = Path(__file__).parent.absolute()

# Loader files to run (in order of importance)
LOADERS = {
    "stage_1": [
        ("loadannualincomestatement.py", "Annual Income Statements (4 years)"),
    ],
    "stage_2": [
        ("loadquarterlyincomestatement.py", "Quarterly Income Statements (8 quarters)"),
    ],
    "stage_3": [
        ("loadannualcashflow.py", "Annual Cash Flow (Free Cash Flow, OCF)"),
        ("loadannualbalancesheet.py", "Annual Balance Sheet (Total Assets)"),
        ("loadearningshistory.py", "Earnings History (EPS actual vs estimate)"),
    ],
    "stage_4": [
        ("selective_growth_loader.py --batch-size 500", "Growth Metrics Loader (All symbols)"),
    ],
}


class LoaderOrchestrator:
    """Orchestrates sequential loader execution with monitoring."""

    def __init__(self):
        self.execution_log = {
            "start_time": None,
            "end_time": None,
            "stages": {},
            "total_rows_loaded": 0,
            "errors": [],
        }

    def run_loader(self, loader_cmd: str, description: str) -> Tuple[bool, str]:
        """
        Run a single loader with output capture.

        Returns: (success, output_summary)
        """
        logger.info(f"\n{'='*80}")
        logger.info(f"🚀 RUNNING: {description}")
        logger.info(f"   Command: python3 {loader_cmd}")
        logger.info(f"{'='*80}")

        try:
            # Run loader
            start = time.time()
            result = subprocess.run(
                f"cd {WORK_DIR} && python3 {loader_cmd}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=3600,  # 1 hour timeout per loader
            )
            elapsed = time.time() - start

            # Capture output
            output = result.stdout + result.stderr
            success = result.returncode == 0

            # Log summary
            if success:
                logger.info(f"✅ COMPLETE in {elapsed:.1f}s")
            else:
                logger.warning(f"⚠️ FINISHED with issues in {elapsed:.1f}s")
                logger.warning(f"Return code: {result.returncode}")

            # Parse output for stats
            summary = self._extract_summary(output, description)

            # Force garbage collection
            gc.collect()
            time.sleep(2)

            return success, summary

        except subprocess.TimeoutExpired:
            logger.error(f"❌ TIMEOUT: {description} exceeded 1 hour")
            return False, "Timeout"
        except Exception as e:
            logger.error(f"❌ ERROR: {description} - {e}")
            return False, str(e)

    def _extract_summary(self, output: str, description: str) -> str:
        """Extract key stats from loader output."""
        summary = []

        # Look for common log patterns
        for line in output.split("\n"):
            if any(keyword in line.lower() for keyword in ["✅", "inserted", "updated", "rows", "symbols", "processed", "complete"]):
                if line.strip():
                    summary.append(line.strip())

        if not summary:
            summary.append(description)

        return " | ".join(summary[-3:])  # Return last 3 summary lines

    def run_stage(self, stage_name: str) -> bool:
        """Run all loaders in a stage."""
        logger.info(f"\n\n{'#'*80}")
        logger.info(f"# STAGE: {stage_name.upper()}")
        logger.info(f"{'#'*80}\n")

        loaders = LOADERS.get(stage_name, [])
        stage_results = {
            "start_time": datetime.now().isoformat(),
            "loaders": {},
            "success_count": 0,
            "error_count": 0,
        }

        for loader_cmd, description in loaders:
            success, summary = self.run_loader(loader_cmd, description)

            stage_results["loaders"][description] = {
                "success": success,
                "summary": summary,
            }

            if success:
                stage_results["success_count"] += 1
            else:
                stage_results["error_count"] += 1
                self.execution_log["errors"].append(f"{stage_name}: {description}")

            # Brief pause between loaders
            time.sleep(1)

        stage_results["end_time"] = datetime.now().isoformat()
        self.execution_log["stages"][stage_name] = stage_results

        return stage_results["error_count"] == 0

    def run_all_stages(self):
        """Run all stages in sequence."""
        self.execution_log["start_time"] = datetime.now().isoformat()

        stages = ["stage_1", "stage_2", "stage_3", "stage_4"]
        results = {}

        for stage in stages:
            logger.info(f"\n🔄 Starting {stage}...")
            success = self.run_stage(stage)
            results[stage] = success

            if not success:
                logger.warning(f"⚠️ {stage} had errors - continuing anyway...")

            # Pause between stages
            time.sleep(5)

        self.execution_log["end_time"] = datetime.now().isoformat()

        # Final summary
        self._print_summary(results)

    def _print_summary(self, results: Dict[str, bool]):
        """Print execution summary."""
        print(f"\n\n{'='*80}")
        print("📊 EXECUTION SUMMARY")
        print(f"{'='*80}\n")

        for stage_name, success in results.items():
            status = "✅ PASSED" if success else "⚠️ ISSUES"
            stage_data = self.execution_log["stages"].get(stage_name, {})
            loaders = stage_data.get("loaders", {})

            print(f"{status} - {stage_name.upper()}")
            for loader_name, loader_result in loaders.items():
                symbol = "✅" if loader_result["success"] else "❌"
                print(f"  {symbol} {loader_name}")
                if loader_result["summary"]:
                    print(f"     {loader_result['summary'][:100]}")

        print(f"\n{'='*80}")
        print(f"Start: {self.execution_log['start_time']}")
        print(f"End:   {self.execution_log['end_time']}")

        if self.execution_log["errors"]:
            print(f"\n⚠️ ERRORS ({len(self.execution_log['errors'])}):")
            for error in self.execution_log["errors"][:5]:
                print(f"   - {error}")

        print(f"{'='*80}\n")

        # Save execution log
        log_file = WORK_DIR / "load_all_growth_data_execution.json"
        with open(log_file, "w") as f:
            json.dump(self.execution_log, f, indent=2, default=str)
        logger.info(f"✅ Execution log saved: {log_file}")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Load all growth metrics data sequentially"
    )
    parser.add_argument(
        "--stage",
        choices=["1", "2", "3", "4", "all"],
        default="all",
        help="Which stage to run (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would run, don't actually run",
    )

    args = parser.parse_args()

    # Check environment
    if not Path(WORK_DIR / ".env.local").exists():
        logger.error("❌ .env.local not found - cannot connect to database")
        sys.exit(1)

    # Show plan
    if args.stage == "all":
        print(f"\n{'='*80}")
        print("📋 EXECUTION PLAN: ALL STAGES")
        print(f"{'='*80}\n")
        print("Stage 1: Load Annual Income Statements (~5,000 symbols)")
        print("  └─ Provides: Revenue, EPS, Operating Income (4 years)")
        print("  └─ Time: ~45 min\n")

        print("Stage 2: Load Quarterly Income Statements (~4,800 symbols)")
        print("  └─ Provides: Quarterly growth momentum (8 quarters)")
        print("  └─ Time: ~45 min\n")

        print("Stage 3: Load Supporting Financial Data")
        print("  ├─ Annual Cash Flow (~4,600 symbols)")
        print("  ├─ Annual Balance Sheet (~3,500 symbols)")
        print("  └─ Earnings History (~3,300 symbols)")
        print("  └─ Time: ~45 min\n")

        print("Stage 4: Load All Growth Metrics")
        print("  └─ Uses all available upstream data")
        print("  └─ Batches in 500-symbol chunks")
        print("  └─ Time: ~30 min\n")

        print(f"Total Time: ~3.5 hours")
        print(f"Expected Additional Symbols: ~10,000-15,000")
        print(f"Expected Coverage Improvement: ~4% → ~20%\n")
        print(f"{'='*80}\n")

        if args.dry_run:
            logger.info("DRY RUN - Not executing")
            return

        # Confirm
        response = input("📌 Ready to start? Type 'yes' to proceed: ").strip().lower()
        if response != "yes":
            logger.info("Cancelled by user")
            return

    # Run
    orchestrator = LoaderOrchestrator()

    if args.stage == "all":
        orchestrator.run_all_stages()
    else:
        stage_map = {
            "1": "stage_1",
            "2": "stage_2",
            "3": "stage_3",
            "4": "stage_4",
        }
        stage = stage_map[args.stage]
        orchestrator.run_stage(stage)
        orchestrator._print_summary({stage: True})


if __name__ == "__main__":
    main()
