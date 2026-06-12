#!/usr/bin/env python3
"""
Script to complete Issue #3 migration: Convert all critical fetch_* functions to API-ONLY.

This script documents the exact changes needed to complete the consolidation to API-only data layer.
Run after manually updating dashboard.py with these patterns, or use as reference for editor search/replace.

STATUS: Phase 2 Migration Guide (apply after api_data_layer.py is imported)
"""

# UPDATED FETCH FUNCTIONS FOR API-ONLY CONSOLIDATION

# ============================================================================
# 1. fetch_perf() - REPLACE ENTIRE FUNCTION
# ============================================================================
def fetch_perf_API_ONLY(c):
    """Issue 3 FIX: API-only performance data (eliminates dual-source inconsistency)."""
    try:
        perf = DashboardDataAPI.get_performance() if DashboardDataAPI else {}
        if "_error" in perf or not perf:
            return {}
        return {
            "n": int(perf.get("total_trades") or 0),
            "w": int(perf.get("winning_trades") or 0),
            "l": int(perf.get("losing_trades") or 0),
            "wr": float(perf.get("win_rate") or 0),
            "pnl": float(perf.get("total_pnl_dollars") or 0),
            "streak": 0,
            "sharpe": perf.get("sharpe_ratio"),
            "maxdd": float(perf.get("max_drawdown_pct") or 0),
            "avg_win": float(perf.get("avg_win_pct") or 0),
            "avg_loss": float(perf.get("avg_loss_pct") or 0),
            "profit_factor": perf.get("profit_factor"),
            "expectancy": perf.get("expectancy_r"),
            "avg_r": 0,
            "equity_vals": [],
            "recent_rets": []
        }
    except Exception as e:
        logger.error(f"fetch_perf: {type(e).__name__}: {e}")
        return {}


# ============================================================================
# 2. fetch_positions() - REPLACE ENTIRE FUNCTION
# ============================================================================
def fetch_positions_API_ONLY(c):
    """Issue 3 FIX: API-only positions data (eliminates field name mismatches)."""
    try:
        positions = DashboardDataAPI.get_positions() if DashboardDataAPI else []
        return positions if positions else []
    except Exception as e:
        logger.error(f"fetch_positions: {type(e).__name__}: {e}")
        return []


# ============================================================================
# 3. fetch_recent_trades() - REPLACE ENTIRE FUNCTION
# ============================================================================
def fetch_recent_trades_API_ONLY(c):
    """Issue 3 FIX: API-only trades data (includes exit_r_multiple)."""
    try:
        trades = DashboardDataAPI.get_trades(limit=100) if DashboardDataAPI else []
        # Filter to closed trades only
        closed = [t for t in trades if t.get("status") == "closed"]
        return closed[:10]  # Return last 10
    except Exception as e:
        logger.error(f"fetch_recent_trades: {type(e).__name__}: {e}")
        return []


# ============================================================================
# 4. fetch_signals() - REPLACE ENTIRE FUNCTION
# ============================================================================
def fetch_signals_API_ONLY(c):
    """Issue 3 FIX: API-only signals data."""
    try:
        sig = DashboardDataAPI.get_signals() if DashboardDataAPI else {}
        if "_error" in sig:
            return {"_error": sig["_error"], "n": 0, "total": 0, "buy_sigs": [], "grades": {}, "near": [], "top_a": [], "trend": []}
        return {
            "n": sig.get("n", 0),
            "total": sig.get("total", 0),
            "buy_sigs": sig.get("buy_sigs", [])[:5],
            "grades": sig.get("grades", {}),
            "near": sig.get("near", []),
            "top_a": sig.get("top_a", []),
            "trend": sig.get("trend", [])
        }
    except Exception as e:
        logger.error(f"fetch_signals: {type(e).__name__}: {e}")
        return {"_error": str(e), "n": 0, "total": 0, "buy_sigs": [], "grades": {}, "near": [], "top_a": [], "trend": []}


# ============================================================================
# 5. fetch_portfolio() - REPLACE ENTIRE FUNCTION
# ============================================================================
def fetch_portfolio_API_ONLY(c):
    """Issue 3 FIX: API-only portfolio snapshot."""
    try:
        port = DashboardDataAPI.get_portfolio() if DashboardDataAPI else {}
        if "_error" in port:
            return {}
        return {
            "snapshot_date": port.get("last_run"),
            "total_portfolio_value": port.get("total_portfolio_value") or 0,
            "total_cash": port.get("total_cash") or 0,
            "position_count": port.get("open_positions") or 0,
            "daily_return_pct": port.get("daily_return_pct") or 0,
            "unrealized_pnl_pct": port.get("unrealized_pnl_pct") or 0,
        }
    except Exception as e:
        logger.error(f"fetch_portfolio: {type(e).__name__}: {e}")
        return {"_error": str(e)}


# ============================================================================
# 6. fetch_health() - REPLACE ENTIRE FUNCTION
# ============================================================================
def fetch_health_API_ONLY(c):
    """Issue 3 FIX: API-only data health status."""
    try:
        health = DashboardDataAPI.get_health() if DashboardDataAPI else {}
        if "_error" in health:
            return []
        sources = health.get("sources", [])
        # Convert to format expected by dashboard
        return [
            {
                "table_name": s.get("name"),
                "status": s.get("status"),
                "latest_date": s.get("last_updated"),
                "age_days": s.get("age_hours", 0) / 24 if s.get("age_hours") else None,
                "completion_pct": 100 if s.get("status") == "ok" else 0,
                "error_message": None
            }
            for s in sources
        ]
    except Exception as e:
        logger.error(f"fetch_health: {type(e).__name__}: {e}")
        return []


