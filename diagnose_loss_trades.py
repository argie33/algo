#!/usr/bin/env python3
"""
Diagnose why 5 consecutive trades got stopped out with significant losses.
"""

from utils.db.context import DatabaseContext

def diagnose():
    print("\n" + "="*80)
    print("DIAGNOSING ROOT CAUSE OF 5 CONSECUTIVE LOSSES")
    print("="*80)

    with DatabaseContext("read") as cur:
        # Get detailed info about the 5 loss trades
        loss_trades = ["TRD-186F03002A", "TRD-9D8D1C624E", "TRD-EC648B2695", "TRD-0EEE4FD698", "TRD-4DE16E2F76"]

        for trade_id in loss_trades:
            print(f"\n{'='*80}")
            print(f"TRADE: {trade_id}")
            print(f"{'='*80}")

            # Get trade details
            cur.execute("""
                SELECT symbol, entry_price, stop_loss_price, entry_quantity,
                       profit_loss_pct, exit_reason, entry_reason
                FROM algo_trades
                WHERE trade_id = %s
            """, (trade_id,))

            trade = cur.fetchone()
            if trade:
                sym, entry_p, stop_p, qty, pnl, exit_reason, entry_reason = trade
                print(f"\nSymbol: {sym}")
                print(f"Entry: ${entry_p:.2f} | Stop: ${stop_p:.2f} | Qty: {qty:.2f}")
                print(f"P&L: {pnl:.2f}% | Exit Reason: {exit_reason}")
                print(f"Entry Reason: {entry_reason}")

                # Calculate stop distance
                if entry_p and stop_p:
                    stop_pct_from_entry = ((stop_p - entry_p) / entry_p) * 100
                    print(f"Stop Distance: {stop_pct_from_entry:.1f}% from entry")

                    if stop_pct_from_entry > -5:
                        print("⚠️ TIGHT STOP - only {stop_pct_from_entry:.1f}% risk")
                    elif stop_pct_from_entry < -15:
                        print("🛑 WIDE STOP - {stop_pct_from_entry:.1f}% risk (unusual)")

            # Check signal data
            cur.execute("""
                SELECT signal_date, quality_score,
                       CASE
                           WHEN quality_score >= 75 THEN 'HIGH'
                           WHEN quality_score >= 60 THEN 'MEDIUM'
                           ELSE 'LOW'
                       END as quality_tier
                FROM algo_signals
                WHERE symbol = %s
                ORDER BY signal_date DESC
                LIMIT 1
            """, (sym,))

            signal = cur.fetchone()
            if signal:
                sig_date, quality, tier = signal
                print(f"\nSignal Quality: {quality:.0f} ({tier})")
                print(f"Signal Date: {sig_date}")

                if quality < 60:
                    print("❌ LOW QUALITY SIGNAL - this may explain the poor entry")

            # Check if this symbol has a history of losses
            cur.execute("""
                SELECT COUNT(*) as total_trades,
                       COUNT(*) FILTER (WHERE profit_loss_pct < 0) as losing_trades,
                       AVG(profit_loss_pct) as avg_pnl
                FROM algo_trades
                WHERE symbol = %s AND status = 'closed'
            """, (sym,))

            history = cur.fetchone()
            if history:
                total, losses, avg_pnl = history
                if total > 0:
                    loss_rate = (losses / total) * 100
                    print(f"\nTrade History: {total} total, {losses} losses ({loss_rate:.0f}%), Avg PNL: {avg_pnl:.2f}%")
                    if loss_rate > 70:
                        print("⚠️ HIGH LOSS RATE on this symbol")

    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print("""
Possible root causes for 5 consecutive losses:
1. LOW SIGNAL QUALITY - signals below quality threshold being executed
2. TIGHT STOPS - stops too close to entry, normal volatility triggers them
3. POOR MOMENTUM SELECTION - entering at wrong time in trend
4. MARKET CONDITIONS - unusual volatility or gaps in price data
5. ENTRY FILTERING BUG - earnings, sector concentration not being checked

Next steps:
- Review Phase 7 signal quality scoring logic
- Review Phase 8 entry filtering (earnings blackout, concentration limits)
- Check if prices used for entry/stop calculation are stale or incorrect
- Run orchestrator during market hours to get fresh price data
""")

if __name__ == "__main__":
    diagnose()
