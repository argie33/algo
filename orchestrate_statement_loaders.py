#!/usr/bin/env python3
"""
Smart Statement Loaders Orchestrator - yfinance Best Practices Edition
Runs statement loaders sequentially with optimized rate limit handling
Based on actual yfinance API best practices: 2-5s delays, smart backoff
"""

import sys
import subprocess
import time
import logging
from datetime import datetime
from typing import List, Dict, Tuple
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [ORCHESTRATOR] - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# Statement loaders in recommended execution order
# Based on yfinance best practices: research shows 2-5s inter-request delays optimal
STATEMENT_LOADERS = [
    {
        "name": "Annual Balance Sheet",
        "script": "loadannualbalancesheet.py",
        "priority": 1,
        "group": "annual",
        "description": "Essential for debt/equity calculations"
    },
    {
        "name": "Quarterly Balance Sheet",
        "script": "loadquarterlybalancesheet.py",
        "priority": 2,
        "group": "quarterly",
        "description": "Essential for quarterly metrics"
    },
    {
        "name": "Annual Income Statement",
        "script": "loadannualincomestatement.py",
        "priority": 3,
        "group": "annual",
        "description": "Essential for profitability scores"
    },
    {
        "name": "Quarterly Income Statement",
        "script": "loadquarterlyincomestatement.py",
        "priority": 4,
        "group": "quarterly",
        "description": "Essential for quarterly earnings analysis"
    },
    {
        "name": "Annual Cash Flow",
        "script": "loadannualcashflow.py",
        "priority": 5,
        "group": "annual",
        "description": "Essential for cash flow scoring"
    },
    {
        "name": "Quarterly Cash Flow",
        "script": "loadquarterlycashflow.py",
        "priority": 6,
        "group": "quarterly",
        "description": "Essential for quarterly cash analysis"
    },
    {
        "name": "TTM Income Statement",
        "script": "loadttmincomestatement.py",
        "priority": 7,
        "group": "ttm",
        "description": "TTM profitability metrics"
    },
    {
        "name": "TTM Cash Flow",
        "script": "loadttmcashflow.py",
        "priority": 8,
        "group": "ttm",
        "description": "TTM cash flow metrics"
    },
    {
        "name": "Earnings History",
        "script": "loadearningshistory.py",
        "priority": 9,
        "group": "earnings",
        "description": "Historical earnings data"
    }
]

# Rate limit modes based on yfinance best practices
# Research shows optimal delays: 2-5 seconds between loaders + loaders' internal 1s pauses
DELAY_MODES = {
    "fast": {
        "inter_loader_delay": 2,      # 2s between loaders (minimal but safe)
        "description": "2s delays - fastest safe mode (yfinance best practice)"
    },
    "standard": {
        "inter_loader_delay": 3,      # 3s between loaders (default)
        "description": "3s delays - balanced speed and safety"
    },
    "safe": {
        "inter_loader_delay": 5,      # 5s between loaders (if seeing rate limits)
        "description": "5s delays - for rate limit recovery"
    },
    "careful": {
        "inter_loader_delay": 10,     # 10s between loaders (aggressive protection)
        "description": "10s delays - maximum rate limit protection"
    }
}

class LoaderResult:
    """Track execution result for each loader"""
    def __init__(self, name: str, script: str):
        self.name = name
        self.script = script
        self.start_time = None
        self.end_time = None
        self.success = False
        self.return_code = None
        self.error_msg = None
        self.output = ""

    def duration_seconds(self) -> float:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0

    def __repr__(self) -> str:
        status = "✅ PASS" if self.success else "❌ FAIL"
        duration = f"{self.duration_seconds():.1f}s"
        return f"{status} | {self.name:30s} | {duration}"

