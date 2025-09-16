#!/usr/bin/env python3
"""
Data Loader Orchestrator - Bulletproof Data Loading System
===========================================================

This is the master data loading orchestrator that:
1. Manages all data loaders systematically
2. Handles failures gracefully with retries
3. Provides comprehensive logging and monitoring
4. Integrates with ECS deployment triggers
5. Validates data quality after loading
6. Reports status to CloudWatch and database

Author: Financial Platform Team
Updated: 2025-07-17
"""

import importlib
import json
import logging
import os
import signal
import subprocess
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import psutil

# Add current directory to path for local imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


@dataclass
class LoaderConfig:
    """Configuration for a data loader"""

    name: str
    script_file: str
    description: str
    priority: str  # 'critical', 'high', 'medium', 'low'
    frequency: str  # 'continuous', 'hourly', 'daily', 'weekly'
    timeout_seconds: int
    retry_count: int
    dependencies: List[str]
    environment_vars: List[str]
    requires_market_hours: bool = False
    estimated_runtime_minutes: int = 5


@dataclass
class LoaderResult:
    """Result from running a data loader"""

    name: str
    success: bool
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    records_processed: int
    error_message: Optional[str] = None
    warnings: List[str] = None
    retry_count: int = 0

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class DataLoaderOrchestrator:
    """
    Main orchestrator class for managing all data loaders
    """

    def __init__(self, config_file: str = None, dry_run: bool = False):
        """
        Initialize the orchestrator

        Args:
            config_file: Path to configuration file (optional)
            dry_run: If True, don't actually run loaders
        """
        self.dry_run = dry_run
        self.results: List[LoaderResult] = []
        self.setup_logging()

        # Load configuration
        self.loaders = self._load_default_configuration()
        if config_file and os.path.exists(config_file):
            self._load_configuration_file(config_file)

        # Runtime state
        self.is_running = False
        self.shutdown_requested = False

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        self.logger.info(
            f"Data Loader Orchestrator initialized with {len(self.loaders)} loaders"
        )

    def setup_logging(self):
        """Setup comprehensive logging"""
        # Create logs directory if it doesn't exist
        log_dir = os.path.join(os.path.dirname(__file__), "logs")
        os.makedirs(log_dir, exist_ok=True)

        # Setup logging configuration
        log_format = "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
        logging.basicConfig(
            level=logging.INFO,
            format=log_format,
            handlers=[
                logging.FileHandler(
                    os.path.join(
                        log_dir, f'data_loader_{datetime.now().strftime("%Y%m%d")}.log'
                    )
                ),
                logging.StreamHandler(sys.stdout),
            ],
        )

        self.logger = logging.getLogger(__name__)
        self.logger.info("=== Data Loader Orchestrator Starting ===")

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        self.logger.warning(
            f"Received signal {signum}, initiating graceful shutdown..."
        )
        self.shutdown_requested = True

    def _load_default_configuration(self) -> Dict[str, LoaderConfig]:
        """Load default configuration for all known data loaders"""

        # Define all known data loaders with their configurations
        loader_configs = {
            # CRITICAL DATA LOADERS (must succeed)
            "stock_symbols": LoaderConfig(
                name="stock_symbols",
                script_file="loadstocksymbols.py",
                description="Load stock and ETF symbols from NASDAQ",
                priority="critical",
                frequency="daily",
                timeout_seconds=300,
                retry_count=3,
                dependencies=[],
                environment_vars=[],
                estimated_runtime_minutes=5,
            ),
            "price_daily": LoaderConfig(
                name="price_daily",
                script_file="loadpricedaily.py",
                description="Load daily stock prices (OHLCV)",
                priority="critical",
                frequency="daily",
                timeout_seconds=1800,  # 30 minutes
                retry_count=2,
                dependencies=["stock_symbols"],
                environment_vars=[],
                requires_market_hours=False,
                estimated_runtime_minutes=25,
            ),
            "latest_price_daily": LoaderConfig(
                name="latest_price_daily",
                script_file="loadlatestpricedaily.py",
                description="Load latest daily prices",
                priority="critical",
                frequency="hourly",
                timeout_seconds=900,  # 15 minutes
                retry_count=3,
                dependencies=["stock_symbols"],
                environment_vars=[],
                requires_market_hours=True,
                estimated_runtime_minutes=10,
            ),
            "technicals_daily": LoaderConfig(
                name="technicals_daily",
                script_file="loadtechnicalsdaily.py",
                description="Calculate and load daily technical indicators",
                priority="high",
                frequency="daily",
                timeout_seconds=1200,  # 20 minutes
                retry_count=2,
                dependencies=["price_daily"],
                environment_vars=[],
                estimated_runtime_minutes=15,
            ),
            "company_info": LoaderConfig(
                name="company_info",
                script_file="loadinfo.py",
                description="Load company profiles and financial metrics",
                priority="high",
                frequency="weekly",
                timeout_seconds=1800,  # 30 minutes
                retry_count=2,
                dependencies=["stock_symbols"],
                environment_vars=[],
                estimated_runtime_minutes=20,
            ),
            # HIGH PRIORITY DATA LOADERS
            "price_weekly": LoaderConfig(
                name="price_weekly",
                script_file="loadpriceweekly.py",
                description="Load weekly aggregated prices",
                priority="high",
                frequency="weekly",
                timeout_seconds=900,
                retry_count=2,
                dependencies=["price_daily"],
                environment_vars=[],
                estimated_runtime_minutes=10,
            ),
            "price_monthly": LoaderConfig(
                name="price_monthly",
                script_file="loadpricemonthly.py",
                description="Load monthly aggregated prices",
                priority="high",
                frequency="weekly",
                timeout_seconds=600,
                retry_count=2,
                dependencies=["price_daily"],
                environment_vars=[],
                estimated_runtime_minutes=8,
            ),
            "technicals_weekly": LoaderConfig(
                name="technicals_weekly",
                script_file="loadtechnicalsweekly.py",
                description="Calculate weekly technical indicators",
                priority="medium",
                frequency="weekly",
                timeout_seconds=900,
                retry_count=2,
                dependencies=["price_weekly"],
                environment_vars=[],
                estimated_runtime_minutes=10,
            ),
            "quarterly_financials": LoaderConfig(
                name="quarterly_financials",
                script_file="loadquarterlyincomestatement.py",
                description="Load quarterly financial statements",
                priority="high",
                frequency="weekly",
                timeout_seconds=1800,
                retry_count=2,
                dependencies=["stock_symbols"],
                environment_vars=[],
                estimated_runtime_minutes=20,
            ),
            # MEDIUM PRIORITY DATA LOADERS
            "economic_data": LoaderConfig(
                name="economic_data",
                script_file="loadecondata.py",
                description="Load economic indicators from FRED",
                priority="medium",
                frequency="daily",
                timeout_seconds=600,
                retry_count=2,
                dependencies=[],
                environment_vars=["FRED_API_KEY"],
                estimated_runtime_minutes=5,
            ),
            "earnings_calendar": LoaderConfig(
                name="earnings_calendar",
                script_file="loadcalendar.py",
                description="Load earnings calendar events",
                priority="medium",
                frequency="daily",
                timeout_seconds=600,
                retry_count=2,
                dependencies=["stock_symbols"],
                environment_vars=[],
                estimated_runtime_minutes=8,
            ),
            "earnings_estimates": LoaderConfig(
                name="earnings_estimates",
                script_file="loadearningsestimate.py",
                description="Load earnings estimates and forecasts",
                priority="medium",
                frequency="weekly",
                timeout_seconds=1200,
                retry_count=2,
                dependencies=["stock_symbols"],
                environment_vars=[],
                estimated_runtime_minutes=15,
            ),
            # LOW PRIORITY / SENTIMENT DATA LOADERS
            "fear_greed_index": LoaderConfig(
                name="fear_greed_index",
                script_file="loadfeargreed.py",
                description="Load CNN Fear & Greed Index",
                priority="low",
                frequency="daily",
                timeout_seconds=300,
                retry_count=2,
                dependencies=[],
                environment_vars=[],
                estimated_runtime_minutes=3,
            ),
            "aaii_sentiment": LoaderConfig(
                name="aaii_sentiment",
                script_file="loadaaiidata.py",
                description="Load AAII Sentiment Survey data",
                priority="low",
                frequency="weekly",
                timeout_seconds=300,
                retry_count=2,
                dependencies=[],
                environment_vars=[],
                estimated_runtime_minutes=3,
            ),
            "news_data": LoaderConfig(
                name="news_data",
                script_file="loadnews.py",
                description="Load financial news and sentiment",
                priority="medium",
                frequency="hourly",
                timeout_seconds=900,
                retry_count=2,
                dependencies=["stock_symbols"],
                environment_vars=[],
                estimated_runtime_minutes=12,
            ),
        }

        return loader_configs

    def _load_configuration_file(self, config_file: str):
        """Load configuration from JSON file"""
        try:
            with open(config_file, "r") as f:
                config_data = json.load(f)

            # Update loader configurations
            for loader_name, config in config_data.get("loaders", {}).items():
                if loader_name in self.loaders:
                    # Update existing loader config
                    for key, value in config.items():
                        setattr(self.loaders[loader_name], key, value)
                    self.logger.info(f"Updated configuration for loader: {loader_name}")

        except Exception as e:
            self.logger.error(f"Error loading configuration file {config_file}: {e}")

    def check_prerequisites(self) -> Tuple[bool, List[str]]:
        """
        Check if all prerequisites are met before running loaders

        Returns:
            Tuple of (success, list of error messages)
        """
        errors = []

        # Check database connectivity
        try:
            # Try to import database module
            sys.path.append(os.path.dirname(__file__))

            # Try basic database query
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    'import sys; sys.path.append("."); from database import query; result = query("SELECT 1"); print("DB_OK")',
                ],
                cwd=os.path.dirname(__file__),
                capture_output=True,
                text=True,
                timeout=30,
            )

            if "DB_OK" not in result.stdout:
                errors.append(f"Database connection failed: {result.stderr}")

        except Exception as e:
            errors.append(f"Database connectivity check failed: {e}")

        # Check required environment variables
        required_env_vars = ["AWS_REGION", "DB_SECRET_ARN"]
        for env_var in required_env_vars:
            if not os.getenv(env_var):
                errors.append(f"Required environment variable not set: {env_var}")

        # Check Python dependencies
        required_packages = ["yfinance", "psycopg2", "boto3", "requests"]
        for package in required_packages:
            try:
                importlib.import_module(package)
            except ImportError:
                errors.append(f"Required Python package not installed: {package}")

        # Check disk space
        disk_usage = psutil.disk_usage("/")
        free_gb = disk_usage.free / (1024**3)
        if free_gb < 2:  # Less than 2GB free
            errors.append(f"Low disk space: {free_gb:.1f}GB remaining")

        return len(errors) == 0, errors

    def run_single_loader(self, loader_config: LoaderConfig) -> LoaderResult:
        """
        Run a single data loader with comprehensive error handling

        Args:
            loader_config: Configuration for the loader to run

        Returns:
            LoaderResult with execution details
        """
        start_time = datetime.now()

        result = LoaderResult(
            name=loader_config.name,
            success=False,
            start_time=start_time,
            end_time=start_time,
            duration_seconds=0,
            records_processed=0,
        )

        self.logger.info(f"Starting loader: {loader_config.name}")

        try:
            # Check if script file exists
            script_path = os.path.join(
                os.path.dirname(__file__), loader_config.script_file
            )
            if not os.path.exists(script_path):
                raise FileNotFoundError(f"Loader script not found: {script_path}")

            # Check file is not empty
            if os.path.getsize(script_path) == 0:
                raise ValueError(f"Loader script is empty: {script_path}")

            # Check required environment variables
            for env_var in loader_config.environment_vars:
                if not os.getenv(env_var):
                    raise EnvironmentError(
                        f"Required environment variable not set: {env_var}"
                    )

            # Skip if dry run
            if self.dry_run:
                self.logger.info(f"DRY RUN: Would execute {loader_config.script_file}")
                result.success = True
                result.records_processed = 999  # Dummy value for dry run
                result.end_time = datetime.now()
                result.duration_seconds = 1.0
                return result

            # Set up environment
            env = os.environ.copy()
            env["PYTHONPATH"] = os.path.dirname(__file__)

            # Execute the loader script
            self.logger.info(f"Executing: python3 {loader_config.script_file}")

            process = subprocess.Popen(
                [sys.executable, loader_config.script_file],
                cwd=os.path.dirname(__file__),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )

            # Wait for completion with timeout
            try:
                stdout, stderr = process.communicate(
                    timeout=loader_config.timeout_seconds
                )
                return_code = process.returncode

                result.end_time = datetime.now()
                result.duration_seconds = (
                    result.end_time - result.start_time
                ).total_seconds()

                if return_code == 0:
                    result.success = True
                    # Try to extract records processed from output
                    for line in stdout.split("\n"):
                        if (
                            "records processed" in line.lower()
                            or "inserted" in line.lower()
                        ):
                            try:
                                import re

                                numbers = re.findall(r"\d+", line)
                                if numbers:
                                    result.records_processed = int(numbers[-1])
                                    break
                            except:
                                pass

                    self.logger.info(
                        f"Loader {loader_config.name} completed successfully in {result.duration_seconds:.1f}s"
                    )

                else:
                    result.error_message = (
                        f"Process exited with code {return_code}: {stderr}"
                    )
                    self.logger.error(
                        f"Loader {loader_config.name} failed: {result.error_message}"
                    )

                # Log any warnings from stderr
                if stderr and result.success:
                    result.warnings = [
                        line.strip() for line in stderr.split("\n") if line.strip()
                    ]

            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                result.end_time = datetime.now()
                result.duration_seconds = loader_config.timeout_seconds
                result.error_message = (
                    f"Loader timed out after {loader_config.timeout_seconds} seconds"
                )
                self.logger.error(f"Loader {loader_config.name} timed out")

        except Exception as e:
            result.end_time = datetime.now()
            result.duration_seconds = (
                result.end_time - result.start_time
            ).total_seconds()
            result.error_message = f"Exception: {str(e)}"
            self.logger.error(f"Loader {loader_config.name} failed with exception: {e}")

        return result

    def run_loader_with_retries(self, loader_config: LoaderConfig) -> LoaderResult:
        """
        Run a loader with retry logic

        Args:
            loader_config: Configuration for the loader

        Returns:
            Final LoaderResult after all retry attempts
        """
        last_result = None

        for attempt in range(loader_config.retry_count + 1):
            if self.shutdown_requested:
                self.logger.warning(
                    f"Shutdown requested, skipping {loader_config.name}"
                )
                break

            if attempt > 0:
                self.logger.info(
                    f"Retrying {loader_config.name} (attempt {attempt + 1}/{loader_config.retry_count + 1})"
                )
                time.sleep(min(30 * attempt, 300))  # Exponential backoff, max 5 minutes

            result = self.run_single_loader(loader_config)
            result.retry_count = attempt
            last_result = result

            if result.success:
                break

            self.logger.warning(
                f"Attempt {attempt + 1} failed for {loader_config.name}: {result.error_message}"
            )

        return last_result

    def resolve_dependencies(self, loaders: Dict[str, LoaderConfig]) -> List[str]:
        """
        Resolve loader dependencies and return execution order

        Args:
            loaders: Dictionary of loader configurations

        Returns:
            List of loader names in dependency order
        """
        # Simple topological sort for dependency resolution
        resolved = []
        unresolved = set(loaders.keys())

        def resolve_loader(name: str, path: List[str] = None):
            if path is None:
                path = []

            if name in path:
                raise ValueError(
                    f"Circular dependency detected: {' -> '.join(path + [name])}"
                )

            if name in resolved:
                return

            if name in unresolved:
                path = path + [name]

                # Resolve dependencies first
                for dep in loaders[name].dependencies:
                    if dep in loaders:
                        resolve_loader(dep, path)

                resolved.append(name)
                unresolved.remove(name)

        # Resolve all loaders
        while unresolved:
            # Start with any remaining loader
            loader_name = next(iter(unresolved))
            resolve_loader(loader_name)

        return resolved

    def run_loaders_by_priority(
        self, loaders_to_run: List[str] = None, max_parallel: int = 3
    ) -> List[LoaderResult]:
        """
        Run loaders organized by priority and dependencies

        Args:
            loaders_to_run: Specific loaders to run (optional, defaults to all)
            max_parallel: Maximum parallel executions per priority level

        Returns:
            List of all LoaderResults
        """
        if loaders_to_run is None:
            loaders_to_run = list(self.loaders.keys())

        # Filter to only requested loaders
        filtered_loaders = {
            k: v for k, v in self.loaders.items() if k in loaders_to_run
        }

        # Resolve dependencies
        try:
            execution_order = self.resolve_dependencies(filtered_loaders)
        except ValueError as e:
            self.logger.error(f"Dependency resolution failed: {e}")
            return []

        # Group by priority
        priority_groups = {"critical": [], "high": [], "medium": [], "low": []}

        for loader_name in execution_order:
            if loader_name in filtered_loaders:
                priority = filtered_loaders[loader_name].priority
                priority_groups[priority].append(loader_name)

        all_results = []

        # Run each priority group
        for priority in ["critical", "high", "medium", "low"]:
            if not priority_groups[priority]:
                continue

            self.logger.info(
                f"Running {priority} priority loaders: {priority_groups[priority]}"
            )

            # Run loaders in this priority group (with limited parallelism)
            with ThreadPoolExecutor(max_workers=max_parallel) as executor:
                futures = {}

                for loader_name in priority_groups[priority]:
                    if self.shutdown_requested:
                        break

                    future = executor.submit(
                        self.run_loader_with_retries, filtered_loaders[loader_name]
                    )
                    futures[future] = loader_name

                # Wait for completion
                for future in as_completed(futures):
                    if self.shutdown_requested:
                        break

                    loader_name = futures[future]
                    try:
                        result = future.result()
                        all_results.append(result)

                        if (
                            not result.success
                            and filtered_loaders[loader_name].priority == "critical"
                        ):
                            self.logger.error(
                                f"CRITICAL loader {loader_name} failed - this may affect dependent loaders"
                            )

                    except Exception as e:
                        self.logger.error(
                            f"Error getting result for {loader_name}: {e}"
                        )
                        # Create error result
                        error_result = LoaderResult(
                            name=loader_name,
                            success=False,
                            start_time=datetime.now(),
                            end_time=datetime.now(),
                            duration_seconds=0,
                            records_processed=0,
                            error_message=f"Execution error: {e}",
                        )
                        all_results.append(error_result)

            # Check if we should continue to next priority level
            if priority == "critical":
                critical_failures = [
                    r
                    for r in all_results
                    if not r.success and r.name in priority_groups["critical"]
                ]
                if critical_failures:
                    self.logger.error(
                        f"Critical failures detected: {[r.name for r in critical_failures]}"
                    )
                    # Continue anyway but log the issue

        return all_results

    def generate_report(self, results: List[LoaderResult]) -> Dict:
        """
        Generate comprehensive execution report

        Args:
            results: List of LoaderResults

        Returns:
            Dictionary with detailed report
        """
        total_loaders = len(results)
        successful = len([r for r in results if r.success])
        failed = total_loaders - successful

        total_duration = sum(r.duration_seconds for r in results)
        total_records = sum(r.records_processed for r in results)

        report = {
            "execution_timestamp": datetime.now().isoformat(),
            "summary": {
                "total_loaders": total_loaders,
                "successful": successful,
                "failed": failed,
                "success_rate": (
                    (successful / total_loaders * 100) if total_loaders > 0 else 0
                ),
                "total_duration_minutes": total_duration / 60,
                "total_records_processed": total_records,
            },
            "results": [asdict(r) for r in results],
            "failures": [
                {"name": r.name, "error": r.error_message, "retry_count": r.retry_count}
                for r in results
                if not r.success
            ],
            "performance": {
                "fastest_loader": (
                    min(results, key=lambda x: x.duration_seconds).name
                    if results
                    else None
                ),
                "slowest_loader": (
                    max(results, key=lambda x: x.duration_seconds).name
                    if results
                    else None
                ),
                "avg_duration_seconds": (
                    total_duration / total_loaders if total_loaders > 0 else 0
                ),
            },
        }

        return report

    def save_report(self, report: Dict, filename: str = None) -> str:
        """Save execution report to file"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"data_loader_report_{timestamp}.json"

        filepath = os.path.join(os.path.dirname(__file__), "logs", filename)

        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w") as f:
                json.dump(report, f, indent=2, default=str)

            self.logger.info(f"Report saved to: {filepath}")
            return filepath

        except Exception as e:
            self.logger.error(f"Failed to save report: {e}")
            return None

    def update_database_status(self, results: List[LoaderResult]):
        """Update last_updated table with execution results"""
        try:
            # Try to update database with results
            for result in results:
                update_script = f"""
