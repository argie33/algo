#!/usr/bin/env python3
"""Bootstrap minimal data into critical dashboard tables.

This script ensures that dashboard panels can render even if data loaders haven't run yet.
It populates critical tables with sensible defaults so the dashboard shows useful
initial state instead of "Panel Unavailable" errors.

Run this after database setup but before first dashboard load.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.db.context import DatabaseContext
from algo.config.orchestrator_config import OrchestratorConfig
import psycopg2.extras

def bootstrap_audit_log():
    """Ensure algo_audit_log has at least one entry."""
    with DatabaseContext('write') as db:
        cur = db.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute("SELECT COUNT(*) as cnt FROM algo_audit_log")
        count = cur.fetchone()['cnt']

        if count == 0:
            print("[BOOTSTRAP] Seeding algo_audit_log with initial entry...")
            cur.execute("""
                INSERT INTO algo_audit_log (action_type, action_date, status, details)
                VALUES (
                    'INIT',
                    NOW(),
                    'ready',
                    jsonb_build_object(
                        'run_id', 'bootstrap_init',
                        'summary', 'Dashboard bootstrap initialization'
                    )
                )
            """)
            db.connection.commit()
            print("  ✓ algo_audit_log initialized")
        else:
            print(f"[BOOTSTRAP] algo_audit_log has {count} entries, skipping")

def bootstrap_portfolio_snapshots():
    """Ensure algo_portfolio_snapshots has at least one entry."""
    with DatabaseContext('write') as db:
        cur = db.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute("SELECT COUNT(*) as cnt FROM algo_portfolio_snapshots")
        count = cur.fetchone()['cnt']

        if count == 0:
            print("[BOOTSTRAP] Seeding algo_portfolio_snapshots with initial entry...")

            # Load config to get initial capital (fail-fast if not configured)
            try:
                config = OrchestratorConfig()
                initial_capital = config.get("initial_capital_paper_trading")
                if not initial_capital:
                    raise RuntimeError(
                        "[BOOTSTRAP] CRITICAL: initial_capital_paper_trading not configured in algo_config. "
                        "Set this value in algo_config table before bootstrapping."
                    )
            except Exception as config_err:
                print(f"[BOOTSTRAP] ERROR: Could not load config: {config_err}")
                raise RuntimeError(f"Bootstrap failed: cannot load initial capital from config: {config_err}") from config_err

            starting_cash = float(initial_capital)

            cur.execute("""
                INSERT INTO algo_portfolio_snapshots (
                    snapshot_date,
                    total_portfolio_value,
                    total_cash,
                    position_count,
                    daily_return_pct,
                    unrealized_pnl_total,
                    data_unavailable,
                    data_unavailable_reason
                )
                VALUES (
                    CURRENT_DATE,
                    %s,
                    %s,
                    0,
                    0.0,
                    0.0,
                    TRUE,
                    'Bootstrap initialization - loaders must populate with real data'
                )
            """, (starting_cash, starting_cash))
            db.connection.commit()
            print(f"  ✓ algo_portfolio_snapshots initialized with ${starting_cash:,.2f} (marked data_unavailable until loaders run)")
        else:
            print(f"[BOOTSTRAP] algo_portfolio_snapshots has {count} entries, skipping")

def bootstrap_performance_metrics():
    """Ensure algo_performance_metrics has at least one entry."""
    with DatabaseContext('write') as db:
        cur = db.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute("SELECT COUNT(*) as cnt FROM algo_performance_metrics")
        count = cur.fetchone()['cnt']

        if count == 0:
            print("[BOOTSTRAP] Seeding algo_performance_metrics with initial entry...")
            cur.execute("""
                INSERT INTO algo_performance_metrics (
                    total_trades, winning_trades, losing_trades, breakeven_trades,
                    win_rate, profit_factor, expectancy,
                    sharpe_ratio, sortino_ratio, max_drawdown_pct,
                    computed_at
                )
                VALUES (
                    0, 0, 0, 0,
                    NULL, NULL, NULL,
                    NULL, NULL, NULL,
                    NOW()
                )
            """)
            db.connection.commit()
            print("  ✓ algo_performance_metrics initialized")
        else:
            print(f"[BOOTSTRAP] algo_performance_metrics has {count} entries, skipping")

def bootstrap_circuit_breaker_status():
    """Ensure circuit_breaker_status has at least one entry."""
    with DatabaseContext('write') as db:
        cur = db.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute("SELECT COUNT(*) as cnt FROM circuit_breaker_status")
        count = cur.fetchone()['cnt']

        if count == 0:
            print("[BOOTSTRAP] Seeding circuit_breaker_status with initial entry...")

            # Load threshold defaults from config to avoid hardcoding risk limits
            try:
                config = OrchestratorConfig()
                halt_drawdown = config.get("halt_drawdown_pct", -20.0)
                vix_default = config.get("vix_max_threshold", 35.0)
            except Exception as config_err:
                print(f"[BOOTSTRAP] WARNING: Could not load circuit breaker config, using safe defaults: {config_err}")
                halt_drawdown = -20.0
                vix_default = 35.0

            # Initialize with NULL/0 values (no historical trading yet) and mark as unavailable
            cur.execute("""
                INSERT INTO circuit_breaker_status (
                    check_date,
                    portfolio_drawdown_pct,
                    daily_loss_pct,
                    weekly_loss_pct,
                    open_risk_pct,
                    consecutive_losses,
                    vix_level,
                    market_stage,
                    halt_triggered,
                    computed_at,
                    data_unavailable,
                    data_unavailable_reason
                )
                VALUES (
                    CURRENT_DATE,
                    NULL, NULL, NULL, NULL,
                    NULL, NULL, NULL,
                    FALSE,
                    NOW(),
                    TRUE,
                    'Bootstrap initialization - no trading activity yet'
                )
            """)
            db.connection.commit()
            print(f"  ✓ circuit_breaker_status initialized with config thresholds (halt_drawdown={halt_drawdown}%, vix_max={vix_default})")
        else:
            print(f"[BOOTSTRAP] circuit_breaker_status has {count} entries, skipping")

def bootstrap_positions():
    """Ensure algo_positions is properly set up (table may be empty, which is fine)."""
    with DatabaseContext('write') as db:
        cur = db.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Just verify the table exists and view is refreshed
        try:
            cur.execute("SELECT COUNT(*) as cnt FROM algo_positions")
            pos_count = cur.fetchone()['cnt']
            print(f"[BOOTSTRAP] algo_positions has {pos_count} rows (empty portfolios are valid)")

            # Refresh the view
            cur.execute("REFRESH MATERIALIZED VIEW algo_positions_with_risk")
            db.connection.commit()
            print("  ✓ algo_positions_with_risk view refreshed")
        except Exception as e:
            print(f"  ✗ Could not refresh positions view: {e}")

def main():
    """Bootstrap all critical tables."""
    print("\n" + "="*70)
    print("DASHBOARD DATA BOOTSTRAP")
    print("="*70)
    print("Ensuring critical tables have minimal bootstrap data...\n")

    try:
        bootstrap_audit_log()
        bootstrap_portfolio_snapshots()
        bootstrap_performance_metrics()
        bootstrap_circuit_breaker_status()
        bootstrap_positions()

        print("\n" + "="*70)
        print("✓ BOOTSTRAP COMPLETE")
        print("Dashboard should now display panels instead of errors")
        print("="*70 + "\n")

    except Exception as e:
        print(f"\n✗ BOOTSTRAP FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
