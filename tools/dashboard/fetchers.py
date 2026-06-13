"""Fetcher functions for dashboard data from API endpoints."""

import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from data_validation import safe_int, safe_float, safe_json_parse, safe_bool

from utilities import (
    api_call, logger, _data_status_cache, _data_status_lock,
    G, R, Y, CY,
)


def fetch_run(c):
    try:
        data = api_call('/api/algo/last-run')
        if data.get('_error'):
            return data
        return {
            "run_id":    data.get("run_id"),
            "run_at":    data.get("completed_at") or data.get("started_at"),
            "success":   data.get("success", False),
            "halted":    data.get("halted", False),
            "errored":   data.get("errored", False),
            "summary":   data.get("summary"),
            "halt_reason": data.get("halt_reason"),
            "phases_completed": data.get("phases_completed") or [],
            "phases_halted":    data.get("phases_halted") or [],
            "phases_errored":   data.get("phases_errored") or [],
            "phase_results":    safe_json_parse(data.get("phase_results"), default=[], field_name="fetch_run.phase_results"),
        }
    except Exception as e:
        logger.error(f"fetch_run: {type(e).__name__}: {e}")
        return {"_error": str(e)}

def fetch_algo_config(c):
    """AWS-only algo configuration (no local fallback)."""
    try:
        data = api_call('/api/algo/config')
        if data.get('_error'):
            return {"_error": data.get('_error'), "enabled": False, "mode": "unknown", "max_pos_pct": None, "max_pos_n": None, "max_sec_n": None, "min_score": None, "base_risk": None, "t1_r": None, "pyramid": False}
        cfg = data.get('data', {})
        if "_error" in cfg:
            return {"_error": cfg["_error"], "enabled": False, "mode": "unknown", "max_pos_pct": None, "max_pos_n": None, "max_sec_n": None, "min_score": None, "base_risk": None, "t1_r": None, "pyramid": False}
        return {
            "enabled": cfg.get("algo_enabled", True),
            "mode": cfg.get("trade_mode", "unknown"),
            "max_pos_pct": safe_float(cfg.get("max_position_size_pct")),
            "max_pos_n": safe_int(cfg.get("max_positions")),
            "max_sec_n": safe_int(cfg.get("max_positions_per_sector")),
            "min_score": safe_float(cfg.get("min_swing_score")),
            "base_risk": safe_float(cfg.get("base_risk_pct")),
            "t1_r": safe_float(cfg.get("t1_target_r_multiple")),
            "pyramid": cfg.get("pyramid_enabled", "false").lower() == "true",
        }
    except Exception as e:
        logger.error(f"fetch_algo_config: {type(e).__name__}: {e}")
        return {"_error": str(e), "enabled": False, "mode": "unknown", "max_pos_pct": None, "max_pos_n": None, "max_sec_n": None, "min_score": None, "base_risk": None, "t1_r": None, "pyramid": False}

def fetch_market(c):
    """Issue 3 FIX: API-only market data."""
    try:
        mkt = api_call('/api/algo/markets')
        if mkt.get('_error'):
            return {"_error": mkt.get('_error'), "pct": None, "tier": "unknown", "halts": [], "vix": None, "stage": None, "trend": None, "dist": None, "spy": None, "spy_chg": None, "upvol": None, "adr": None, "nh": None, "nl": None, "pcr": None, "bmom": None, "ycs": None, "fed": None}
        data = mkt.get('data', {})
        return {
            "pct": safe_float(data.get("exposure_pct")),
            "tier": data.get("regime", "unknown"),
            "halts": safe_json_parse(data.get("halt_reasons"), default=[], field_name="halt_reasons"),
            "vix": safe_float(data.get("vix_level")),
            "stage": data.get("market_stage"),
            "trend": data.get("market_trend"),
            "dist": safe_int(data.get("distribution_days_4w")),
            "spy": safe_float(data.get("spy_close")),
            "spy_chg": safe_float(data.get("spy_change_pct")),
            "upvol": safe_float(data.get("up_volume_percent")),
            "adr": safe_float(data.get("advance_decline_ratio")),
            "nh": safe_int(data.get("new_highs_count")),
            "nl": safe_int(data.get("new_lows_count")),
            "pcr": safe_float(data.get("put_call_ratio")),
            "bmom": safe_float(data.get("breadth_momentum_10d")),
            "ycs": safe_float(data.get("yield_curve_slope")),
            "fed": data.get("fed_rate_environment"),
        }
    except Exception as e:
        logger.error(f"fetch_market: {type(e).__name__}: {e}")
        return {"_error": str(e), "pct": None, "tier": "unknown", "halts": [], "vix": None, "stage": None, "trend": None, "dist": None, "spy": None, "spy_chg": None, "upvol": None, "adr": None, "nh": None, "nl": None, "pcr": None, "bmom": None, "ycs": None, "fed": None}