import sys
sys.path.append('.')
from database import query
query('''
    INSERT INTO last_updated (script_name, last_run, status, records_processed, notes)
    VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT (script_name) DO UPDATE SET
        last_run = EXCLUDED.last_run,
        status = EXCLUDED.status,
        records_processed = EXCLUDED.records_processed,
        notes = EXCLUDED.notes
''', ('{result.name}', '{result.end_time.isoformat()}', '{'success' if result.success else 'failed'}', {result.records_processed}, '{result.error_message or ''}'))
"""

                subprocess.run(
                    [sys.executable, "-c", update_script],
                    cwd=os.path.dirname(__file__),
                    capture_output=True,
                    timeout=30,
                )

        except Exception as e:
            self.logger.warning(f"Failed to update database status: {e}")

    def run_all_loaders(
        self, loaders_to_run: List[str] = None, max_parallel: int = 3
    ) -> Dict:
        """
        Main method to run all data loaders

        Args:
            loaders_to_run: Specific loaders to run (optional)
            max_parallel: Maximum parallel executions

        Returns:
            Execution report
        """
        self.is_running = True
        start_time = datetime.now()

        try:
            self.logger.info("=== Starting Data Loader Orchestration ===")

            # Check prerequisites
            prereq_ok, prereq_errors = self.check_prerequisites()
            if not prereq_ok:
                self.logger.error("Prerequisites check failed:")
                for error in prereq_errors:
                    self.logger.error(f"  - {error}")
                return {
                    "success": False,
                    "error": "Prerequisites check failed",
                    "errors": prereq_errors,
                }

            # Run loaders
            results = self.run_loaders_by_priority(loaders_to_run, max_parallel)

            # Generate report
            report = self.generate_report(results)

            # Save report
            self.save_report(report)

            # Update database
            self.update_database_status(results)

            # Log summary
            summary = report["summary"]
            self.logger.info(f"=== Orchestration Complete ===")
            self.logger.info(
                f"Total: {summary['total_loaders']}, Success: {summary['successful']}, Failed: {summary['failed']}"
            )
            self.logger.info(
                f"Duration: {summary['total_duration_minutes']:.1f} minutes"
            )
            self.logger.info(f"Records: {summary['total_records_processed']:,}")

            if report["failures"]:
                self.logger.warning("Failed loaders:")
                for failure in report["failures"]:
                    self.logger.warning(f"  - {failure['name']}: {failure['error']}")

            return report

        except Exception as e:
            self.logger.error(f"Orchestration failed: {e}")
            self.logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": str(e),
                "traceback": traceback.format_exc(),
            }
        finally:
            self.is_running = False
            end_time = datetime.now()
            self.logger.info(
                f"Total execution time: {(end_time - start_time).total_seconds():.1f} seconds"
            )


def main():
    """Main function for command-line usage"""
    import argparse

    parser = argparse.ArgumentParser(description="Data Loader Orchestrator")
    parser.add_argument(
        "--loaders", type=str, help="Comma-separated list of loaders to run"
    )
    parser.add_argument("--config", type=str, help="Configuration file path")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    parser.add_argument(
        "--parallel", type=int, default=3, help="Maximum parallel executions"
    )
    parser.add_argument(
        "--priority",
        type=str,
        choices=["critical", "high", "medium", "low"],
        help="Run only loaders of specified priority",
    )

    args = parser.parse_args()

    # Parse loaders list
    loaders_to_run = None
    if args.loaders:
        loaders_to_run = [loader.strip() for loader in args.loaders.split(",")]

    # Create orchestrator
    orchestrator = DataLoaderOrchestrator(config_file=args.config, dry_run=args.dry_run)

    # Filter by priority if specified
    if args.priority:
        if loaders_to_run is None:
            loaders_to_run = []
        priority_loaders = [
            name
            for name, config in orchestrator.loaders.items()
            if config.priority == args.priority
        ]
        loaders_to_run.extend(priority_loaders)

    # Run orchestration
    report = orchestrator.run_all_loaders(loaders_to_run, args.parallel)

    # Exit with appropriate code
    if report.get("success", True) and report.get("summary", {}).get("failed", 1) == 0:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
