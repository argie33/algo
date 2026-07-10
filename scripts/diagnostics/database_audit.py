#!/usr/bin/env python3
"""
Comprehensive database audit for algo system.
Checks orchestrator runs, data freshness, portfolio status, signals, and scores.
"""

from datetime import datetime, timedelta
from utils.db import DatabaseContext


def safe_dt(dt):
    """Safely remove timezone from datetime and convert date to datetime."""
    if dt is None:
        return None
    # If it's a date, convert to datetime
    if hasattr(dt, 'year') and not hasattr(dt, 'hour'):  # It's a date object
        return datetime.combine(dt, datetime.min.time())
    # If it's a datetime with tzinfo, remove it
    if hasattr(dt, 'tzinfo') and dt.tzinfo:
        return dt.replace(tzinfo=None)
    return dt


def audit_orchestrator_runs():
    """Check recent orchestrator runs in last 24 hours."""
    print("\n" + "="*80)
    print("1. ORCHESTRATOR RUNS (algo_orchestrator_runs)")
    print("="*80)

    # Get runs in last 24 hours
    with DatabaseContext('read') as cur:
        cur.execute("""
        SELECT
            COUNT(*) as total_runs,
            SUM(CASE WHEN overall_status = 'completed' THEN 1 ELSE 0 END) as completed,
            SUM(CASE WHEN overall_status = 'failed' THEN 1 ELSE 0 END) as failed,
            SUM(CASE WHEN overall_status = 'in_progress' THEN 1 ELSE 0 END) as in_progress,
            MAX(started_at) as latest_run,
            MIN(started_at) as earliest_run
        FROM algo_orchestrator_runs
        WHERE started_at > NOW() - get_interval_sql('24h')
        """)
        result_24h = cur.fetchone()

    print(f"\nLast 24 Hours:")
    print(f"  Total runs:     {result_24h['total_runs']}")
    print(f"  Completed:      {result_24h['completed']}")
    print(f"  Failed:         {result_24h['failed']}")
    print(f"  In Progress:    {result_24h['in_progress']}")

    if result_24h['latest_run']:
        latest = safe_dt(result_24h['latest_run'])
        time_ago = datetime.now() - latest
        print(f"  Latest run:     {latest} ({time_ago.total_seconds()/3600:.1f} hours ago)")

    # Get last 5 runs details
    print(f"\nLast 5 Runs:")
    with DatabaseContext('read') as cur:
        cur.execute("""
        SELECT run_id, overall_status, started_at, completed_at, halt_reason
        FROM algo_orchestrator_runs
        ORDER BY started_at DESC
        LIMIT 5
        """)
        last_runs = cur.fetchall()

    for run in last_runs:
        status_icon = "OK" if run['overall_status'] == 'completed' else "XX" if run['overall_status'] == 'failed' else "WP"
        print(f"  {status_icon} {run['run_id'][:12]}... | {run['overall_status']:10} | {run['started_at']}")
        if run['halt_reason']:
            print(f"     Reason: {run['halt_reason'][:100]}")

    # Status assessment
    if result_24h['total_runs'] == 0:
        print("\n[!] Status: NO RUNS IN LAST 24 HOURS - Orchestrator may not be executing")
    elif result_24h['failed'] and result_24h['failed'] > 0:
        print(f"\n[X] Status: {result_24h['failed']} FAILED RUNS - Check messages above")
    elif result_24h['completed'] and result_24h['completed'] >= 2:
        print(f"\n[OK] Status: GOOD - {result_24h['completed']} successful runs")
    else:
        print(f"\n[!] Status: DEGRADED - Only {result_24h['completed']} successful runs")


