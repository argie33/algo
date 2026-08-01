#!/usr/bin/env python3
"""
DIRECT FIX: Force exit all oversized positions immediately
Bypasses orchestrator schedule to fix risk violations NOW
"""
import logging
from datetime import date as _date
from decimal import Decimal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def execute_force_exits():
    """Exit oversized positions directly"""
    from utils.db.connection import get_db_connection
    from utils.db.context import DatabaseContext
    from algo.infrastructure.config import AlgoConfig
    from algo.trading import ExitEngine

    print("=" * 70)
    print("DIRECT FORCE EXIT OF OVERSIZED POSITIONS")
    print("=" * 70)

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Find oversized positions
        cur.execute('''
        SELECT ap.position_id, ap.symbol, ap.quantity, ap.current_price,
               ap.trade_ids_arr,
               ROUND(ap.quantity * ap.current_price / (SELECT SUM(quantity * current_price) FROM algo_positions WHERE quantity != 0) * 100, 2) as pct
        FROM algo_positions ap
        WHERE ap.quantity != 0 AND ap.status = 'open'
        ORDER BY ap.quantity * ap.current_price DESC
        ''')

        all_positions = cur.fetchall()
        oversized = [(p[0], p[1], p[2], p[3], p[5], p[4]) for p in all_positions if p[5] and p[5] > 6.0]

        print(f"\nFound {len(oversized)} oversized positions (>6%):\n")
        for pos_id, symbol, qty, price, pct, trade_ids in oversized:
            print(f"  {symbol:8} {qty:8.0f}sh @ ${price:8.2f} = {pct:6.2f}% of portfolio")

        if not oversized:
            print("  (none)")
            return True

        # Load config
        config = AlgoConfig()

        # Create exit engine
        exit_engine = ExitEngine(config)

        # Build trade list for oversized positions
        trades_to_exit = []
        for pos_id, symbol, qty, price, pct, trade_ids in oversized:
            if not trade_ids:
                logger.error(f"{symbol}: No trade_ids - cannot exit")
                continue

            trade_id_list = trade_ids if isinstance(trade_ids, list) else [trade_ids]
            if not trade_id_list:
                logger.error(f"{symbol}: Empty trade list - cannot exit")
                continue

            # Get trade details for this position
            cur.execute('''
            SELECT t.trade_id, t.symbol, t.entry_price, t.entry_quantity,
                   t.stop_loss_price, t.alpaca_order_id
            FROM algo_trades t
            WHERE t.trade_id = %s
            ''', (trade_id_list[0],))

            trade_row = cur.fetchone()
            if not trade_row:
                logger.error(f"{symbol}: Trade not found - cannot exit")
                continue

            trade_id, sym, entry_price, entry_qty, stop_price, alpaca_id = trade_row
            trades_to_exit.append({
                'trade_id': trade_id,
                'symbol': symbol,
                'entry_price': float(entry_price),
                'entry_qty': int(entry_qty),
                'stop_loss_price': float(stop_price) if stop_price else float(price) * 0.95,
                'alpaca_order_id': alpaca_id,
                'quantity': qty,  # current quantity
            })

        if not trades_to_exit:
            print("  ERROR: Could not build trade list for any oversized position")
            return False

        print(f"\nExecuting FULL exits for {len(trades_to_exit)} oversized positions...\n")

        # CRITICAL: Execute FULL exits (100%) for oversized positions, not partial exits
        # The standard exit engine applies distribution rules (50% reduction), but for
        # oversized positions we need to force FULL exits regardless of distribution days
        from algo.trading import TradeExecutor

        executor = TradeExecutor(config)
        exits_executed = 0
        stop_raises = 0
        errors = 0
        forced_closes = 0

        # Build a map of trade_id to current_price for all oversized positions
        position_prices = {}
        for pos_id, symbol, qty, price, pct, trade_ids in oversized:
            if trade_ids and isinstance(trade_ids, list) and trade_ids:
                position_prices[trade_ids[0]] = float(price)

        for trade in trades_to_exit:
            try:
                # Get current market price for this symbol
                current_price = position_prices.get(trade['trade_id'], None)
                if current_price is None:
                    # Fallback: use the stop price as a conservative estimate
                    current_price = trade['stop_loss_price'] * 1.05

                # FULL EXIT (100%) for oversized position - ignore normal exit rules
                result = executor.exit_trade(
                    trade_id=trade['trade_id'],
                    exit_price=current_price,
                    exit_reason=f'FORCE_EXIT: Position exceeds 6% concentration limit',
                    exit_fraction=1.0,  # FULL EXIT - 100% of remaining shares
                    exit_stage=None,  # No target stage, pure force close
                )

                if result.get('success'):
                    exits_executed += 1
                    if result.get('shares_exited', 0) > 0:
                        forced_closes += 1
                    print(f"  ✓ {trade['symbol']}: Forced exit {result.get('shares_exited', 0):.0f}sh @ ${result.get('exit_price', current_price):.2f}")
                else:
                    errors += 1
                    print(f"  ✗ {trade['symbol']}: Force exit failed - {result.get('message', 'unknown error')}")
            except Exception as e:
                errors += 1
                logger.error(f"Force exit error for {trade['symbol']}: {e}")
                print(f"  ✗ {trade['symbol']}: Exception during force exit - {e}")

        print(f"\n" + "=" * 70)
        print(f"RESULTS:")
        print(f"  Exits executed: {exits_executed}")
        print(f"  Stop raises: {stop_raises}")
        print(f"  Forced closes: {forced_closes}")
        print(f"  Errors: {errors}")
        print("=" * 70)

        # Verify results
        print("\nVerifying portfolio state after exits...\n")

        cur.execute('''
        SELECT COUNT(*) as cnt, SUM(quantity * current_price) as total_value
        FROM algo_positions WHERE quantity != 0 AND status = 'open'
        ''')

        cnt, total_val = cur.fetchone()
        print(f"Open positions remaining: {cnt}")
        print(f"Portfolio value: ${total_val:,.2f}" if total_val else "Portfolio value: $0.00")

        # Check for any remaining oversized
        cur.execute('''
        SELECT symbol,
               ROUND(quantity * current_price / NULLIF((SELECT SUM(quantity * current_price) FROM algo_positions WHERE quantity != 0), 0) * 100, 2) as pct
        FROM algo_positions
        WHERE quantity != 0
        AND ROUND(quantity * current_price / NULLIF((SELECT SUM(quantity * current_price) FROM algo_positions WHERE quantity != 0), 0) * 100, 2) > 6.0
        ORDER BY pct DESC
        ''')

        remaining_oversized = cur.fetchall()
        if remaining_oversized:
            print(f"\nWARNING: {len(remaining_oversized)} positions still oversized:")
            for symbol, pct in remaining_oversized:
                print(f"  {symbol}: {pct:.2f}%")
        else:
            print(f"\n✓ No oversized positions remaining")

        if errors == 0 and not remaining_oversized:
            print(f"\n✓ Force exit completed successfully")
            return True
        else:
            print(f"\n⚠ Force exit completed with issues")
            return False

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    try:
        success = execute_force_exits()
        exit(0 if success else 1)
    except Exception as e:
        logger.critical(f"Force exit execution failed: {e}")
        print(f"\n✗ FAILED: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