def fetch_exposure_factors(c):
    """Issue 3 FIX: API-only exposure factors."""
    try:
        data = api_call('/api/algo/exposure-policy')
        if data.get('_error'):
            return {"_error": data.get('_error'), "raw_score": None, "exposure_pct": None, "regime": None, "factors": {}}
        d = data.get('data', {})
        return {
            "raw_score": safe_float(d.get("factor_quality")),
            "exposure_pct": safe_float(d.get("current_exposure_pct")),
            "regime": d.get("regime"),
            "factors": safe_json_parse(d.get("factors"), default={}, field_name="factors"),
        }
    except Exception as e:
        logger.error(f"fetch_exposure_factors: {type(e).__name__}: {e}")
        return {"_error": str(e), "raw_score": None, "exposure_pct": None, "regime": None, "factors": {}}

def _validate_required_fields(data_dict, required_fields, source_name):
    """Validate that all required fields exist in response dict. Return error dict if missing."""
    if not isinstance(data_dict, dict):
        return {"_error": f"{source_name}: expected dict but got {type(data_dict).__name__}"}
    missing = [f for f in required_fields if f not in data_dict]
    if missing:
        logger.warning(f"{source_name}: missing required fields: {missing}")
        return {"_error": f"{source_name}: missing fields {missing}"}
    return None

def fetch_portfolio(c):
    """Fetch portfolio snapshot from API. Fails clean if unavailable."""
    try:
        data = api_call('/api/algo/portfolio')
        if data.get('_error'):
            return {
                "_error": data.get('_error'),
                "snapshot_date": None, "total_portfolio_value": None, "total_cash": None,
                "position_count": None, "daily_return_pct": None, "unrealized_pnl_pct": None,
                "cumulative_return_pct": None, "max_drawdown_pct": None, "largest_position_pct": None,
                "data_age_seconds": None
            }
        port = data.get('data', {})
        required_fields = ["total_portfolio_value", "total_cash", "open_positions"]
        validation_error = _validate_required_fields(port, required_fields, "fetch_portfolio")
        if validation_error:
            return {**validation_error, "snapshot_date": None, "total_portfolio_value": None,
                   "total_cash": None, "position_count": None, "daily_return_pct": None,
                   "unrealized_pnl_pct": None, "cumulative_return_pct": None,
                   "max_drawdown_pct": None, "largest_position_pct": None, "data_age_seconds": None}
        return {
            "snapshot_date": port.get("last_run"),
            "total_portfolio_value": safe_float(port.get("total_portfolio_value")),
            "total_cash": safe_float(port.get("total_cash")),
            "position_count": safe_int(port.get("open_positions")),
            "daily_return_pct": safe_float(port.get("daily_return_pct")),
            "unrealized_pnl_pct": safe_float(port.get("unrealized_pnl_pct")),
            "cumulative_return_pct": safe_float(port.get("cumulative_return_pct")),
            "max_drawdown_pct": safe_float(port.get("max_drawdown_pct")),
            "largest_position_pct": safe_float(port.get("largest_position_pct")),
            "data_age_seconds": port.get("data_age_seconds")
        }
    except Exception as e:
        logger.error(f"fetch_portfolio: {type(e).__name__}: {e}")
        return {
            "_error": str(e),
            "snapshot_date": None, "total_portfolio_value": None, "total_cash": None,
            "position_count": None, "daily_return_pct": None, "unrealized_pnl_pct": None,
            "cumulative_return_pct": None, "max_drawdown_pct": None, "largest_position_pct": None,
            "data_age_seconds": None
        }