def audit_data_freshness():
    """Check data loader status and freshness."""
    print("\n" + "="*80)
    print("2. DATA FRESHNESS (data_loader_status)")
    print("="*80)

    with DatabaseContext('read') as cur:
        cur.execute("""
        SELECT
            table_name,
            status,
            last_updated,
            age_days,
            symbol_count,
            error_message,
            row_count
        FROM data_loader_status
        ORDER BY last_updated DESC
        """)
        loaders = cur.fetchall()

    if not loaders:
        print("\n[!] No loader status records found")
        return

    print("\nLoader Status Summary:")
    critical_freshness = 4  # hours
    warning_freshness = 8   # hours

    for loader in loaders:
        status = loader['status']
        last_updated = safe_dt(loader['last_updated'])
        age_days = loader.get('age_days', None)

        # Calculate hours since last update
        if last_updated:
            time_ago = datetime.now() - last_updated
            hours_ago = time_ago.total_seconds() / 3600
        else:
            hours_ago = None

        # Determine status icon
        if status == 'success' or status == 'complete':
            if age_days is not None:
                if age_days == 0:
                    icon = "OK"
                elif age_days < 1:
                    icon = "[!]"
                else:
                    icon = "XX"
            else:
                icon = "OK"
        else:
            icon = "XX"

        row_info = f" | Rows: {loader['row_count']}" if loader['row_count'] else ""
        sym_info = f" | Symbols: {loader['symbol_count']}" if loader['symbol_count'] else ""
        print(f"  {icon} {loader['table_name']:30} | {status:10} | Age: {age_days}d{row_info}{sym_info}")

        if loader['error_message']:
            print(f"     Error: {loader['error_message'][:80]}")

    # Summary assessment
    successful = [l for l in loaders if l['status'] in ('success', 'complete')]
    fresh = [l for l in successful if l.get('age_days', 0) == 0]

    if len(successful) == len(loaders) and len(fresh) >= len(loaders) // 2:
        print(f"\n[OK] Status: GOOD - {len(successful)} loaders successful, {len(fresh)} fresh")
    elif len(successful) == len(loaders):
        print(f"\n[!] Status: STALE - All loaders successful but data aging")
    else:
        print(f"\n[X] Status: CRITICAL - {len(loaders) - len(successful)} loaders failed")


def audit_portfolio_status():
    """Check portfolio positions and total value."""
    print("\n" + "="*80)
    print("3. PORTFOLIO STATUS (algo_trades)")
    print("="*80)

    # Get open positions
    with DatabaseContext('read') as cur:
        cur.execute("""
        SELECT
            id,
            symbol,
            status,
            quantity,
            entry_price,
            exit_price,
            entry_date,
            profit_loss_dollars,
            profit_loss_pct
        FROM algo_trades
        WHERE status IN ('open', 'partially_filled')
        ORDER BY entry_date DESC
        """)
        open_positions = cur.fetchall()

    print(f"\nOpen Positions: {len(open_positions)}")

    total_value = 0
    for pos in open_positions:
        # Fail-fast if critical price data missing
        if pos['entry_price'] is None:
            print(f"  [ERROR] {pos['symbol']:6} | Missing entry_price - cannot calculate position value")
            continue
        if pos['quantity'] is None or pos['quantity'] == 0:
            print(f"  [ERROR] {pos['symbol']:6} | Missing or zero quantity - invalid position")
            continue

        price = pos['exit_price'] if pos['exit_price'] is not None else pos['entry_price']
        quantity = float(pos['quantity'])
        value = quantity * float(price)
        total_value += value
        pnl = pos['profit_loss_dollars']
        pnl_icon = "+" if pnl and pnl > 0 else "-" if pnl and pnl < 0 else "="
        pnl_pct = pos['profit_loss_pct'] if pos['profit_loss_pct'] is not None else 0.0
        print(f"  {pos['symbol']:6} | Qty: {quantity:7.0f} | Value: ${value:10.2f} | P&L: {pnl_icon} {pnl_pct:6.2f}%")

    print(f"\nTotal Portfolio Value: ${total_value:.2f}")

    # Get recent trades
    with DatabaseContext('read') as cur:
        cur.execute("""
        SELECT
            COUNT(*) as total_trades,
            COUNT(CASE WHEN status IN ('filled', 'closed') THEN 1 END) as filled_closed,
            COUNT(CASE WHEN status = 'closed' THEN 1 END) as closed,
            MAX(entry_date) as latest_trade
        FROM algo_trades
        WHERE entry_date > NOW() - get_interval_sql('7d')
        """)
        recent_trades = cur.fetchone()

    print(f"\nLast 7 Days:")
    print(f"  Total trades:   {recent_trades['total_trades']}")
    print(f"  Filled/Closed:  {recent_trades['filled_closed']}")
    if recent_trades['latest_trade']:
        latest = safe_dt(recent_trades['latest_trade'])
        time_ago = datetime.now() - latest
        hours_ago = time_ago.total_seconds() / 3600
        print(f"  Latest trade:   {hours_ago:.1f} hours ago")

    # Status assessment
    if len(open_positions) == 0:
        print("\n[!] Status: NO OPEN POSITIONS - System idle or all positions closed")
    elif total_value > 0:
        print(f"\n[OK] Status: GOOD - {len(open_positions)} positions, ${total_value:.2f} at risk")
    else:
        print(f"\n[X] Status: CRITICAL - Portfolio value is zero or negative")


