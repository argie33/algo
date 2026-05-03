#!/usr/bin/env python3
"""
Daily Algo Orchestrator - Run complete algo workflow

1. Load market and technical data (load_algo_metrics_daily.py)
2. Evaluate signals through 5-tier filter (algo_filter_pipeline.py)
3. Size positions for qualified signals (algo_position_sizer.py)
4. Execute trades (algo_trade_executor.py)
5. Check exits and execute (algo_exit_engine.py)
6. Daily reconciliation (algo_daily_reconciliation.py)
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from algo_config import get_config
from algo_filter_pipeline import FilterPipeline
from algo_position_sizer import PositionSizer
from algo_trade_executor import TradeExecutor
from algo_exit_engine import ExitEngine
from algo_daily_reconciliation import DailyReconciliation

def run_algo_workflow(eval_date=None):
    """Run complete daily algo workflow."""
    if not eval_date:
        eval_date = datetime.now().date()

    print(f"\n{'='*70}")
    print(f"SWING TRADING ALGO - DAILY WORKFLOW")
    print(f"Date: {eval_date}")
    print(f"{'='*70}\n")

    config = get_config()

    # Check if algo is enabled
    if not config.get('enable_algo', True):
        print("ALGO DISABLED - exiting\n")
        return {'status': 'disabled'}

    execution_mode = config.get('execution_mode', 'paper')
    print(f"Execution Mode: {execution_mode}\n")

    try:
        # Step 1: Evaluate signals
        print(f"STEP 1: SIGNAL EVALUATION")
        print(f"-" * 70)
        pipeline = FilterPipeline()
        qualified_trades = pipeline.evaluate_signals(eval_date)
        print(f"\nQualified trades: {len(qualified_trades)}\n")

        if len(qualified_trades) == 0:
            print("No qualified trades today\n")
            return {'status': 'ok', 'trades_executed': 0}

        # Step 2: Size positions
        print(f"STEP 2: POSITION SIZING")
        print(f"-" * 70)
        sizer = PositionSizer(config)
        sized_trades = []

        for trade in qualified_trades:
            symbol = trade['symbol']
            entry_price = trade['entry_price']

            # Estimate stop (5% below entry for simplicity)
            stop_loss = entry_price * 0.95

            result = sizer.calculate_position_size(symbol, entry_price, stop_loss)

            if result['status'] == 'ok':
                # Calculate targets (1.5R, 3R, 4R)
                risk_per_share = entry_price - stop_loss
                t1 = entry_price + (risk_per_share * 1.5)
                t2 = entry_price + (risk_per_share * 3.0)
                t3 = entry_price + (risk_per_share * 4.0)

                sized_trades.append({
                    'symbol': symbol,
                    'entry_price': entry_price,
                    'shares': result['shares'],
                    'stop_loss': stop_loss,
                    'target_1': t1,
                    'target_2': t2,
                    'target_3': t3,
                    'position_size_pct': result['position_size_pct'],
                    'risk': result['risk_dollars']
                })

                print(f"{symbol}: {result['shares']} shares | " +
                      f"Entry: ${entry_price:.2f} | " +
                      f"Stop: ${stop_loss:.2f} | " +
                      f"Risk: ${result['risk_dollars']:.2f}")

        print(f"\nSized trades: {len(sized_trades)}\n")

        if len(sized_trades) == 0:
            print("No trades passed position sizing\n")
            return {'status': 'ok', 'trades_executed': 0}

        # Step 3: Execute trades
        print(f"STEP 3: TRADE EXECUTION")
        print(f"-" * 70)
        executor = TradeExecutor(config)
        executed_trades = []

        for trade in sized_trades[:12]:  # Max 12 positions
            signal_date = eval_date  # Using eval date as signal date
            result = executor.execute_trade(
                symbol=trade['symbol'],
                entry_price=trade['entry_price'],
                shares=trade['shares'],
                stop_loss_price=trade['stop_loss'],
                target_1_price=trade['target_1'],
                target_2_price=trade['target_2'],
                target_3_price=trade['target_3'],
                signal_date=signal_date
            )

            if result['success']:
                executed_trades.append(result)
                print(f"{trade['symbol']}: {result['message']}")
            else:
                print(f"{trade['symbol']}: FAILED - {result['message']}")

        print(f"\nExecuted: {len(executed_trades)} trades\n")

        # Step 4: Check exits
        print(f"STEP 4: EXIT CHECK")
        print(f"-" * 70)
        exit_engine = ExitEngine(config)
        exits = exit_engine.check_and_execute_exits(eval_date)

        # Step 5: Daily reconciliation
        print(f"STEP 5: DAILY RECONCILIATION")
        print(f"-" * 70)
        reconciliation = DailyReconciliation(config)
        recon_result = reconciliation.run_daily_reconciliation(eval_date)

        # Summary
        print(f"\n{'='*70}")
        print(f"WORKFLOW COMPLETE")
        print(f"{'='*70}")
        print(f"Signals Evaluated: {len(qualified_trades)}")
        print(f"Trades Executed: {len(executed_trades)}")
        print(f"Exits Checked: {exits}")
        print(f"Portfolio Value: ${recon_result.get('portfolio_value', 0):,.2f}")
        print(f"{'='*70}\n")

        return {
            'status': 'ok',
            'signals_evaluated': len(qualified_trades),
            'trades_executed': len(executed_trades),
            'exits_checked': exits,
            'portfolio_value': recon_result.get('portfolio_value', 0)
        }

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return {'status': 'error', 'message': str(e)}

if __name__ == "__main__":
    import subprocess

    # First, load daily metrics
    print("Loading daily metrics...")
    result = subprocess.run(
        ['python3', 'load_algo_metrics_daily.py'],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print("Warning: Metrics load had issues:")
        print(result.stderr[-200:] if result.stderr else result.stdout[-200:])
    else:
        print("Metrics loaded successfully\n")

    # Run workflow
    workflow_result = run_algo_workflow()
    sys.exit(0 if workflow_result['status'] == 'ok' else 1)