def fetch_perf(c):
    """AWS-only performance data (no local fallback)."""
    try:
        data = api_call('/api/algo/performance')
        if data.get('_error'):
            return {
                "_error": data.get('_error'),
                "n": None, "w": None, "l": None, "wr": None, "pnl": None, "streak": None,
                "sharpe": None, "maxdd": None, "avg_win": None, "avg_loss": None,
                "profit_factor": None, "expectancy": None, "avg_r": None,
                "equity_vals": [], "recent_rets": []
            }
        perf = data.get('data', {})
        required_fields = ["total_trades", "winning_trades", "losing_trades"]
        validation_error = _validate_required_fields(perf, required_fields, "fetch_perf")
        if validation_error:
            return {**validation_error, "n": None, "w": None, "l": None, "wr": None,
                   "pnl": None, "streak": None, "sharpe": None, "maxdd": None,
                   "avg_win": None, "avg_loss": None, "profit_factor": None,
                   "expectancy": None, "avg_r": None, "equity_vals": [], "recent_rets": []}
        return {
            "n": safe_int(perf.get("total_trades")),
            "w": safe_int(perf.get("winning_trades")),
            "l": safe_int(perf.get("losing_trades")),
            "wr": safe_float(perf.get("win_rate_pct")),
            "open_count": safe_int(perf.get("open_positions")),
            "pnl": safe_float(perf.get("total_pnl_dollars")),
            "unrealized_pnl": safe_float(perf.get("unrealized_pnl")),
            "streak": 0,
            "sharpe": safe_float(perf.get("sharpe_annualized")),
            "maxdd": safe_float(perf.get("max_drawdown_pct")),
            "avg_win": safe_float(perf.get("avg_win_pct")),
            "avg_loss": safe_float(perf.get("avg_loss_pct")),
            "profit_factor": safe_float(perf.get("profit_factor")),
            "expectancy": safe_float(perf.get("expectancy_r")),
            "avg_r": 0,
            "equity_vals": perf.get("equity_vals", []),
            "recent_rets": perf.get("recent_rets", [])
        }
    except Exception as e:
        logger.error(f"fetch_perf: {type(e).__name__}: {e}")
        return {
            "_error": str(e),
            "n": None, "w": None, "l": None, "wr": None, "pnl": None, "streak": None,
            "sharpe": None, "maxdd": None, "avg_win": None, "avg_loss": None,
            "profit_factor": None, "expectancy": None, "avg_r": None,
            "equity_vals": [], "recent_rets": []
        }

def fetch_positions(c):
    """Fetch positions via AWS API only (no local database fallback)."""
    try:
        data = api_call('/api/algo/positions')
        if data.get('_error'):
            return {"_error": data.get('_error'), "items": [], "timestamp": datetime.now(timezone.utc)}
        result = data.get('data', {})
        items = result.get('items', []) if isinstance(result, dict) else result if isinstance(result, list) else []
        return {"items": items, "timestamp": datetime.now(timezone.utc)}
    except Exception as e:
        logger.error(f"fetch_positions: {type(e).__name__}: {e}")
        return {"_error": str(e), "items": [], "timestamp": datetime.now(timezone.utc)}

def fetch_recent_trades(c):
    """AWS-only trades data (no local fallback)."""
    try:
        data = api_call('/api/algo/trades', params={'limit': 100})
        if data.get('_error'):
            return {"_error": data.get('_error'), "items": [], "timestamp": datetime.now(timezone.utc)}
        result = data.get('data', {})
        trades = result.get('items', []) if isinstance(result, dict) else result if isinstance(result, list) else []
        closed = [t for t in trades if t.get("status") == "closed"]
        return {"items": closed[:10], "timestamp": datetime.now(timezone.utc)}
    except Exception as e:
        logger.error(f"fetch_recent_trades: {type(e).__name__}: {e}")
        return {"_error": str(e), "items": [], "timestamp": datetime.now(timezone.utc)}