def audit_signal_generation():
    """Check buy/sell signal generation freshness."""
    print("\n" + "="*80)
    print("4. SIGNAL GENERATION (buy_sell_daily)")
    print("="*80)

    # Get today's signals
    with DatabaseContext('read') as cur:
        cur.execute("""
        SELECT
            COUNT(*) as total_signals,
            SUM(CASE WHEN signal = 'BUY' THEN 1 ELSE 0 END) as buy_count,
            SUM(CASE WHEN signal = 'SELL' THEN 1 ELSE 0 END) as sell_count,
            SUM(CASE WHEN signal = 'HOLD' THEN 1 ELSE 0 END) as hold_count,
            MAX(date) as latest_signal_date,
            MAX(created_at) as latest_created
        FROM buy_sell_daily
        WHERE DATE(date) = CURRENT_DATE
        """)
        today_signals = cur.fetchone()

    print(f"\nToday's Signals:")
    print(f"  Total:          {today_signals['total_signals']}")
    print(f"  BUY:            {today_signals['buy_count']}")
    print(f"  SELL:           {today_signals['sell_count']}")
    print(f"  HOLD:           {today_signals['hold_count']}")

    if today_signals['latest_signal_date']:
        latest = safe_dt(today_signals['latest_signal_date'])
        time_ago = datetime.now() - latest
        hours_ago = time_ago.total_seconds() / 3600
        print(f"  Latest signal:  {hours_ago:.1f} hours ago")

    # Sample recent signals
    print(f"\nRecent BUY signals (top 10):")
    with DatabaseContext('read') as cur:
        cur.execute("""
        SELECT symbol, signal_strength, date
        FROM buy_sell_daily
        WHERE signal = 'BUY'
        ORDER BY created_at DESC
        LIMIT 10
        """)
        buy_signals = cur.fetchall()

    for sig in buy_signals:
        strength = sig['signal_strength'] or 0
        print(f"  {sig['symbol']:6} | Strength: {strength:6.2f} | {sig['date']}")

    # Status assessment
    freshness_threshold = 4  # hours
    if today_signals['total_signals'] == 0:
        print(f"\n[X] Status: NO SIGNALS TODAY - Signal generation may be stalled")
    elif today_signals['latest_created']:
        latest = safe_dt(today_signals['latest_created'])
        time_ago = datetime.now() - latest
        hours_ago = time_ago.total_seconds() / 3600
        if hours_ago < freshness_threshold:
            print(f"\n[OK] Status: FRESH - Signals generated {hours_ago:.1f} hours ago")
        else:
            print(f"\n[!] Status: STALE - Last signals {hours_ago:.1f} hours old (threshold: {freshness_threshold}h)")
    else:
        print(f"\n[!] Status: UNKNOWN - Cannot determine signal freshness")


def audit_stock_scores():
    """Check stock scores availability and freshness."""
    print("\n" + "="*80)
    print("5. STOCK SCORES (stock_scores)")
    print("="*80)

    # Get score statistics
    with DatabaseContext('read') as cur:
        cur.execute("""
        SELECT
            COUNT(*) as total_scores,
            COUNT(CASE WHEN composite_score IS NOT NULL THEN 1 END) as with_composite,
            COUNT(CASE WHEN composite_score IS NULL THEN 1 END) as missing_composite,
            MAX(updated_at) as latest_update,
            MIN(updated_at) as oldest_update,
            AVG(CAST(composite_score AS FLOAT)) as avg_composite_score
        FROM stock_scores
        WHERE updated_at > NOW() - get_interval_sql('7d')
        """)
        score_stats = cur.fetchone()

    print(f"\nScore Statistics (Last 7 Days):")
    print(f"  Total symbols:      {score_stats['total_scores']}")
    print(f"  With composite:     {score_stats['with_composite']}")
    print(f"  Missing composite:  {score_stats['missing_composite']}")
    if score_stats['avg_composite_score']:
        print(f"  Avg score:          {score_stats['avg_composite_score']:.2f}")

    if score_stats['latest_update']:
        latest = safe_dt(score_stats['latest_update'])
        time_ago = datetime.now() - latest
        hours_ago = time_ago.total_seconds() / 3600
        print(f"  Latest update:      {hours_ago:.1f} hours ago")

    # Get update frequency
    with DatabaseContext('read') as cur:
        cur.execute("""
        SELECT
            DATE(updated_at) as update_date,
            COUNT(*) as symbol_count
        FROM stock_scores
        WHERE updated_at > NOW() - get_interval_sql('7d')
        GROUP BY DATE(updated_at)
        ORDER BY update_date DESC
        LIMIT 7
        """)
        update_freq = cur.fetchall()

    print(f"\nUpdate Frequency (Last 7 Days):")
    for freq in update_freq:
        print(f"  {freq['update_date']}: {freq['symbol_count']} symbols")

    # Sample top scores
    with DatabaseContext('read') as cur:
        cur.execute("""
        SELECT symbol, composite_score, quality_score, growth_score, updated_at
        FROM stock_scores
        WHERE composite_score IS NOT NULL
        ORDER BY composite_score DESC
        LIMIT 10
        """)
        top_scores = cur.fetchall()

    print(f"\nTop 10 Highest Scores:")
    for score in top_scores:
        comp = score['composite_score'] or 0
        qual = score['quality_score'] or 0
        growth = score['growth_score'] or 0
        print(f"  {score['symbol']:6} | Composite: {comp:6.2f} | Quality: {qual:6.2f} | Growth: {growth:6.2f}")

    # Status assessment
    freshness_threshold = 4  # hours
    if score_stats['total_scores'] == 0:
        print(f"\n[X] Status: NO SCORES - Stock scores not available")
    elif score_stats['latest_update']:
        latest = safe_dt(score_stats['latest_update'])
        time_ago = datetime.now() - latest
        hours_ago = time_ago.total_seconds() / 3600
        if score_stats['with_composite'] and score_stats['with_composite'] > 0 and hours_ago < freshness_threshold:
            print(f"\n[OK] Status: FRESH - {score_stats['with_composite']} symbols with scores, updated {hours_ago:.1f}h ago")
        else:
            print(f"\n[!] Status: STALE - Last update {hours_ago:.1f} hours ago")
    else:
        print(f"\n[!] Status: UNKNOWN - Cannot determine score freshness")


