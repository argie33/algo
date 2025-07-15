#!/usr/bin/env python3
"""
Data Loader Coordinator and Health Monitor
Manages multiple data loaders with dependency resolution, health monitoring,
and comprehensive performance tracking.
"""

import os
import sys
import json
import time
import logging
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
import concurrent.futures
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/tmp/data_loader_coordinator.log', mode='a')
    ]
)
logger = logging.getLogger(__name__)

class LoaderStatus(Enum):
    """Status enumeration for data loaders."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

@dataclass
class LoaderConfig:
    """Configuration for a data loader."""
    name: str
    description: str
    script_path: str
    table_name: str
    dependencies: List[str]
    critical: bool
    timeout_minutes: int = 30
    retry_count: int = 2
    enabled: bool = True

@dataclass
class LoaderResult:
    """Result from a data loader execution."""
    name: str
    status: LoaderStatus
    start_time: datetime
    end_time: Optional[datetime]
    duration_seconds: float
    records_processed: int
    records_inserted: int
    records_failed: int
    error_message: Optional[str]
    metrics: Dict[str, Any]

class DataLoaderCoordinator:
    """
    Coordinates multiple data loaders with dependency management and health monitoring.
    """
    
    def __init__(self, config_file: str = None):
        """
        Initialize the data loader coordinator.
        
        Args:
            config_file: Path to loader configuration file
        """
        self.start_time = datetime.now()
        self.loaders: Dict[str, LoaderConfig] = {}
        self.results: Dict[str, LoaderResult] = {}
        self.execution_order: List[str] = []
        
        # Load configuration
        if config_file and os.path.exists(config_file):
            self._load_config_from_file(config_file)
        else:
            self._load_default_config()
        
        logger.info(f"🚀 Data Loader Coordinator initialized with {len(self.loaders)} loaders")
    
    def _load_default_config(self):
        """Load default loader configuration."""
        default_loaders = [
            # Core foundational data (highest priority)
            LoaderConfig(
                name="stock_symbols",
                description="Stock and ETF symbols from exchanges",
                script_path="loadstocksymbols_optimized.py",
                table_name="stock_symbols",
                dependencies=[],
                critical=True,
                timeout_minutes=15
            ),
            
            # Price data (depends on symbols)
            LoaderConfig(
                name="price_daily",
                description="Daily stock prices (OHLCV)",
                script_path="loadpricedaily.py",
                table_name="price_daily",
                dependencies=["stock_symbols"],
                critical=True,
                timeout_minutes=45
            ),
            
            LoaderConfig(
                name="latest_price_daily",
                description="Latest daily price data",
                script_path="loadlatestpricedaily.py",
                table_name="latest_price_daily",
                dependencies=["price_daily"],
                critical=True,
                timeout_minutes=20
            ),
            
            # Technical analysis (depends on price data)
            LoaderConfig(
                name="technicals_daily",
                description="Daily technical indicators",
                script_path="loadtechnicalsdaily.py",
                table_name="technicals_daily",
                dependencies=["price_daily"],
                critical=True,
                timeout_minutes=30
            ),
            
            # Company information (can run in parallel with price data)
            LoaderConfig(
                name="company_info",
                description="Company profiles and basic financials",
                script_path="loadinfo.py",
                table_name="company_profile",
                dependencies=["stock_symbols"],
                critical=True,
                timeout_minutes=25
            ),
            
            # Financial statements (depends on company info)
            LoaderConfig(
                name="annual_balance_sheet",
                description="Annual balance sheet data",
                script_path="loadannualbalancesheet.py",
                table_name="annual_balance_sheet",
                dependencies=["company_info"],
                critical=False,
                timeout_minutes=35
            ),
            
            LoaderConfig(
                name="annual_income_statement",
                description="Annual income statement data",
                script_path="loadannualincomestatement.py",
                table_name="annual_income_stmt",
                dependencies=["company_info"],
                critical=False,
                timeout_minutes=35
            ),
            
            # Advanced analytics (depends on multiple sources)
            LoaderConfig(
                name="scores",
                description="Stock scoring and analytics",
                script_path="loadscores.py",
                table_name="scores",
                dependencies=["technicals_daily", "company_info"],
                critical=False,
                timeout_minutes=40
            ),
            
            # Market sentiment and news (can run independently)
            LoaderConfig(
                name="sentiment",
                description="Market sentiment data",
                script_path="loadsentiment.py",
                table_name="sentiment",
                dependencies=[],
                critical=False,
                timeout_minutes=20
            ),
            
            LoaderConfig(
                name="news",
                description="Financial news and analysis",
                script_path="loadnews.py",
                table_name="news",
                dependencies=[],
                critical=False,
                timeout_minutes=25
            )
        ]
        
        self.loaders = {loader.name: loader for loader in default_loaders}
        logger.info(f"✅ Loaded {len(self.loaders)} default loader configurations")
    
    def _load_config_from_file(self, config_file: str):
        """Load loader configuration from JSON file."""
        try:
            with open(config_file, 'r') as f:
                config_data = json.load(f)
            
            for loader_data in config_data.get('loaders', []):
                loader = LoaderConfig(**loader_data)
                self.loaders[loader.name] = loader
            
            logger.info(f"✅ Loaded {len(self.loaders)} loaders from {config_file}")
            
        except Exception as e:
            logger.error(f"❌ Failed to load config from {config_file}: {e}")
            self._load_default_config()
    
    def _resolve_dependencies(self) -> List[str]:
        """
        Resolve loader dependencies and return execution order.
        
        Returns:
            List of loader names in dependency-resolved order
        """
        execution_order = []
        resolved = set()
        pending = set(self.loaders.keys())
        
        while pending:
            # Find loaders with satisfied dependencies
            ready = []
            for loader_name in pending:
                loader = self.loaders[loader_name]
                if not loader.enabled:
                    continue
                
                deps_satisfied = all(dep in resolved for dep in loader.dependencies)
                if deps_satisfied:
                    ready.append(loader_name)
            
            if not ready:
                # Circular dependency or missing dependency
                remaining = [name for name in pending if self.loaders[name].enabled]
                if remaining:
                    logger.warning(f"⚠️ Circular or missing dependencies detected for: {remaining}")
                    # Add them anyway to avoid infinite loop
                    ready = remaining[:1]  # Add one to break the cycle
                else:
                    break
            
            # Add ready loaders to execution order
            for loader_name in ready:
                execution_order.append(loader_name)
                resolved.add(loader_name)
                pending.remove(loader_name)
        
        self.execution_order = execution_order
        logger.info(f"📋 Execution order resolved: {' → '.join(execution_order)}")
        return execution_order
    
    def _execute_loader(self, loader_name: str) -> LoaderResult:
        """
        Execute a single data loader.
        
        Args:
            loader_name: Name of the loader to execute
            
        Returns:
            LoaderResult with execution details
        """
        loader = self.loaders[loader_name]
        start_time = datetime.now()
        
        logger.info(f"🔄 Starting loader: {loader_name}")
        
        result = LoaderResult(
            name=loader_name,
            status=LoaderStatus.RUNNING,
            start_time=start_time,
            end_time=None,
            duration_seconds=0,
            records_processed=0,
            records_inserted=0,
            records_failed=0,
            error_message=None,
            metrics={}
        )
        
        try:
            # Check if script exists
            if not os.path.exists(loader.script_path):
                raise FileNotFoundError(f"Script not found: {loader.script_path}")
            
            # Execute the loader script
            import subprocess
            
            cmd = [sys.executable, loader.script_path]
            timeout_seconds = loader.timeout_minutes * 60
            
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                cwd=os.path.dirname(os.path.abspath(__file__))
            )
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            if process.returncode == 0:
                result.status = LoaderStatus.COMPLETED
                result.end_time = end_time
                result.duration_seconds = duration
                
                # Try to parse metrics from output
                try:
                    # Look for JSON metrics in stdout
                    lines = process.stdout.split('\n')
                    for line in lines:
                        if 'records_processed' in line or 'Final Metrics' in line:
                            # Try to extract metrics
                            pass  # Could parse specific metrics here
                except:
                    pass
                
                logger.info(f"✅ Loader {loader_name} completed successfully in {duration:.2f}s")
                
            else:
                result.status = LoaderStatus.FAILED
                result.end_time = end_time
                result.duration_seconds = duration
                result.error_message = process.stderr or "Unknown error"
                
                logger.error(f"❌ Loader {loader_name} failed: {result.error_message}")
        
        except subprocess.TimeoutExpired:
            result.status = LoaderStatus.FAILED
            result.end_time = datetime.now()
            result.duration_seconds = loader.timeout_minutes * 60
            result.error_message = f"Timeout after {loader.timeout_minutes} minutes"
            
            logger.error(f"⏰ Loader {loader_name} timed out after {loader.timeout_minutes} minutes")
        
        except Exception as e:
            result.status = LoaderStatus.FAILED
            result.end_time = datetime.now()
            result.duration_seconds = (result.end_time - start_time).total_seconds()
            result.error_message = str(e)
            
            logger.error(f"❌ Loader {loader_name} failed with exception: {e}")
        
        return result
    
    def run_sequential(self, critical_only: bool = False) -> Dict[str, Any]:
        """
        Run data loaders sequentially in dependency order.
        
        Args:
            critical_only: If True, only run critical loaders
            
        Returns:
            Summary of execution results
        """
        logger.info("🚀 Starting sequential data loader execution")
        
        execution_order = self._resolve_dependencies()
        
        if critical_only:
            execution_order = [name for name in execution_order if self.loaders[name].critical]
            logger.info(f"🎯 Running critical loaders only: {len(execution_order)} loaders")
        
        successful_loaders = []
        failed_loaders = []
        
        for loader_name in execution_order:
            loader = self.loaders[loader_name]
            
            # Check if dependencies succeeded (for non-critical loaders)
            if loader.dependencies and not loader.critical:
                deps_failed = any(
                    dep in failed_loaders for dep in loader.dependencies
                )
                if deps_failed:
                    logger.warning(f"⏭️ Skipping {loader_name} due to failed dependencies")
                    self.results[loader_name] = LoaderResult(
                        name=loader_name,
                        status=LoaderStatus.SKIPPED,
                        start_time=datetime.now(),
                        end_time=datetime.now(),
                        duration_seconds=0,
                        records_processed=0,
                        records_inserted=0,
                        records_failed=0,
                        error_message="Skipped due to failed dependencies",
                        metrics={}
                    )
                    continue
            
            # Execute the loader
            result = self._execute_loader(loader_name)
            self.results[loader_name] = result
            
            if result.status == LoaderStatus.COMPLETED:
                successful_loaders.append(loader_name)
            else:
                failed_loaders.append(loader_name)
                
                # Stop execution if critical loader fails
                if loader.critical:
                    logger.error(f"💥 Critical loader {loader_name} failed, stopping execution")
                    break
        
        # Generate execution summary
        total_duration = (datetime.now() - self.start_time).total_seconds()
        
        summary = {
            'execution_type': 'sequential',
            'start_time': self.start_time.isoformat(),
            'end_time': datetime.now().isoformat(),
            'total_duration_seconds': total_duration,
            'loaders_attempted': len(execution_order),
            'loaders_successful': len(successful_loaders),
            'loaders_failed': len(failed_loaders),
            'success_rate': len(successful_loaders) / len(execution_order) if execution_order else 0,
            'successful_loaders': successful_loaders,
            'failed_loaders': failed_loaders,
            'results': {name: asdict(result) for name, result in self.results.items()}
        }
        
        self._log_execution_summary(summary)
        return summary
    
    def run_parallel(self, max_workers: int = 3, critical_only: bool = False) -> Dict[str, Any]:
        """
        Run data loaders in parallel respecting dependencies.
        
        Args:
            max_workers: Maximum number of parallel workers
            critical_only: If True, only run critical loaders
            
        Returns:
            Summary of execution results
        """
        logger.info(f"🚀 Starting parallel data loader execution with {max_workers} workers")
        
        execution_order = self._resolve_dependencies()
        
        if critical_only:
            execution_order = [name for name in execution_order if self.loaders[name].critical]
            logger.info(f"🎯 Running critical loaders only: {len(execution_order)} loaders")
        
        # Group loaders by dependency level
        dependency_levels = self._group_by_dependency_level(execution_order)
        
        successful_loaders = []
        failed_loaders = []
        
        # Execute each dependency level in parallel
        for level, loader_names in dependency_levels.items():
            logger.info(f"📊 Executing dependency level {level}: {loader_names}")
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_loader = {
                    executor.submit(self._execute_loader, name): name
                    for name in loader_names
                }
                
                for future in concurrent.futures.as_completed(future_to_loader):
                    loader_name = future_to_loader[future]
                    try:
                        result = future.result()
                        self.results[loader_name] = result
                        
                        if result.status == LoaderStatus.COMPLETED:
                            successful_loaders.append(loader_name)
                        else:
                            failed_loaders.append(loader_name)
                            
                    except Exception as e:
                        logger.error(f"❌ Parallel execution error for {loader_name}: {e}")
                        failed_loaders.append(loader_name)
        
        # Generate execution summary
        total_duration = (datetime.now() - self.start_time).total_seconds()
        
        summary = {
            'execution_type': 'parallel',
            'max_workers': max_workers,
            'start_time': self.start_time.isoformat(),
            'end_time': datetime.now().isoformat(),
            'total_duration_seconds': total_duration,
            'loaders_attempted': len(execution_order),
            'loaders_successful': len(successful_loaders),
            'loaders_failed': len(failed_loaders),
            'success_rate': len(successful_loaders) / len(execution_order) if execution_order else 0,
            'successful_loaders': successful_loaders,
            'failed_loaders': failed_loaders,
            'dependency_levels': dependency_levels,
            'results': {name: asdict(result) for name, result in self.results.items()}
        }
        
        self._log_execution_summary(summary)
        return summary
    
    def _group_by_dependency_level(self, execution_order: List[str]) -> Dict[int, List[str]]:
        """Group loaders by dependency level for parallel execution."""
        levels = {}
        loader_levels = {}
        
        # Calculate dependency level for each loader
        for loader_name in execution_order:
            level = self._calculate_dependency_level(loader_name, loader_levels)
            loader_levels[loader_name] = level
            
            if level not in levels:
                levels[level] = []
            levels[level].append(loader_name)
        
        return levels
    
    def _calculate_dependency_level(self, loader_name: str, calculated_levels: Dict[str, int]) -> int:
        """Calculate the dependency level for a loader."""
        if loader_name in calculated_levels:
            return calculated_levels[loader_name]
        
        loader = self.loaders[loader_name]
        
        if not loader.dependencies:
            calculated_levels[loader_name] = 0
            return 0
        
        max_dep_level = 0
        for dep in loader.dependencies:
            dep_level = self._calculate_dependency_level(dep, calculated_levels)
            max_dep_level = max(max_dep_level, dep_level)
        
        level = max_dep_level + 1
        calculated_levels[loader_name] = level
        return level
    
    def _log_execution_summary(self, summary: Dict[str, Any]):
        """Log a comprehensive execution summary."""
        logger.info("=" * 80)
        logger.info("📊 DATA LOADER EXECUTION SUMMARY")
        logger.info("=" * 80)
        logger.info(f"🕐 Execution Type: {summary['execution_type']}")
        logger.info(f"⏱️  Total Duration: {summary['total_duration_seconds']:.2f}s")
        logger.info(f"📈 Success Rate: {summary['success_rate']:.2%}")
        logger.info(f"✅ Successful: {summary['loaders_successful']}/{summary['loaders_attempted']}")
        logger.info(f"❌ Failed: {summary['loaders_failed']}/{summary['loaders_attempted']}")
        
        if summary['successful_loaders']:
            logger.info(f"✅ Successful loaders: {', '.join(summary['successful_loaders'])}")
        
        if summary['failed_loaders']:
            logger.error(f"❌ Failed loaders: {', '.join(summary['failed_loaders'])}")
        
        logger.info("=" * 80)


def main():
    """Main execution function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Data Loader Coordinator")
    parser.add_argument("--mode", choices=["sequential", "parallel"], default="sequential",
                       help="Execution mode")
    parser.add_argument("--critical-only", action="store_true",
                       help="Run only critical loaders")
    parser.add_argument("--max-workers", type=int, default=3,
                       help="Maximum parallel workers (for parallel mode)")
    parser.add_argument("--config", type=str,
                       help="Configuration file path")
    
    args = parser.parse_args()
    
    try:
        # Verify environment
        if not os.environ.get("DB_SECRET_ARN"):
            logger.error("❌ DB_SECRET_ARN environment variable not set")
            sys.exit(1)
        
        # Initialize coordinator
        coordinator = DataLoaderCoordinator(args.config)
        
        # Run loaders
        if args.mode == "parallel":
            result = coordinator.run_parallel(args.max_workers, args.critical_only)
        else:
            result = coordinator.run_sequential(args.critical_only)
        
        # Save detailed results
        results_file = f"/tmp/data_loader_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(results_file, 'w') as f:
            json.dump(result, f, indent=2)
        
        logger.info(f"📄 Detailed results saved to: {results_file}")
        
        # Exit with appropriate code
        if result['loaders_failed'] == 0:
            logger.info("🎉 All loaders completed successfully!")
            sys.exit(0)
        else:
            logger.error(f"❌ {result['loaders_failed']} loaders failed!")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"❌ Fatal error in data loader coordinator: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()