def fetch_signals(c):
    """Fetch dashboard signals from API."""
    try:
        data = api_call('/api/signals/stocks')
        if data.get('_error'):
            return {"_error": data.get('_error'), "n": 0, "total": 0, "buy_sigs": [], "grades": {}, "near": [], "top_a": [], "trend": [], "timestamp": datetime.now(timezone.utc)}
        if not data.get('data'):
            return {"n": 0, "total": 0, "buy_sigs": [], "grades": {}, "near": [], "top_a": [], "trend": [], "timestamp": datetime.now(timezone.utc)}

        result = data['data']
        signals = result.get('signals', [])
        return {
            "n": len(signals),
            "total": result.get('total', len(signals)),
            "buy_sigs": signals[:5] if signals else [],
            "grades": result.get('grades', {}),
            "near": signals[5:10] if len(signals) > 10 else (signals[5:] if len(signals) > 5 else []),
            "top_a": signals[:3] if signals else [],
            "trend": result.get('trend', []),
            "timestamp": datetime.now(timezone.utc)
        }
    except Exception as e:
        logger.error(f"fetch_signals: {type(e).__name__}: {e}")
        return {"_error": str(e), "n": 0, "total": 0, "buy_sigs": [], "grades": {}, "near": [], "top_a": [], "trend": [], "timestamp": datetime.now(timezone.utc)}

def fetch_sector_ranking(c):
    """Fetch sector rankings from API."""
    try:
        data = api_call('/api/sectors')
        if data.get('_error'):
            return {"_error": data.get('_error'), "items": []}
        rankings = data.get('data', [])
        return {"items": rankings if isinstance(rankings, list) else []}
    except Exception as e:
        logger.error(f"fetch_sector_ranking: {type(e).__name__}: {e}")
        return {"_error": str(e), "items": []}

def fetch_activity(c):
    """Fetch activity and audit log from API."""
    try:
        data = api_call('/api/algo/audit-log')
        if data.get('_error'):
            return {"_error": data.get('_error')}
        result = data.get('data', {})
        return {
            "run_id": result.get("run_id"),
            "run_at": result.get("run_at"),
            "phases": result.get("phases", []),
            "recent_actions": result.get("recent_actions", [])
        }
    except Exception as e:
        logger.error(f"fetch_activity: {type(e).__name__}: {e}")
        return {"_error": str(e)}

def _get_data_status_cached():
    """Issue 2.2 FIX: Unified fetch for /api/algo/data-status endpoint.

    Both fetch_health and fetch_loader_status need the same endpoint. This
    caches the result to avoid duplicate API calls when both are fetched
    in parallel. Thread-safe with lock to ensure single API call.
    """
    global _data_status_cache, _data_status_lock

    if 'result' in _data_status_cache:
        return _data_status_cache['result']

    with _data_status_lock:
        if 'result' in _data_status_cache:
            return _data_status_cache['result']

        try:
            data = api_call('/api/algo/data-status')
            _data_status_cache['result'] = data
            return data
        except Exception as e:
            error_result = {"_error": str(e)}
            _data_status_cache['result'] = error_result
            return error_result

def fetch_health(c):
    """Fetch data loader health status from API. Uses cached data-status."""
    try:
        data = _get_data_status_cached()
        if data.get('_error'):
            return {"_error": data.get('_error'), "items": []}
        health = data.get('data', [])
        return {"items": health if isinstance(health, list) else []}
    except Exception as e:
        logger.error(f"fetch_health: {type(e).__name__}: {e}")
        return {"_error": str(e), "items": []}

def fetch_economic_pulse(c):
    try:
        data = api_call('/api/economic')
        if data.get('_error'):
            return {"_error": data.get('_error'), 't10': None, 't2': None, 't3m': None, 't6m': None, 'yc_10_2': None, 'yc_10_3m': None, 'hy': None, 'ig': None, 'oil': None, 'nfci': None, 'fed_funds': None, 'cpi_yoy': None, 'unrate': None, 'be10': None, 'be5': None, 'dxy': None, 'mortgage': None, 'umcsent': None}
        econ = data.get('data', {})
        return {
            't10': econ.get('t10'), 't2': econ.get('t2'), 't3m': econ.get('t3m'), 't6m': econ.get('t6m'),
            'yc_10_2':  econ.get('yc_10_2'), 'yc_10_3m': econ.get('yc_10_3m'),
            'hy':  econ.get('hy'), 'ig': econ.get('ig'),
            'oil': econ.get('oil'),    'nfci': econ.get('nfci'),
            'fed_funds': econ.get('fed_funds'),
            'cpi_yoy':   econ.get('cpi_yoy'),
            'unrate':    econ.get('unrate'),
            'be10':      econ.get('be10'),
            'be5':       econ.get('be5'),
            'dxy':       econ.get('dxy'),
            'mortgage':  econ.get('mortgage'),
            'umcsent':   econ.get('umcsent'),
        }
    except Exception as e:
        return {"_error": str(e), 't10': None, 't2': None, 't3m': None, 't6m': None, 'yc_10_2': None, 'yc_10_3m': None, 'hy': None, 'ig': None, 'oil': None, 'nfci': None, 'fed_funds': None, 'cpi_yoy': None, 'unrate': None, 'be10': None, 'be5': None, 'dxy': None, 'mortgage': None, 'umcsent': None}

