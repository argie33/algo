#!/usr/bin/env python3
"""Local API server for development - serves dashboard data."""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

import psycopg2.extras

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
            sector_list = [
                {
                    "sector": s,
                    "allocation_pct": round((v / total_value) * 100, 1) if total_value > 0 else 0,
                    "is_overweight": (v / total_value) * 100 > 30 if total_value > 0 else False,
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
        """Return portfolio snapshot."""
        response = {
            "statusCode": 200,
            "data": {
                "total_portfolio_value": 100000.0,
                "total_cash": 25000.0,
                "position_count": 5,
                "daily_return_pct": 0.5,
                "unrealized_pnl_total": 2500.0,
                "last_run": datetime.now(timezone.utc).isoformat(),
                "data_age_seconds": 60,
            },
        }
        self._send_json(200, response)

    def _handle_performance(self) -> None:
        """Return performance metrics."""
        response = {
            "statusCode": 200,
            "data": {
                "total_trades": 150,
                "winning": 90,
                "losing": 55,
                "breakeven": 5,
                "win_rate": 60.0,
                "profit_factor": 1.85,
                "total_pnl": 12500.0,
                "total_pnl_pct": 12.5,
                "avg_trade_pct": 0.45,
                "best_trade": 5.2,
                "worst_trade": -3.8,
                "sharpe": 1.2,
                "sortino": 1.8,
                "calmar": 0.95,
                "max_drawdown": 8.5,
                "cagr": 25.3,
                "best_streak": 12,
                "worst_streak": -4,
                "current_streak": 3,
                "expectancy_r": 0.68,
            },
        }
        self._send_json(200, response)

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
                    buy_sigs.append(
                        {
                            "symbol": s.get("symbol"),
                            "signal": s.get("raw_signal"),
                            "entry_price": float(s.get("entry_price", 0)) if s.get("entry_price") else 0,
                            "quality_score": int(s.get("signal_quality_score", 0))
                            if s.get("signal_quality_score")
                            else 0,
                            "risk_score": float(s.get("risk_score", 0)) if s.get("risk_score") else 0,
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
            response = {
                "statusCode": 200,
                "data": {"buy_sigs": [], "n": 0, "total": 0, "grades": {}, "near": [], "top_a": [], "trend": []},
            }
        self._send_json(200, response)

    def _handle_data_status(self) -> None:
        """Return data loader health status."""
        response = {
            "statusCode": 200,
            "data": {
                "ready_to_trade": True,
                "items": [
                    {
                        "name": "market_data",
                        "st": "ok",
                        "last_check": datetime.now(timezone.utc).isoformat(),
                        "age_hours": 0.1,
                    },
                    {
                        "name": "positions",
                        "st": "ok",
                        "last_check": datetime.now(timezone.utc).isoformat(),
                        "age_hours": 0.1,
                    },
                    {
                        "name": "portfolio",
                        "st": "ok",
                        "last_check": datetime.now(timezone.utc).isoformat(),
                        "age_hours": 0.1,
                    },
                ],
            },
        }
        self._send_json(200, response)

    def _handle_circuit_breakers(self) -> None:
        """Return circuit breaker status."""
        response = {
            "statusCode": 200,
            "data": {
                "breakers": [],
                "any_triggered": False,
                "triggered_count": 0,
                "data_freshness": {"data_age_days": 0, "is_stale": False},
            },
        }
        self._send_json(200, response)

    def _handle_last_run(self) -> None:
        """Return last algo run status."""
        response = {
            "statusCode": 200,
            "data": {
                "run_id": "run_" + datetime.now().strftime("%Y%m%d_%H%M%S"),
                "success": True,
                "halted": False,
                "errored": False,
                "halt_reason": None,
                "summary": "Last run completed successfully",
                "phase_results": [],
                "started_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            },
        }
        self._send_json(200, response)

    def _handle_config(self) -> None:
        """Return algo configuration."""
        response = {
            "statusCode": 200,
            "data": {
                "enabled": True,
                "mode": "paper",
                "risk_config": {"max_position_size": 5.0, "max_portfolio_exposure": 80.0, "max_sector_exposure": 30.0},
            },
        }
        self._send_json(200, response)

    def _handle_markets(self) -> None:
        """Return market data and exposure factors."""
        response = {
            "statusCode": 200,
            "data": {
                "market_status": "open",
                "sp500_price": 5500.0,
                "sp500_change": 0.75,
                "vix": 15.5,
                "market_stage": 2,
                "exposure_factors": {"sector": 0.65, "market": 0.85, "equity": 0.75, "volatility": 0.45},
            },
        }
        self._send_json(200, response)

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
