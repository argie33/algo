"""Unified loader runner - consolidates boilerplate across all data loaders.

This module provides a single entry point for running any OptimalLoader subclass,
eliminating ~25 lines of duplicated main() boilerplate from each of the 42 loaders.

Usage:
    from loaders.runner import run_loader
    from loaders.load_quality_metrics import QualityMetricsLoader

    if __name__ == "__main__":
        sys.exit(run_loader(QualityMetricsLoader))

Benefits:
- Reduces loader files from ~230 lines to ~180 lines (eliminates main/argparse/error handling)
- Single source of truth for loader invocation pattern
- Easier to add new flags (e.g., --backfill-days) to all loaders at once
- Reduces token burn when reading multiple loaders (boilerplate is here, not repeated)
"""

import argparse
import logging

from utils.loaders.config import get_default_parallelism
from utils.loaders.helpers import get_active_symbols
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


def run_loader(
    loader_class: type[OptimalLoader],
    description: str | None = None,
    global_mode: bool = False,
) -> int:
    """Execute a loader with standard argument parsing and error handling.

    Args:
        loader_class: The OptimalLoader subclass to instantiate and run.
        description: Optional description for argparse (defaults to loader table_name).
        global_mode: If True, call load_global() for market-wide loaders (no symbol args).
                    If False (default), call run(symbols) for per-symbol loaders.

    Returns:
        Exit code: 0 on success, 1 if fail_rate > 5%.
    """
    parser = argparse.ArgumentParser(description=description or f"{loader_class.table_name} loader")

    if not global_mode:
        parser.add_argument("--symbols", help="Comma-separated symbols. Default: all active symbols.")
        parser.add_argument(
            "--parallelism",
            type=int,
            default=get_default_parallelism(loader_class.table_name),
            help="Number of parallel workers (default: per-loader config).",
        )
        parser.add_argument(
            "--backfill-days",
            type=int,
            default=None,
            help="Refetch last N days instead of using watermark (for recovery/validation).",
        )

    args = parser.parse_args()

    loader = loader_class()
    try:
        if global_mode:
            result = loader.load_global()
            if result > 0:
                logger.info(f"SUCCESS: {result} records loaded")
                return 0
            else:
                logger.error("FAILED: No records loaded")
                return 1
        else:
            # Per-symbol mode
            if args.symbols:
                symbols = [s.strip().upper() for s in args.symbols.split(",")]
            else:
                symbols = get_active_symbols(timeout_secs=60)

            if args.backfill_days:
                stats = loader.run(
                    symbols,
                    parallelism=args.parallelism,
                    backfill_days=args.backfill_days,
                )
            else:
                stats = loader.run(symbols, parallelism=args.parallelism)

            # Assess success: warn if fail_rate > 5%
            if "symbols_failed" not in stats:
                raise RuntimeError(
                    f"[LOADER] Stats missing 'symbols_failed' key. "
                    f"Loader contract violation: expected stats dict with failure count, got {list(stats.keys())}. "
                    f"Cannot determine load success/failure without explicit failure count."
                )
            symbols_failed = stats["symbols_failed"]
            if not isinstance(symbols_failed, int):
                raise TypeError(
                    f"[LOADER] 'symbols_failed' must be int, got {type(symbols_failed).__name__}: {symbols_failed}. "
                    f"Stats tracking corrupted."
                )
            fail_rate = symbols_failed / max(len(symbols), 1)
            if fail_rate > 0.05:
                logger.error(
                    f"Too many failures: {symbols_failed}/{len(symbols)} ({fail_rate * 100:.1f}%)"
                )
                return 1

            return 0
    finally:
        loader.close()
