#!/usr/bin/env python3
from utils.db import DatabaseContext
import json
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

print('=== LAST SUCCESSFUL RUN ANALYSIS ===\n')

with DatabaseContext('read') as cur:
    # Get the last successful run and see what it did
    cur.execute('''
        SELECT run_id, started_at, completed_at, phase_results
        FROM orchestrator_execution_log
        WHERE overall_status IN ('success', 'ok')
        ORDER BY started_at DESC
        LIMIT 1
    ''')

    row = cur.fetchone()
    if row:
        run_id = row[0] if isinstance(row, (tuple, list)) else row.get('run_id')
        started = row[1] if isinstance(row, (tuple, list)) else row.get('started_at')
        completed = row[2] if isinstance(row, (tuple, list)) else row.get('completed_at')
        results_raw = row[3] if isinstance(row, (tuple, list)) else row.get('phase_results')

        print(f'Run: {run_id}')
        print(f'Started: {started}')
        print(f'Completed: {completed}')
        if completed:
            print(f'Duration: {(completed - started).total_seconds():.0f}s')
        print()

        if results_raw:
            try:
                phases = json.loads(results_raw) if isinstance(results_raw, str) else results_raw
                if isinstance(phases, dict):
                    print('PHASE RESULTS:')
                    for pnum in sorted(phases.keys(), key=lambda x: int(x) if x.isdigit() else 99):
                        pinfo = phases[pnum]
                        if isinstance(pinfo, dict):
                            pstat = pinfo.get('status', '?')
                            pres = pinfo.get('result', '')
                            print(f'  Phase {pnum}: {pstat}')
                            if pres and len(str(pres)) > 0:
                                print(f'    Result: {str(pres)[:100]}')
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse phase results JSON: {e} (invalid JSON format)")
                print('Could not parse phase results (JSON decode error)')
            except (TypeError, ValueError, AttributeError) as e:
                logger.error(f"Failed to process phase results: {type(e).__name__}: {e}")
                print(f'Could not parse phase results ({type(e).__name__})')
            except Exception as e:
                logger.error(f"Unexpected error parsing phase results: {type(e).__name__}: {e}")
                print(f'Could not parse phase results (unexpected error)')

# Now check if this run generated any signals or trades
print('\n=== SIGNALS & TRADES AFTER LAST SUCCESSFUL RUN ===')

with DatabaseContext('read') as cur:
    cur.execute('''
        SELECT COUNT(*), MAX(entry_date)
        FROM algo_trades
        WHERE entry_date >= '2026-07-06'::date
    ''')
    row = cur.fetchone()
    trade_count = row[0] if row and isinstance(row, (tuple, list)) else 0
    trade_date = row[1] if row and isinstance(row, (tuple, list)) and len(row) > 1 else None
    print(f'Trades created on 2026-07-06: {trade_count}')
    print(f'Latest trade date: {trade_date}')

    # Check if Phase 7 generated any candidates
    cur.execute('''
        SELECT COUNT(DISTINCT symbol), MAX(date)
        FROM buy_sell_daily
        WHERE signal_type = 'BUY' AND date >= '2026-07-06'::date
    ''')
    row = cur.fetchone()
    signal_count = row[0] if row and isinstance(row, (tuple, list)) else 0
    signal_date = row[1] if row and isinstance(row, (tuple, list)) and len(row) > 1 else None
    print(f'BUY signals on 2026-07-06: {signal_count}')
    print(f'Latest signal date: {signal_date}')

print('\n=== TRADES TABLE vs ALPACA POSITIONS VIEW ===')
with DatabaseContext('read') as cur:
    cur.execute("SELECT COUNT(*) FROM algo_positions_with_risk WHERE status = 'open'")
    row = cur.fetchone()
    view_open = row[0] if row else 0

    cur.execute("SELECT COUNT(*) FROM algo_trades WHERE status = 'open'")
    row = cur.fetchone()
    trades_open = row[0] if row else 0

    print(f'Positions view (open): {view_open}')
    print(f'Trades table (open): {trades_open}')
    print(f'Mismatch: {view_open != trades_open}')