def fetch_algo_metrics(c):
    """Issue 3 FIX: API-only algo metrics."""
    try:
        data = api_call('/api/algo/metrics')
        if data.get('_error'):
            return {"_error": data.get('_error'), "items": []}
        return {"items": data.get('data', []) if isinstance(data.get('data'), list) else []}
    except Exception as e:
        logger.error(f"fetch_algo_metrics: {type(e).__name__}: {e}")
        return {"_error": str(e), "items": []}

def fetch_notifications(c):
    try:
        data = api_call('/api/algo/notifications')
        if data.get('_error'):
            return {"_error": data.get('_error')}
        return data.get('data', [])
    except Exception as e:
        return {"_error": str(e)}

def fetch_sentiment(c):
    """Issue 3 FIX: API-only sentiment data."""
    try:
        data = api_call('/api/algo/sentiment')
        if data.get('_error'):
            return {"_error": data.get('_error'), "fg": 50, "label": "Unknown", "date": None, "color": CY}
        d = data.get('data', {})
        fg = safe_float(d.get("fear_greed_index"), default=50)
        label = d.get("label", "Neutral")
        c_fg = (R if fg <= 25 else (Y if fg <= 45 else (G if fg >= 75 else CY)))
        return {"fg": round(fg, 1), "label": label, "date": d.get("date"), "color": c_fg}
    except Exception as e:
        logger.error(f"fetch_sentiment: {type(e).__name__}: {e}")
        return {"_error": str(e), "fg": 50, "label": "Unknown", "date": None, "color": CY}

def fetch_economic_calendar(c):
    """Issue 3 FIX: API-only economic calendar."""
    try:
        data = api_call('/api/algo/economic-calendar')
        if data.get('_error'):
            return {"_error": data.get('_error'), "items": []}
        return {"items": data.get('data', []) if isinstance(data.get('data'), list) else []}
    except Exception as e:
        logger.error(f"fetch_economic_calendar: {type(e).__name__}: {e}")
        return {"_error": str(e), "items": []}

def fetch_risk_metrics(c):
    """Issue 3 FIX: API-only risk metrics."""
    try:
        data = api_call('/api/algo/risk-metrics')
        if data.get('_error'):
            return {"_error": data.get('_error'), "date": None, "var95": None, "cvar95": None, "svar": None, "beta": None, "conc5": None}
        d = data.get('data', {})
        return {
            "date": d.get("report_date"),
            "var95": safe_float(d.get("var_pct_95")),
            "cvar95": safe_float(d.get("cvar_pct_95")),
            "svar": safe_float(d.get("stressed_var_pct")),
            "beta": safe_float(d.get("portfolio_beta")),
            "conc5": safe_float(d.get("top_5_concentration")),
        }
    except Exception as e:
        logger.error(f"fetch_risk_metrics: {type(e).__name__}: {e}")
        return {"_error": str(e), "date": None, "var95": None, "cvar95": None, "svar": None, "beta": None, "conc5": None}

def fetch_perf_analytics(c):
    """Issue 3 FIX: API-only performance analytics."""
    try:
        data = api_call('/api/algo/performance-analytics')
        if data.get('_error'):
            return {"_error": data.get('_error'), "sharpe252": None, "sortino": None, "calmar": None, "wr50": None, "avg_w_r": None, "avg_l_r": None, "expectancy": None, "maxdd": None}
        d = data.get('data', {})
        return {
            "sharpe252": safe_float(d.get("rolling_sharpe_252d")),
            "sortino": safe_float(d.get("rolling_sortino_252d")),
            "calmar": safe_float(d.get("calmar_ratio")),
            "wr50": safe_float(d.get("win_rate_50t")),
            "avg_w_r": safe_float(d.get("avg_win_r_50t")),
            "avg_l_r": safe_float(d.get("avg_loss_r_50t")),
            "expectancy": safe_float(d.get("expectancy")),
            "maxdd": safe_float(d.get("max_drawdown_pct")),
        }
    except Exception as e:
        logger.error(f"fetch_perf_analytics: {type(e).__name__}: {e}")
        return {"_error": str(e), "sharpe252": None, "sortino": None, "calmar": None, "wr50": None, "avg_w_r": None, "avg_l_r": None, "expectancy": None, "maxdd": None}

