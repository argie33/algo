#!/usr/bin/env python3

"""
Scheduled Daily Weight Optimization Loader

Runs after orchestrator completion (6:00 PM ET daily).
Triggers continuous improvement loop:
  1. Populate signal_trade_performance from closed trades
  2. Compute IC (Information Coefficient) for each component
  3. Run weight optimizer to adapt swing_score weights
  4. Weekly: trigger walk-forward backtest validation

Enables data-driven, automated refinement of the swing trading strategy.
"""

import sys
import logging
from datetime import date as _date, timedelta
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Optional imports for full optimization cycle
try:
    from algo.algo_signal_trade_performance import SignalTradePerformancePopulator
    from algo.algo_signal_attribution import SignalAttributionEngine
    from algo.algo_weight_optimizer import WeightOptimizer
except ImportError:
    SignalTradePerformancePopulator = None
    SignalAttributionEngine = None
    WeightOptimizer = None


def run_weight_optimization_cycle(config: Dict[str, Any], run_date: _date = None, dry_run: bool = False) -> Dict[str, Any]:
    """
    Execute full daily weight optimization cycle.

    Args:
        config: Configuration dict (from AlgoConfig.load())
        run_date: Date to optimize for (default: today)
        dry_run: If True, compute but don't persist weight changes

    Returns:
        {
            'success': bool,
            'run_date': str,
            'trades_processed': int,
            'ic_values': dict,
            'weight_changes': list,
            'message': str
        }
    """
    if run_date is None:
        run_date = _date.today()

    results = {
        'success': True,
        'run_date': str(run_date),
        'trades_processed': 0,
        'ic_values': {},
        'weight_changes': [],
    }

    try:
        # Step 1: Populate signal_trade_performance from recently closed trades
        logger.info("=== DAILY WEIGHT OPTIMIZATION CYCLE ===")
        logger.info(f"Date: {run_date}")

        stpp = SignalTradePerformancePopulator()
        stpp_result = stpp.populate_closed_trades(lookback_days=7)
        results['trades_processed'] = stpp_result.get('trades_processed', 0)

        if not stpp_result.get('success'):
            logger.warning(f"Failed to populate trades: {stpp_result.get('message')}")
            results['success'] = False
            results['message'] = stpp_result.get('message', 'Population failed')
            return results

        if results['trades_processed'] == 0:
            logger.info("No new closed trades to process.")
            results['message'] = 'No new closed trades'
            return results

        logger.info(f"✓ Populated {results['trades_processed']} closed trades")

        # Step 2: Compute IC for components
        attribution = SignalAttributionEngine()
        attr_result = attribution.compute_ic(run_date, lookback_trades=40)

        if attr_result.get('components'):
            results['ic_values'] = attr_result['components']
            logger.info(f"✓ Computed IC for {len(attr_result['components'])} components:")
            for comp, ic_data in attr_result['components'].items():
                status = '★' if ic_data.get('ic', 0) >= 0.25 else '◇' if ic_data.get('ic', 0) >= 0.10 else '·'
                logger.info(
                    f"  {comp:20s}  IC={ic_data.get('ic', 0):+.3f}  "
                    f"pval={ic_data.get('pvalue', 1):.3f}  {status}"
                )
        else:
            logger.info("⚠ Could not compute IC (insufficient data or error)")

        # Step 3: Run weight optimizer
        try:
            optimizer = WeightOptimizer(config)
            opt_result = optimizer.apply(run_date, dry_run=dry_run)

            if opt_result.get('changes'):
                results['weight_changes'] = opt_result['changes']
                logger.info(f"✓ Weight optimization: {len(opt_result['changes'])} changes")
                for change in opt_result['changes']:
                    logger.info(
                        f"  {change['component']:20s}  "
                        f"{change['old_weight']:3d}% → {change['new_weight']:3d}%  "
                        f"[IC={change.get('ic', 0):+.3f}]"
                    )
                if dry_run:
                    logger.info("  (DRY-RUN — not persisted)")
            else:
                logger.info("✓ Weight optimization: no changes (stable or insufficient data)")

            if not opt_result.get('success'):
                results['success'] = False
                results['message'] = opt_result.get('message', 'Optimization failed')
                logger.warning(f"Optimization failed: {opt_result.get('message')}")
        except Exception as e:
            logger.error(f"Weight optimization failed: {e}", exc_info=True)
            results['success'] = False
            results['message'] = str(e)[:100]

        # Step 4: Weekly backtest (Fridays only)
        if run_date.weekday() == 4:  # Friday
            logger.info("\n[WEEKLY] Running walk-forward validation...")
            try:
                from algo.algo_backtest import Backtester
                backtester = Backtester(config)

                # Use last 63 days for test window
                test_start = run_date - timedelta(days=63)
                test_end = run_date

                backtest_result = backtester.run_backtest(test_start, test_end)
                logger.info(
                    f"✓ Walk-forward result: Sharpe={backtest_result.get('sharpe_ratio', 0):.2f}, "
                    f"WinRate={backtest_result.get('win_rate_pct', 0):.1f}%, "
                    f"Profit={backtest_result.get('total_return_pct', 0):+.1f}%"
                )
            except Exception as e:
                logger.warning(f"Weekly backtest failed (non-critical): {e}")

        logger.info("=== CYCLE COMPLETE ===\n")
        results['message'] = f"Processed {results['trades_processed']} trades, {len(results['weight_changes'])} weight changes"
        return results

    except Exception as e:
        logger.error(f"Weight optimization cycle failed: {e}", exc_info=True)
        results['success'] = False
        results['message'] = str(e)[:100]
        return results


def main():
    import argparse
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from config.env_loader import load_env

    load_env()
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    parser = argparse.ArgumentParser(description="Weight Optimization Loader")
    parser.add_argument("--symbols", type=str, help="(Unused - for compatibility)")
    parser.add_argument("--parallelism", type=int, default=1, help="(Unused - for compatibility)")
    parser.add_argument("--dry-run", action="store_true", help="Compute but don't persist changes")
    args = parser.parse_args()

    try:
        from config.algo_config import AlgoConfig
        config = AlgoConfig.load()
        result = run_weight_optimization_cycle(config, run_date=_date.today(), dry_run=args.dry_run)
        print(f"\nResult: {result}")
        return 0 if result['success'] else 1
    except ImportError as e:
        logging.warning(f"Weight optimization skipped - algo modules not available: {e}")
        return 0  # Don't fail for missing optional modules
    except Exception as e:
        logging.error(f"Weight optimization failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