def audit_market_data():
    """Check market data availability."""
    print("\n" + "="*80)
    print("6. MARKET DATA (market_exposure_daily)")
    print("="*80)

    # Get latest market data
    with DatabaseContext('read') as cur:
        cur.execute("""
        SELECT
            COUNT(*) as data_points,
            MAX(date) as latest_date,
            AVG(CAST(market_exposure_pct AS FLOAT)) as avg_exposure,
            MAX(CAST(market_exposure_pct AS FLOAT)) as max_exposure,
            MIN(CAST(market_exposure_pct AS FLOAT)) as min_exposure,
            MAX(exposure_tier) as latest_tier
        FROM market_exposure_daily
        WHERE date > CURRENT_DATE - get_interval_sql('7d')
        """)
        market_data = cur.fetchone()

    print(f"\nMarket Exposure Data (Last 7 Days):")
    print(f"  Data points:        {market_data['data_points']}")

    if market_data['latest_date']:
        latest = safe_dt(market_data['latest_date'])
        time_ago = datetime.now() - latest
        hours_ago = time_ago.total_seconds() / 3600
        print(f"  Latest data date:   {market_data['latest_date']} ({hours_ago:.1f} hours ago)")

    if market_data['avg_exposure']:
        print(f"  Avg exposure:       {market_data['avg_exposure']:.2f}%")
    if market_data['max_exposure']:
        print(f"  Max exposure:       {market_data['max_exposure']:.2f}%")
    if market_data['min_exposure']:
        print(f"  Min exposure:       {market_data['min_exposure']:.2f}%")
    if market_data['latest_tier']:
        print(f"  Latest tier:        {market_data['latest_tier']}")

    # Recent market health data
    print(f"\nRecent Market Health (Last 5 Days):")
    with DatabaseContext('read') as cur:
        cur.execute("""
        SELECT date, market_exposure_pct, exposure_tier
        FROM market_exposure_daily
        WHERE date > CURRENT_DATE - INTERVAL '5 days'
        ORDER BY date DESC
        LIMIT 5
        """)
        recent_market = cur.fetchall()

    for market in recent_market:
        exp = market['market_exposure_pct'] or 0
        tier = market['exposure_tier'] or "N/A"
        print(f"  {market['date']}: {exp:.1f}% [{tier}]")

    # Status assessment
    if market_data['data_points'] == 0:
        print(f"\n[X] Status: NO MARKET DATA - Market exposure data not available")
    elif market_data['latest_date']:
        latest = safe_dt(market_data['latest_date'])
        time_ago = datetime.now() - latest
        hours_ago = time_ago.total_seconds() / 3600
        if hours_ago < 24:
            print(f"\n[OK] Status: GOOD - Latest market data available ({hours_ago:.1f}h ago)")
        else:
            print(f"\n[!] Status: STALE - Market data {hours_ago:.1f} hours old")
    else:
        print(f"\n[!] Status: UNKNOWN - Cannot determine data freshness")


def main():
    """Run all audit checks."""
    print("\n" + "="*80)
    print("DATABASE AUDIT - ALGO SYSTEM")
    print(f"Timestamp: {datetime.now()}")
    print("="*80)

    try:
        audit_orchestrator_runs()
        audit_data_freshness()
        audit_portfolio_status()
        audit_signal_generation()
        audit_stock_scores()
        audit_market_data()

        print("\n" + "="*80)
        print("AUDIT COMPLETE")
        print("="*80 + "\n")

    except Exception as e:
        print(f"\n[ERROR] {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