# ============================================================================
# 7. fetch_algo_config() - REPLACE ENTIRE FUNCTION
# ============================================================================
def fetch_algo_config_API_ONLY(c):
    """Issue 3 FIX: API-only algo configuration."""
    try:
        cfg = DashboardDataAPI.get_config() if DashboardDataAPI else {}
        if "_error" in cfg:
            return {"_error": cfg["_error"]}
        return {
            "enabled": cfg.get("algo_enabled", True),
            "mode": cfg.get("trade_mode", "unknown"),
            "max_pos_pct": float(cfg.get("max_position_size_pct", 0)) if cfg.get("max_position_size_pct") else None,
            "max_pos_n": int(cfg.get("max_positions", 0)) if cfg.get("max_positions") else None,
            "max_sec_n": int(cfg.get("max_positions_per_sector", 0)) if cfg.get("max_positions_per_sector") else None,
            "min_score": float(cfg.get("min_swing_score", 0)) if cfg.get("min_swing_score") else None,
            "base_risk": float(cfg.get("base_risk_pct", 0)) if cfg.get("base_risk_pct") else None,
            "t1_r": float(cfg.get("t1_target_r_multiple", 0)) if cfg.get("t1_target_r_multiple") else None,
            "pyramid": cfg.get("pyramid_enabled", "false").lower() == "true",
        }
    except Exception as e:
        logger.error(f"fetch_algo_config: {type(e).__name__}: {e}")
        return {"_error": str(e)}


# ============================================================================
# 8. fetch_circuit() - REPLACE ENTIRE FUNCTION
# ============================================================================
def fetch_circuit_API_ONLY(c):
    """Issue 3 FIX: API-only circuit breaker status."""
    try:
        cb = DashboardDataAPI.get_circuit_breakers() if DashboardDataAPI else {}
        if "_error" in cb:
            return {"_error": cb["_error"], "bs": [], "any": False, "n": 0}
        breakers = cb.get("breakers", [])
        return {
            "bs": breakers,
            "any": cb.get("any_triggered", False),
            "n": cb.get("triggered_count", 0)
        }
    except Exception as e:
        logger.error(f"fetch_circuit: {type(e).__name__}: {e}")
        return {"_error": str(e), "bs": [], "any": False, "n": 0}


# ============================================================================
# 9. fetch_activity() - REPLACE ENTIRE FUNCTION
# ============================================================================
def fetch_activity_API_ONLY(c):
    """Issue 3 FIX: API-only activity/audit log."""
    try:
        last_run = DashboardDataAPI.get_last_run() if DashboardDataAPI else {}
        if "_error" in last_run or not last_run.get("run_id"):
            return {}

        audit = DashboardDataAPI.get_audit_log(limit=100) if DashboardDataAPI else {}
        audit_items = audit.get("items", [])

        return {
            "run_id": last_run.get("run_id"),
            "run_at": last_run.get("last_run"),
            "phases": last_run.get("phases", []),
            "recent_actions": [
                a for a in audit_items
                if a.get("action_type") in [
                    "entry_executed", "exit_executed", "entry_rejected",
                    "position_exited", "order_placed", "order_rejected"
                ]
            ][:6]
        }
    except Exception as e:
        logger.error(f"fetch_activity: {type(e).__name__}: {e}")
        return {"_error": str(e)}


# ============================================================================
# MIGRATION CHECKLIST
# ============================================================================
MIGRATION_CHECKLIST = """
Phase 2 Migration: Update All Critical Fetch Functions to API-ONLY

[ ] 1. fetch_perf() — Replace with fetch_perf_API_ONLY above
[ ] 2. fetch_positions() — Replace with fetch_positions_API_ONLY above (already partially done)
[ ] 3. fetch_recent_trades() — Replace with fetch_recent_trades_API_ONLY above
[ ] 4. fetch_signals() — Replace with fetch_signals_API_ONLY above
[ ] 5. fetch_portfolio() — Replace with fetch_portfolio_API_ONLY above
[ ] 6. fetch_health() — Replace with fetch_health_API_ONLY above
[ ] 7. fetch_algo_config() — Replace with fetch_algo_config_API_ONLY above
[ ] 8. fetch_circuit() — Replace with fetch_circuit_API_ONLY above
[ ] 9. fetch_activity() — Replace with fetch_activity_API_ONLY above

Phase 3 Verification:
[ ] Dashboard starts without errors
[ ] All panels display data correctly
[ ] No "undefined field" errors in logs
[ ] Test with API unavailable (should show empty panels, not crash)

Phase 4 Cleanup:
[ ] Remove DB connection pool initialization (no longer needed)
[ ] Remove remaining DB query functions (fetch_sector_ranking, etc. if moving to API)
[ ] Document API-first architecture decision in README
"""

if __name__ == "__main__":
    print("API Migration Script - Phase 2 Reference")
    print("=" * 70)
    print("This script documents the exact code changes needed to complete")
    print("Issue #3 consolidation to API-ONLY data layer.")
    print()
    print("INSTRUCTIONS:")
    print("1. Copy the fetch_*_API_ONLY functions above")
    print("2. Replace corresponding fetch_* functions in dashboard.py")
    print("3. Run through the migration checklist above")
    print()
    print(MIGRATION_CHECKLIST)