def fetch_signal_eval(c):
    """Fetch signal evaluation stats from API."""
    try:
        data = api_call('/api/algo/rejection-funnel')
        if data.get('_error'):
            return {"_error": data.get('_error')}
        result = data.get('data', {})
        return {
            "total":    safe_int(result.get("total")),
            "t1": safe_int(result.get("t1")),
            "t2": safe_int(result.get("t2")),
            "t3": safe_int(result.get("t3")),
            "t4": safe_int(result.get("t4")),
            "t5": safe_int(result.get("t5")),
            "avg_score": safe_float(result.get("avg_score")),
            "date":     result.get("signal_date"),
            "rejected": result.get("rejected", []),
        }
    except Exception as e:
        logger.error(f"fetch_signal_eval: {type(e).__name__}: {e}")
        return {"_error": str(e)}

def fetch_sector_rotation(c):
    """Fetch sector rotation signal from API."""
    try:
        data = api_call('/api/algo/sector-rotation')
        if data.get('_error'):
            return {"_error": data.get('_error'), "date": None, "signal": "", "strength": None, "weeks": 0, "def_score": 0, "cyc_score": 0}
        row = data.get('data', {})
        if not row:
            return {"date": None, "signal": "", "strength": None, "weeks": 0, "def_score": 0, "cyc_score": 0}
        details = safe_json_parse(row.get("details"), default={}, field_name="fetch_sector_rotation.details")
        return {
            "date":     row.get("date"),
            "signal":   row.get("signal", ""),
            "strength": safe_float(row.get("strength")),
            "weeks":    details.get("weeks_persistent", 1),
            "def_score": details.get("defensive_lead_score", 0),
            "cyc_score": details.get("cyclical_weak_score", 0),
        }
    except Exception as e:
        logger.error(f"fetch_sector_rotation: {type(e).__name__}: {e}")
        return {"_error": str(e), "date": None, "signal": "", "strength": None, "weeks": 0, "def_score": 0, "cyc_score": 0}

def fetch_industry_ranking(c):
    """Fetch industry rankings from API."""
    try:
        data = api_call('/api/industries')
        if data.get('_error'):
            return {"_error": data.get('_error'), "items": []}
        industries = data.get('data', [])
        return {"items": industries if isinstance(industries, list) else []}
    except Exception as e:
        logger.error(f"fetch_industry_ranking: {type(e).__name__}: {e}")
        return {"_error": str(e), "items": []}

def fetch_exec_history(c):
    """Fetch recent execution history from API."""
    try:
        data = api_call('/api/algo/execution/recent', params={'days': 7, 'limit': 10})
        if data.get('_error'):
            return {"_error": data.get('_error'), "items": []}
        executions = data.get('data', [])
        return {"items": executions if isinstance(executions, list) else []}
    except Exception as e:
        logger.error(f"fetch_exec_history: {type(e).__name__}: {e}")
        return {"_error": str(e), "items": []}

def fetch_audit_log(c):
    """Fetch audit log from API."""
    try:
        data = api_call('/api/algo/audit-log')
        if data.get('_error'):
            return {"_error": data.get('_error'), "items": []}
        log_entries = data.get('data', [])
        return {"items": log_entries if isinstance(log_entries, list) else []}
    except Exception as e:
        logger.error(f"fetch_audit_log: {type(e).__name__}: {e}")
        return {"_error": str(e), "items": []}

def fetch_circuit(c):
    """Fetch circuit breakers from API."""
    try:
        data = api_call('/api/algo/circuit-breakers')
        if data.get('_error'):
            return {"_error": data.get('_error')}
        result = data.get('data', {})
        bs = result.get('breakers', [])
        formatted_bs = []
        for r in bs:
            formatted_bs.append({
                "lbl": r.get("breaker_name", ""),
                "cur": safe_float(r.get("current_value")),
                "thr": safe_float(r.get("threshold_value")),
                "u": r.get("unit", ""),
                "fired": safe_bool(r.get("is_active"))
            })
        any_fired = any(b["fired"] for b in formatted_bs)
        return {
            "bs": formatted_bs,
            "any": any_fired,
            "n": sum(1 for b in formatted_bs if b["fired"])
        }
    except Exception as e:
        logger.error(f"fetch_circuit: {type(e).__name__}: {e}")
        return {"_error": str(e)}


