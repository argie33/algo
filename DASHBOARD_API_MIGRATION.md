# Dashboard API Migration - AWS Only, No Local Fallbacks

## Objective
Convert dashboard.py to use ONLY AWS Lambda API endpoints. Remove all direct RDS database queries and local fallbacks.

## API Endpoint Mappings

| Fetcher Function | Old Source | New API Endpoint | Notes |
|---|---|---|---|
| fetch_run | orchestrator_execution_log | `/api/algo/last-run` | Last execution status |
| fetch_algo_config | algo_config | `/api/algo/config` | Algorithm configuration |
| fetch_market | market_exposure_daily + market_health_daily | `/api/algo/markets` | Market exposure & health |
| fetch_exposure_factors | market_exposure_daily | `/api/algo/exposure-policy` | Exposure factors |
| fetch_portfolio | algo_portfolio_snapshots | `/api/algo/status` | Portfolio data (in status.portfolio) |
| fetch_perf | algo_performance_daily | `/api/algo/performance` | Performance metrics |
| fetch_positions | algo_positions | `/api/algo/positions` | Current open positions - AWS ONLY |
| fetch_recent_trades | algo_trades | `/api/algo/trades?limit=10` | Recent closed trades |
| fetch_signals | algo_signals_evaluated | `/api/algo/dashboard-signals` | Dashboard signals |
| fetch_sector_ranking | sector_ranking | `/api/sectors` | Sector rankings |
| fetch_activity | algo_audit_log | `/api/algo/audit-log` | Audit log & activity |
| fetch_health | data_loader_status | `/api/algo/data-status` | Data loader health |
| fetch_economic_pulse | economic_data | `/api/economic` | Economic indicators |
| fetch_algo_metrics | algo_metrics_daily | `/api/algo/status` | In status.metrics |
| fetch_notifications | algo_notifications | `/api/algo/notifications` | Notifications |
| fetch_sentiment | market_sentiment | `/api/sentiment` | Market sentiment/Fear-Greed |
| fetch_economic_calendar | economic_calendar | `/api/economic` | In economic.calendar |
| fetch_risk_metrics | algo_risk_daily | `/api/algo/risk-dashboard` | Risk metrics |
| fetch_perf_analytics | algo_performance_daily | `/api/algo/performance` | In performance data |
| fetch_signal_eval | algo_signals_evaluated | `/api/algo/rejection-funnel` | Signal evaluation/rejection |
| fetch_sector_rotation | sector_rotation_signal | `/api/algo/sector-rotation` | Sector rotation signal |
| fetch_industry_ranking | industry_ranking | `/api/industries` | Industry rankings |
| fetch_loader_status | data_loader_status | `/api/algo/data-status` | Data loader status |
| fetch_exec_history | orchestrator_execution_log | `/api/algo/execution/recent` | Execution history |
| fetch_audit_log | algo_audit_log | `/api/algo/audit-log` | Audit log |
| fetch_circuit | algo_circuit_breakers | `/api/algo/circuit-breakers` | Circuit breaker status |

## Changes Required

1. **Remove all database imports**: 
   - Delete psycopg2 import
   - Delete boto3 import (not needed - API handles it)
   - Delete DashboardDataAPI import

2. **Remove all database connection code**:
   - `_load_db_credentials_from_secrets()`
   - `_init_dashboard_pool()`
   - `get_conn()` function
   - `return_conn()` function
   - `q()` helper function  
   - `q1()` helper function

3. **Update all fetch_* functions**:
   - Replace `q()` and `q1()` calls with `api_call()`
   - Map to correct API endpoints
   - Parse response data from `['data']` key
   - Remove any local fallbacks
   - Use safe_* conversion functions for type safety

4. **Simplify load_all() function**:
   - Remove database connection pool logic
   - Remove retry/backoff for DB errors (API already has it)
   - Just call fetchers directly with None instead of connection

5. **Update docstring**:
   - Change "AWS Secrets Manager" references to "AWS Lambda API"
   - Remove database connection requirements
   - Document that it requires DASHBOARD_API_URL environment variable

## Production Configuration

The dashboard requires:
```bash
export DASHBOARD_API_URL="https://<api-gateway-id>.execute-api.us-east-1.amazonaws.com/prod"
```

In development:
```bash
export DASHBOARD_API_URL="http://localhost:3001"  # or dev API endpoint
```

Default (if not set): `http://localhost:3001`

## Verification

After changes:
1. ✓ All fetch_* functions call api_call() only
2. ✓ No q() or q1() calls remain
3. ✓ No psycopg2, boto3, or database imports
4. ✓ load_all() doesn't create database connections
5. ✓ All API endpoints are correct per mapping above