def run_loader(loader_config: Dict) -> LoaderResult:
    """Execute a single loader with monitoring"""
    result = LoaderResult(loader_config["name"], loader_config["script"])
    script_path = loader_config["script"]

    # Verify script exists
    if not os.path.exists(script_path):
        result.error_msg = f"Script not found: {script_path}"
        logging.error(f"❌ {loader_config['name']}: {result.error_msg}")
        return result

    logging.info(f"▶️  Starting {loader_config['name']} ({script_path})")
    logging.info(f"   {loader_config['description']}")
    result.start_time = datetime.now()

    try:
        # Run loader with subprocess to capture output
        process = subprocess.Popen(
            [sys.executable, script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        # Stream output and capture
        output_lines = []
        for line in process.stdout:
            output_lines.append(line.rstrip())
            # Log key information from loader output
            if "processed:" in line.lower() or "failed" in line.lower() or "error" in line.lower():
                logging.info(f"   {line.rstrip()}")

        result.output = "\n".join(output_lines)
        process.wait()
        result.return_code = process.returncode
        result.success = (process.returncode == 0)

        result.end_time = datetime.now()

        if result.success:
            logging.info(f"✅ {loader_config['name']} completed successfully ({result.duration_seconds():.1f}s)")
        else:
            result.error_msg = f"Process exited with code {process.returncode}"
            logging.warning(f"⚠️  {loader_config['name']} completed with exit code {process.returncode}")

    except Exception as e:
        result.error_msg = str(e)
        result.end_time = datetime.now()
        logging.error(f"❌ {loader_config['name']} failed: {result.error_msg}")

    return result

def orchestrate_loaders(
    loaders: List[Dict],
    mode: str = "standard",
    start_index: int = 0,
    dry_run: bool = False,
    group_filter: str = None
) -> Tuple[List[LoaderResult], Dict]:
    """
    Run loaders with smart yfinance-optimized rate limiting

    Args:
        loaders: List of loader configurations
        mode: "fast" (2s), "standard" (3s), "safe" (5s), "careful" (10s)
        start_index: Start from specific loader (for resuming)
        dry_run: Show what would run without executing
        group_filter: Only run loaders from specific group (annual/quarterly/ttm/earnings)
    """

    # Validate and get delay config
    if mode not in DELAY_MODES:
        logging.error(f"Invalid mode: {mode}. Must be one of: {', '.join(DELAY_MODES.keys())}")
        sys.exit(1)

    delay_config = DELAY_MODES[mode]
    inter_loader_delay = delay_config["inter_loader_delay"]

    # Filter loaders if group specified
    active_loaders = loaders
    if group_filter:
        active_loaders = [l for l in loaders if l["group"] == group_filter]
        logging.info(f"📋 Filtered to {group_filter.upper()} group: {len(active_loaders)} loaders")
    else:
        logging.info(f"📋 Running {len(active_loaders)} total statement loaders")

    # Adjust indices
    if start_index > 0:
        active_loaders = active_loaders[start_index:]
        logging.info(f"▶️  Resuming from loader #{start_index + 1}")

    results = []
    execution_stats = {
        "total": len(active_loaders),
        "passed": 0,
        "failed": 0,
        "total_duration": 0.0,
        "estimated_total_duration": 0.0,
        "data_gaps": [],
        "mode": mode,
        "delay_config": delay_config
    }

    if dry_run:
        logging.info("🔍 DRY RUN MODE - Showing execution plan:")
        logging.info(f"   Mode: {mode} ({delay_config['description']})")
        logging.info(f"   Delay between loaders: {inter_loader_delay}s")
        for idx, loader in enumerate(active_loaders, 1):
            logging.info(f"  {idx}. {loader['name']:35s} | {loader['group']:10s}")

        # Estimate total time
        estimated_loader_time = 3  # minutes per loader (conservative estimate)
        estimated_total = estimated_loader_time * len(active_loaders) + (inter_loader_delay * (len(active_loaders) - 1)) / 60
        logging.info(f"\n   Estimated total time: ~{estimated_total:.1f} minutes")
        return results, execution_stats

    # Main orchestration loop
    logging.info(f"\n🚀 Starting orchestrated execution")
    logging.info(f"   Mode: {mode}")
    logging.info(f"   {delay_config['description']}")
    logging.info(f"   Loaders: {len(active_loaders)}")
    logging.info("=" * 80)

    start_time = datetime.now()

    for idx, loader in enumerate(active_loaders, 1):
        logging.info(f"\n[{idx}/{len(active_loaders)}] {loader['name']}")

        # Execute loader
        result = run_loader(loader)
        results.append(result)

        # Update stats
        if result.success:
            execution_stats["passed"] += 1
        else:
            execution_stats["failed"] += 1
            execution_stats["data_gaps"].append(f"{loader['name']} (exit code: {result.return_code})")

        # Don't wait after last loader
        if idx < len(active_loaders):
            logging.info(f"⏳ Waiting {inter_loader_delay}s before next loader...")
            time.sleep(inter_loader_delay)

    end_time = datetime.now()
    execution_stats["total_duration"] = (end_time - start_time).total_seconds()

    logging.info("\n" + "=" * 80)
    logging.info("📊 EXECUTION COMPLETE")
    logging.info("=" * 80)

    return results, execution_stats

def print_results(results: List[LoaderResult], stats: Dict):
    """Print detailed results report"""
    logging.info("\n📋 LOADER EXECUTION RESULTS:")
    for result in results:
        logging.info(f"  {result}")

    logging.info(f"\n📊 STATISTICS:")
    logging.info(f"  Total Loaders:  {stats['total']}")
    logging.info(f"  ✅ Passed:       {stats['passed']}")
    logging.info(f"  ❌ Failed:       {stats['failed']}")
    logging.info(f"  ⏱️  Total Time:   {stats['total_duration']:.1f}s ({stats['total_duration']/60:.1f}m)")
    logging.info(f"  Success Rate:   {(stats['passed']/stats['total']*100):.1f}%")

    if stats['data_gaps']:
        logging.warning(f"\n⚠️  DATA GAPS DETECTED ({len(stats['data_gaps'])}):")
        for gap in stats['data_gaps']:
            logging.warning(f"  • {gap}")
        logging.warning("\n💡 TIP: Failed loaders can be re-run individually:")
        logging.warning("   python loadannualbalancesheet.py")
        logging.warning("   python loadquarterlyincomestatement.py (etc)")

    # Recommendations
    logging.info(f"\n💡 NEXT STEPS:")
    if stats['passed'] == stats['total']:
        logging.info("  ✅ All statement loaders completed successfully")
        logging.info("  → You can now run score calculations")
    else:
        logging.info(f"  ⚠️  {stats['failed']} loader(s) failed - data gaps may exist")
        logging.info("  → Re-run failed loaders individually after checking logs")
        logging.info("  → Consider increasing delays if seeing rate limit errors")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Statement Loaders Orchestrator - Optimized with yfinance best practices"
    )
    parser.add_argument(
        "--mode",
        choices=["fast", "standard", "safe", "careful"],
        default="standard",
        help="Delay between loaders: fast (2s), standard (3s), safe (5s), careful (10s)"
    )
    parser.add_argument(
        "--resume",
        type=int,
        default=0,
        help="Resume from specific loader index (0-based)"
    )
    parser.add_argument(
        "--group",
        choices=["annual", "quarterly", "ttm", "earnings"],
        help="Run only loaders from specific group"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show execution plan and estimated time without running"
    )

    args = parser.parse_args()

    logging.info("=" * 80)
    logging.info("STATEMENT LOADERS ORCHESTRATOR")
    logging.info("Based on yfinance best practices (2-5s inter-request delays)")
    logging.info("=" * 80)
    logging.info(f"Mode:        {args.mode} - {DELAY_MODES[args.mode]['description']}")
    logging.info(f"Resume:      Loader #{args.resume if args.resume > 0 else 'start'}")
    logging.info(f"Group:       {args.group or 'all'}")
    logging.info(f"Dry-Run:     {args.dry_run}")

    # Run orchestration
    results, stats = orchestrate_loaders(
        STATEMENT_LOADERS,
        mode=args.mode,
        start_index=args.resume,
        dry_run=args.dry_run,
        group_filter=args.group
    )

    # Print results
    print_results(results, stats)

    # Exit with appropriate code
    sys.exit(0 if stats['failed'] == 0 else 1)