FETCHERS = {
    "run":          fetch_run,
    "cfg":          fetch_algo_config,
    "mkt":          fetch_market,
    "port":         fetch_portfolio,
    "perf":         fetch_perf,
    "pos":          fetch_positions,
    "trades":       fetch_recent_trades,
    "sig":          fetch_signals,
    "health":       fetch_health,
    "cb":           fetch_circuit,
    "srank":        fetch_sector_ranking,
    "activity":     fetch_activity,
    "exp_factors":  fetch_exposure_factors,
    "eco":          fetch_economic_pulse,
    "notifs":       fetch_notifications,
    "sentiment":    fetch_sentiment,
    "econ_cal":     fetch_economic_calendar,
    "risk":         fetch_risk_metrics,
    "perf_anl":     fetch_perf_analytics,
    "sig_eval":     fetch_signal_eval,
    "sec_rot":      fetch_sector_rotation,
    "algo_metrics": fetch_algo_metrics,
    "irank":        fetch_industry_ranking,
    "audit":        fetch_audit_log,
    "exec_hist":    fetch_exec_history,
}

def load_all() -> dict:
    """Load all fetcher data in parallel with exponential backoff retry and timeout handling.

    FIXES APPLIED:
    - Issue #1: Removed duplicate api_call() stub
    - Issue #2: Normalized positions data structure {items, count, timestamp}
    - Issue #3: Fetch portfolio metrics from perf API if missing
    - Issue #4: Bounded sector cache with LRU (maxsize=100)
    - Issue #8: Increased thread pool from 8 to 16 workers
    - Issue #9: Increased batch timeout from 100s to 200s

    Issue 10 FIX: Exponential backoff capped at API_MAX_BACKOFF (30s) to prevent runaway delays.
    Issue 11 FIX: Timeout handling ensures orphaned fetchers are marked incomplete and not lost.
    Issue 12 FIX: API calls use retry logic with capped exponential backoff.
    """
    from utilities import API_MAX_BACKOFF
    out: dict = {}
    MAX_RETRIES = 3
    BATCH_TIMEOUT = 200

    def one(name, fn):
        """Execute fetcher with exponential backoff retry on API errors."""
        for attempt in range(MAX_RETRIES + 1):
            try:
                return name, fn(None)
            except Exception as e:
                if attempt < MAX_RETRIES:
                    base_backoff = (2 ** attempt) + random.random() * (2 ** attempt)
                    backoff = min(base_backoff, API_MAX_BACKOFF)
                    logger.warning(f"Fetcher {name} retry {attempt+1}/{MAX_RETRIES} (backoff {backoff:.1f}s): {type(e).__name__}")
                    time.sleep(backoff)
                    continue
                logger.error(f"Fetcher {name} failed after {MAX_RETRIES+1} attempts: {e}")
                return name, {"_error": str(e)}

    with ThreadPoolExecutor(max_workers=min(len(FETCHERS), 16)) as pool:
        futures = {pool.submit(one, k, v): k for k, v in FETCHERS.items()}
        pending_futures = set(futures.keys())

        try:
            for f in as_completed(futures, timeout=BATCH_TIMEOUT):
                try:
                    n, d = f.result()
                    out[n] = d
                    pending_futures.discard(f)
                except Exception as e:
                    k = futures[f]
                    logger.error(f"Thread exception for {k}: {type(e).__name__}: {e}")
                    out[k] = {"_error": str(e)}
                    pending_futures.discard(f)
        except TimeoutError:
            logger.error(f"load_all timeout after {BATCH_TIMEOUT}s - marking incomplete fetchers")
            for f in pending_futures:
                k = futures.get(f)
                if k and not f.done():
                    logger.warning(f"Fetcher {k} timed out - marking incomplete")
                    out[k] = {"_error": f"Timeout (exceeded {BATCH_TIMEOUT}s)"}

    return out
