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

import logging
from datetime import date as _date, timedelta
from typing import Dict, Any

from utils.db_connection import get_db_connection
from config.credential_helper import get_db_config, get_db_password
from algo.algo_signal_trade_performance import SignalTradePerformancePopulator
from algo.algo_signal_attribution import SignalAttributionEngine
from algo.algo_weight_optimizer import WeightOptimizer

logger = logging.getLogger(__name__)


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


if __name__ == "__main__":
    # Test runner (for manual invocation)
    import sys
    from config.algo_config import AlgoConfig

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Load config
    config = AlgoConfig.load()
    dry_run = "--dry-run" in sys.argv

    # Run optimization
    result = run_weight_optimization_cycle(config, run_date=_date.today(), dry_run=dry_run)
    print(f"\nResult: {result}")
    sys.exit(0 if result['success'] else 1)
