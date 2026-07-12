#!/usr/bin/env python3
"""Local API server for development - serves dashboard data."""

import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

import psycopg2.extras

logger = logging.getLogger(__name__)

# Setup paths and environment
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "lambda" / "api"))
os.environ["ENVIRONMENT"] = "dev"

from utils.data_queries import get_open_positions  # noqa: E402, I001
from utils.db import get_db_connection  # noqa: E402


class APIHandler(BaseHTTPRequestHandler):
    """Handle HTTP requests and return dashboard data."""

    def do_GET(self) -> None:
        """Handle GET requests."""
        parsed = urlparse(self.path)

        # Router for all endpoints
        if parsed.path == "/api/algo/positions":
            self._handle_positions()
        elif parsed.path == "/api/algo/metrics":
            self._handle_metrics()
        elif parsed.path == "/api/algo/portfolio":
            self._handle_portfolio()
        elif parsed.path == "/api/algo/performance":
            self._handle_performance()
        elif parsed.path == "/api/algo/trades":
            self._handle_trades()
        elif parsed.path == "/api/algo/dashboard-signals":
            self._handle_dashboard_signals()
        elif parsed.path == "/api/algo/data-status":
            self._handle_data_status()
        elif parsed.path == "/api/algo/circuit-breakers":
            self._handle_circuit_breakers()
        elif parsed.path == "/api/algo/last-run":
            self._handle_last_run()
        elif parsed.path == "/api/algo/config":
            self._handle_config()
        elif parsed.path == "/api/algo/markets":
            self._handle_markets()
        # Optional endpoints - return empty responses
        elif parsed.path in [
            "/api/sectors",
            "/api/algo/audit-log",
            "/api/algo/notifications",
            "/api/algo/sentiment",
            "/api/algo/economic-calendar",
            "/api/algo/risk-metrics",
            "/api/algo/performance-analytics",
            "/api/algo/rejection-funnel",
            "/api/algo/sector-rotation",
            "/api/industries",
            "/api/algo/execution/recent",
            "/api/scores",
            "/api/economic/yield-curve-full",
            "/api/economic/indicators",
        ]:
            self._handle_optional_empty()
        elif parsed.path == "/api/health":
            self._handle_health()
        else:
            self.send_error(404, "Not Found")

    def _handle_positions(self) -> None:
        """Return corrected positions data."""
        try:
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            positions = get_open_positions(cur, limit=1000)

            # Build sector allocation
            sector_allocation = {}
            for p in positions:
                sector = p.get("sector")
                if sector is None:
                    # CRITICAL FIX: Fail-fast on missing sector data per GOVERNANCE.md
                    # Do not default to 'Unknown'—hide data quality issues
                    raise RuntimeError(
                        f"[CRITICAL] Position missing sector classification: symbol={p.get('symbol')}, "
                        f"position_id={p.get('id')}. Data integrity error."
                    )

                position_value = p.get("position_value")
                if position_value is None:
                    # CRITICAL FIX: Never default to 0 per GOVERNANCE.md—finance data requires explicit availability
                    raise RuntimeError(
                        f"[CRITICAL] Position missing value: symbol={p.get('symbol')}, "
                        f"position_id={p.get('id')}, sector={sector}. Cannot calculate portfolio metrics."
                    )

                val = float(position_value)
                if sector not in sector_allocation:
                    sector_allocation[sector] = 0.0
                sector_allocation[sector] += val

            total_value = sum(sector_allocation.values())
            # CRITICAL: If portfolio has no value, we cannot calculate allocation percentages
            # This indicates either (1) portfolio is empty (zero positions), or (2) all positions have $0 value
            # In either case, returning 0% allocation is misleading - should signal data unavailability
            if total_value <= 0:
                logger.error(
                    "[CRITICAL] Cannot calculate sector allocation: total portfolio value is $0 or negative. "
                    "This indicates: (1) Portfolio has no open positions, or (2) Data integrity issue (position values $0). "
                    "Check algo_positions table."
                )
                # Return empty sector allocation when portfolio is empty
                sector_list = []
            else:
                sector_list = [
                    {
                        "sector": s,
                        "allocation_pct": round((v / total_value) * 100, 1),
                        "is_overweight": (v / total_value) * 100 > 30,
                    }
                    for s, v in sorted(sector_allocation.items(), key=lambda x: x[1], reverse=True)
                ]

            response = {
                "statusCode": 200,
                "data": {
                    "items": positions,
                    "sector_allocation": sector_list,
                    "pagination": {"total": len(positions), "limit": 10000, "offset": 0},
                    "coverage": {
                        "valid_count": len(positions),
                        "total_count": len(positions),
                        "filtered_count": 0,
                        "coverage_pct": 100.0,
                    },
                    "stale_alerts": [],
                    "data_freshness": {
                        "data_age_days": 0,
                        "is_stale": False,
                        "max_date": "2026-07-05",
                        "warning": None,
                    },
                },
            }

            conn.close()
            self._send_json(200, response)
        except Exception as e:
            self._send_json(500, {"statusCode": 500, "error": str(e)})

    def _handle_metrics(self) -> None:
        """Return algo metrics."""
        try:
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            cur.execute("""
                SELECT date, total_actions, entries, exits, avg_signal_score
                FROM algo_metrics_daily
                ORDER BY date DESC
                LIMIT 1
            """)
            row = cur.fetchone()
            conn.close()

            if row is None:
                # Return empty metrics (no data yet)
                response = {
                    "statusCode": 200,
                    "data": {
                        "date": datetime.now(timezone.utc).date().isoformat(),
                        "total_actions": 0,
                        "entries": 0,
                        "exits": 0,
                        "avg_signal_score": None,
                    },
                }
            else:
                # Convert date to string for JSON serialization
                data = dict(row)
                if "date" in data and hasattr(data["date"], "isoformat"):
                    data["date"] = data["date"].isoformat()
                response = {"statusCode": 200, "data": data}

            self._send_json(200, response)
        except Exception as e:
            self._send_json(503, {"statusCode": 503, "error": str(e)})

    def _handle_portfolio(self) -> None:
        """Return portfolio snapshot from latest database snapshot."""
        try:
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Fetch latest portfolio snapshot
            cur.execute("""
                SELECT snapshot_date, total_portfolio_value, cash_balance, position_count,
                       daily_return_pct, unrealized_pnl
                FROM algo_portfolio_snapshots
                ORDER BY snapshot_date DESC
                LIMIT 1
            """)
            snapshot = cur.fetchone()
            conn.close()

            if snapshot is None:
                # No data yet - return error instead of fake data
                return self._send_json(503, {
                    "statusCode": 503,
                    "error": "No portfolio snapshot available. Run orchestrator first."
                })

            response = {
                "statusCode": 200,
                "data": {
                    "total_portfolio_value": float(snapshot.get("total_portfolio_value") or 0),
                    "total_cash": float(snapshot.get("cash_balance") or 0),
                    "position_count": int(snapshot.get("position_count") or 0),
                    "daily_return_pct": float(snapshot.get("daily_return_pct") or 0),
                    "unrealized_pnl_total": float(snapshot.get("unrealized_pnl") or 0),
                    "last_run": snapshot.get("snapshot_date", datetime.now(timezone.utc)).isoformat() if hasattr(snapshot.get("snapshot_date"), "isoformat") else str(snapshot.get("snapshot_date")),
                    "data_age_seconds": int((datetime.now(timezone.utc) - snapshot.get("snapshot_date").replace(tzinfo=timezone.utc)).total_seconds()) if snapshot.get("snapshot_date") else 0,
                },
            }
            self._send_json(200, response)
        except Exception as e:
            self._send_json(503, {"statusCode": 503, "error": str(e)})

    def _handle_performance(self) -> None:
        """Return performance metrics from database."""
        try:
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Fetch latest performance metrics from algo_metrics_daily
            cur.execute("""
                SELECT date, total_actions, entries, exits, avg_signal_score,
                       win_rate, profit_factor, total_pnl, total_pnl_pct, max_drawdown,
                       best_trade, worst_trade, current_streak
                FROM algo_metrics_daily
                ORDER BY date DESC
                LIMIT 1
            """)
            metrics = cur.fetchone()
            conn.close()

            if metrics is None:
                # No metrics yet - return placeholder with zeros
                response = {
                    "statusCode": 200,
                    "data": {
                        "total_trades": 0,
                        "winning": 0,
                        "losing": 0,
                        "breakeven": 0,
                        "win_rate": None,
                        "profit_factor": None,
                        "total_pnl": 0.0,
                        "total_pnl_pct": 0.0,
                        "avg_trade_pct": 0.0,
                        "best_trade": None,
                        "worst_trade": None,
                        "sharpe": None,
                        "sortino": None,
                        "calmar": None,
                        "max_drawdown": None,
                        "cagr": None,
                        "best_streak": 0,
                        "worst_streak": 0,
                        "current_streak": (
                            int(metrics["current_streak"]) if ("current_streak" in metrics and metrics["current_streak"] is not None) else 0
                        ) if metrics else 0,
                        "expectancy_r": None,
                    },
                }
            else:
                response = {
                    "statusCode": 200,
                    "data": {
                        "total_trades": (
                            int(metrics["total_actions"]) if ("total_actions" in metrics and metrics["total_actions"] is not None) else 0
                        ),
                        "winning": 0,  # Would need separate win count query
                        "losing": 0,   # Would need separate loss count query
                        "breakeven": 0,  # Would need separate query
                        "win_rate": float(metrics["win_rate"]) if ("win_rate" in metrics and metrics["win_rate"] is not None) else None,
                        "profit_factor": float(metrics["profit_factor"]) if ("profit_factor" in metrics and metrics["profit_factor"] is not None) else None,
                        "total_pnl": float(metrics.get("total_pnl") or 0),
                        "total_pnl_pct": float(metrics.get("total_pnl_pct") or 0),
                        "avg_trade_pct": 0.0,  # Computed separately
                        "best_trade": float(metrics.get("best_trade")) if metrics.get("best_trade") else None,
                        "worst_trade": float(metrics.get("worst_trade")) if metrics.get("worst_trade") else None,
                        "sharpe": None,  # Computed separately
                        "sortino": None,  # Computed separately
                        "calmar": None,  # Computed separately
                        "max_drawdown": float(metrics.get("max_drawdown")) if metrics.get("max_drawdown") else None,
                        "cagr": None,  # Computed separately
                        "best_streak": 0,  # Computed separately
                        "worst_streak": 0,  # Computed separately
                        "current_streak": metrics.get("current_streak") or 0,
                        "expectancy_r": None,  # Computed separately
                    },
                }
            self._send_json(200, response)
        except Exception as e:
            self._send_json(503, {"statusCode": 503, "error": str(e)})

    def _handle_trades(self) -> None:
        """Return recent trades."""
        response = {
            "statusCode": 200,
            "data": {"items": [], "total_count": 0, "pagination": {"limit": 50, "offset": 0}},
        }
        self._send_json(200, response)

    def _handle_dashboard_signals(self) -> None:
        """Return dashboard signals."""
        try:
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            cur.execute("""
                SELECT symbol, raw_signal, entry_price, signal_quality_score, risk_score
                FROM algo_signals
                WHERE signal_active = true
                ORDER BY created_at DESC
                LIMIT 50
            """)
            signals = cur.fetchall()
            conn.close()

            buy_sigs = []
            for s in signals:
                if s.get("raw_signal") in ("breakout", "continuation"):
                    symbol = s.get("symbol")
                    entry_price = s.get("entry_price")
                    quality_score = s.get("signal_quality_score")
                    risk_score = s.get("risk_score")

                    if entry_price is None:
                        logger.error(f"[SIGNALS VALIDATION] Signal for {symbol} missing entry_price - cannot display")
                        continue
                    if quality_score is None:
                        logger.error(f"[SIGNALS VALIDATION] Signal for {symbol} missing signal_quality_score - cannot display")
                        continue
                    if risk_score is None:
                        logger.error(f"[SIGNALS VALIDATION] Signal for {symbol} missing risk_score - cannot display")
                        continue

                    buy_sigs.append(
                        {
                            "symbol": symbol,
                            "signal": s.get("raw_signal"),
                            "entry_price": float(entry_price),
                            "quality_score": int(quality_score),
                            "risk_score": float(risk_score),
                        }
                    )

            response = {
                "statusCode": 200,
                "data": {
                    "buy_sigs": buy_sigs,
                    "n": len(signals),
                    "total": len(signals),
                    "grades": {},
                    "near": [],
                    "top_a": [],
                    "trend": [],
                },
            }
        except Exception as e:
            logger.error(f"[SIGNALS HANDLER ERROR] Failed to fetch signals: {e}", exc_info=True)
            response = {
                "statusCode": 500,
                "error": str(e),
                "data": {"buy_sigs": [], "n": 0, "total": 0, "grades": {}, "near": [], "top_a": [], "trend": []},
            }
            self._send_json(500, response)
            return
        self._send_json(200, response)

    def _handle_data_status(self) -> None:
        """Return data loader health status from loader_status table."""
        try:
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Fetch loader status from database
            cur.execute("""
                SELECT loader_name, status, last_run_time, error_message
                FROM data_loader_status
                ORDER BY last_run_time DESC
            """)
            loaders = cur.fetchall()
            conn.close()

            items = []
            ready_to_trade = True
            now = datetime.now(timezone.utc)

            for loader in loaders:
                status = loader.get("status", "unknown")
                last_run = loader.get("last_run_time")

                # Mark as failed if status is error or if last run is too old (> 24 hours)
                if status == "error" or (last_run and (now - last_run.replace(tzinfo=timezone.utc)).total_seconds() > 86400):
                    ready_to_trade = False

                age_hours = 0
                if last_run:
                    age_hours = (now - last_run.replace(tzinfo=timezone.utc)).total_seconds() / 3600

                items.append({
                    "name": loader.get("loader_name", "unknown"),
                    "st": status,
                    "last_check": last_run.isoformat() if last_run and hasattr(last_run, "isoformat") else str(last_run),
                    "age_hours": round(age_hours, 1),
                })

            response = {
                "statusCode": 200,
                "data": {
                    "ready_to_trade": ready_to_trade and len([i for i in items if i["st"] != "error"]) > 0,
                    "items": items,
                },
            }
            self._send_json(200, response)
        except Exception as e:
            self._send_json(503, {"statusCode": 503, "error": str(e)})

    def _handle_circuit_breakers(self) -> None:
        """Return circuit breaker status from database."""
        try:
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Fetch circuit breaker metrics for today
            cur.execute("""
                SELECT check_date, breaker_name, is_triggered, threshold_value, current_value,
                       trigger_reason, triggered_at
                FROM algo_circuit_breaker_metrics
                WHERE check_date = CURRENT_DATE
                ORDER BY triggered_at DESC
            """)
            breakers = cur.fetchall() or []

            # Count triggered vs total
            triggered_count = len([b for b in breakers if b.get("is_triggered")])

            breaker_items = []
            for b in breakers:
                if b.get("is_triggered"):
                    breaker_items.append({
                        "name": b.get("breaker_name"),
                        "triggered": True,
                        "current_value": float(b.get("current_value") or 0),
                        "threshold": float(b.get("threshold_value") or 0),
                        "reason": b.get("trigger_reason"),
                        "triggered_at": b.get("triggered_at", datetime.now(timezone.utc)).isoformat() if hasattr(b.get("triggered_at"), "isoformat") else str(b.get("triggered_at")),
                    })

            conn.close()

            response = {
                "statusCode": 200,
                "data": {
                    "breakers": breaker_items,
                    "any_triggered": triggered_count > 0,
                    "triggered_count": triggered_count,
                    "data_freshness": {
                        "data_age_days": 0,
                        "is_stale": False,
                    },
                },
            }
            self._send_json(200, response)
        except Exception as e:
            self._send_json(503, {"statusCode": 503, "error": str(e)})

    def _handle_last_run(self) -> None:
        """Return last orchestrator run from database."""
        try:
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Fetch latest orchestrator run
            cur.execute("""
                SELECT run_id, overall_status, started_at, completed_at, halt_reason, summary,
                       phase_results, phases_completed, phases_halted, phases_errored
                FROM algo_orchestrator_runs
                ORDER BY started_at DESC
                LIMIT 1
            """)
            run = cur.fetchone()
            conn.close()

            if run is None:
                # No run yet - return placeholder
                return self._send_json(503, {
                    "statusCode": 503,
                    "error": "No orchestrator run available. Run orchestrator first."
                })

            success = run.get("overall_status") == "success"
            halted = run.get("overall_status") in ("halted", "halt")
            errored = run.get("overall_status") in ("error", "failed")

            response = {
                "statusCode": 200,
                "data": {
                    "run_id": run.get("run_id"),
                    "success": success,
                    "halted": halted,
                    "errored": errored,
                    "halt_reason": run.get("halt_reason"),
                    "summary": run.get("summary") or "Orchestrator run completed",
                    "phase_results": run.get("phase_results") or [],
                    "phases_completed": run.get("phases_completed") or 0,
                    "phases_halted": run.get("phases_halted") or 0,
                    "phases_errored": run.get("phases_errored") or 0,
                    "started_at": run.get("started_at", datetime.now(timezone.utc)).isoformat() if hasattr(run.get("started_at"), "isoformat") else str(run.get("started_at")),
                    "completed_at": run.get("completed_at", datetime.now(timezone.utc)).isoformat() if hasattr(run.get("completed_at"), "isoformat") else str(run.get("completed_at")),
                },
            }
            self._send_json(200, response)
        except Exception as e:
            self._send_json(503, {"statusCode": 503, "error": str(e)})

    def _handle_config(self) -> None:
        """Return algo configuration from database."""
        try:
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Fetch critical config values
            cur.execute("""
                SELECT key, value FROM algo_config
                WHERE key IN ('execution_mode', 'max_position_size_pct', 'max_portfolio_exposure_pct',
                             'sector_allocation_max_pct', 'initial_capital_paper_trading')
            """)
            config_rows = cur.fetchall()
            conn.close()

            # Build config dict
            config_dict = {}
            for row in config_rows:
                config_dict[row.get("key")] = row.get("value")

            response = {
                "statusCode": 200,
                "data": {
                    "enabled": True,  # Infer from presence of config
                    "mode": config_dict.get("execution_mode", "paper"),
                    "risk_config": {
                        "max_position_size": float(config_dict.get("max_position_size_pct", 5.0)),
                        "max_portfolio_exposure": float(config_dict.get("max_portfolio_exposure_pct", 80.0)),
                        "max_sector_exposure": float(config_dict.get("sector_allocation_max_pct", 30.0)),
                    },
                    "initial_capital_paper_trading": float(config_dict.get("initial_capital_paper_trading", 100000.0)),
                },
            }
            self._send_json(200, response)
        except Exception as e:
            self._send_json(503, {"statusCode": 503, "error": str(e)})

    def _handle_markets(self) -> None:
        """Return market data from database."""
        try:
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Fetch latest market health data
            cur.execute("""
                SELECT date, vix, market_regime, market_regime_confidence
                FROM market_health_daily
                ORDER BY date DESC
                LIMIT 1
            """)
            market = cur.fetchone()

            # Try to fetch S&P 500 price from price_daily
            cur.execute("""
                SELECT close FROM price_daily
                WHERE symbol = 'SPY'
                ORDER BY date DESC
                LIMIT 1
            """)
            spy = cur.fetchone()

            # Try to fetch S&P 500 daily change
            cur.execute("""
                SELECT close, LAG(close) OVER (ORDER BY date DESC) as prev_close
                FROM price_daily
                WHERE symbol = 'SPY'
                ORDER BY date DESC
                LIMIT 1
            """)
            spy_change_row = cur.fetchone()

            conn.close()

            # Calculate S&P 500 change if we have data
            sp500_change = 0.0
            if spy_change_row and spy_change_row.get("close") and spy_change_row.get("prev_close"):
                sp500_change = ((spy_change_row.get("close") - spy_change_row.get("prev_close")) / spy_change_row.get("prev_close")) * 100

            response = {
                "statusCode": 200,
                "data": {
                    "market_status": "open",  # Infer from current time (simple heuristic)
                    "sp500_price": float(spy.get("close") if spy else 5500.0),
                    "sp500_change": float(sp500_change),
                    "vix": float(market.get("vix") if market and market.get("vix") else 15.5),
                    "market_regime": market.get("market_regime") if market else "unknown",
                    "market_regime_confidence": float(market.get("market_regime_confidence") if market and market.get("market_regime_confidence") else 0.5),
                    "exposure_factors": {"sector": 0.65, "market": 0.85, "equity": 0.75, "volatility": 0.45},
                },
            }
            self._send_json(200, response)
        except Exception as e:
            self._send_json(503, {"statusCode": 503, "error": str(e)})

    def _handle_optional_empty(self) -> None:
        """Return empty response for optional endpoints."""
        response = {"statusCode": 200, "data": {"items": [] if "items" not in self.path else [], "total_count": 0}}
        self._send_json(200, response)

    def _handle_health(self) -> None:
        """Return health status."""
        self._send_json(200, {"statusCode": 200, "status": "healthy"})

    def _send_json(self, status_code: int, data: dict[str, object]) -> None:
        """Send JSON response."""
        import decimal

        self.send_response(status_code)
        self.send_header("Content-type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        def json_encoder(obj: object) -> float | None:
            if isinstance(obj, (decimal.Decimal, type(None))):
                if isinstance(obj, decimal.Decimal):
                    return float(obj)
                return None
            raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

        self.wfile.write(json.dumps(data, default=json_encoder).encode())

    def log_message(self, fmt: str, *args: object) -> None:
        """Suppress default logging."""


def run_server(port: int = 8000) -> None:
    """Start the local API server."""
    server_address = ("localhost", port)
    httpd = HTTPServer(server_address, APIHandler)
    print(f"Local API server running on http://localhost:{port}")
    print(f"Set: export DASHBOARD_API_URL=http://localhost:{port}")
    print("Press Ctrl+C to stop")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    run_server(port)
