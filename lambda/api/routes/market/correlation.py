"""Handler for /api/market/correlation.

Split out of lambda/api/routes/market.py 2026-09-05 (file-size-ratchet decomposition).
"""

from __future__ import annotations

import logging
from typing import Any

from psycopg2.extensions import cursor
from routes.utils import check_data_freshness, db_route_handler, error_response, json_response, raise_api_error

logger = logging.getLogger(__name__)


@db_route_handler("get correlation matrix")
def _get_correlation_matrix(cur: cursor) -> Any:  # noqa: C901
    """Compute and return correlation matrix between key market indices.

    Returns correlation matrix with statistics and analysis when sufficient data available.
    When data is insufficient (no price history or < 2 valid symbols), returns response
    with data_unavailable marker indicating reason for unavailable data.
    """
    # Session 196: Removed IVV (redundant S&P 500 tracker with perfect correlation to SPY)
    symbols = ["^GSPC", "^IXIC", "SPY", "QQQ", "TLT", "GLD"]

    cur.execute("SAVEPOINT correlation_matrix")
    cur.execute("SET LOCAL statement_timeout = '12s'")  # Query on 252 days of data
    cur.execute(
        """
        SELECT symbol, date, close
        FROM price_daily
        WHERE symbol = ANY(%s)
              AND date >= CURRENT_DATE - INTERVAL '252 days'
        ORDER BY symbol, date
    """,
        (symbols,),
    )
    rows = cur.fetchall()
    cur.execute("RELEASE SAVEPOINT correlation_matrix")

    if not rows:
        logger.error("[CORRELATION_MATRIX] No price history available for correlation calculation")
        return error_response(
            503,
            "insufficient_price_data",
            "Correlation matrix requires price history for 2+ symbols. Insufficient data available.",
        )

    prices_by_symbol: dict[str, list[Any]] = {}
    price_data_errors: list[dict[str, Any]] = []
    for row in rows:
        sym = row["symbol"]
        if sym not in prices_by_symbol:
            prices_by_symbol[sym] = []
        if row["close"] is None or row["close"] <= 0:
            if "date" not in row or row["date"] is None:
                raise ValueError(
                    f"[MARKET_API_DATA_INCOMPLETE] Market data for {sym} missing required 'date' field. "
                    f"Cannot process price data without date. Row keys: {list(row.keys())}. "
                    f"Check upstream price data source and loader."
                )
            # FAIL-FAST: Invalid prices break correlation calculations; cannot silently skip
            # If symbol has invalid price data in lookback period, the correlation is unreliable
            price_data_errors.append({"symbol": sym, "date": row.get("date"), "close": row["close"]})
            continue
        prices_by_symbol[sym].append((row["date"], float(row["close"])))

    # CRITICAL: If ANY symbol has invalid price data, fail the entire calculation
    # Silently skipping breaks time series alignment and produces meaningless correlations
    if price_data_errors:
        error_detail = "; ".join(f"{e['symbol']} {e['date']}: {e['close']}" for e in price_data_errors[:5])
        if len(price_data_errors) > 5:
            error_detail += f"; ... and {len(price_data_errors) - 5} more"
        raise ValueError(
            f"[MARKET_API DATA QUALITY] Cannot compute correlation: {len(price_data_errors)} "
            f"invalid price rows detected. Invalid prices break time series alignment. "
            f"Examples: {error_detail}. "
            f"Check: (1) price_daily loader completion, (2) for data gaps or incomplete loads"
        )

    for sym in prices_by_symbol:
        prices_by_symbol[sym] = [(d, p) for d, p in sorted(prices_by_symbol[sym])]

    returns_by_symbol = {}
    for sym, prices in prices_by_symbol.items():
        if len(prices) < 2:
            continue
        returns = []
        for i in range(1, len(prices)):
            prev_p = prices[i - 1][1]
            curr_p = prices[i][1]
            if prev_p > 0:
                ret = (curr_p - prev_p) / prev_p
                returns.append(ret)
        returns_by_symbol[sym] = returns

    valid_symbols = [s for s in symbols if s in returns_by_symbol and len(returns_by_symbol[s]) >= 10]
    if len(valid_symbols) < 2:
        return json_response(
            200,
            {
                "correlations": [],
                "statistics": {
                    "avg_correlation": None,
                    "max_correlation": {"value": None, "pair": []},
                    "min_correlation": {"value": None, "pair": []},
                },
                "analysis": {
                    "market_regime": "insufficient_data",
                    "diversification_score": None,
                    "risk_assessment": {
                        "concentration_risk": "unknown",
                        "diversification_benefit": "unknown",
                        "portfolio_stability": "unknown",
                    },
                },
                "data_unavailable": True,
                "reason": "insufficient_valid_symbols",
            },
        )

    def pearson_corr(x_ret: list[float], y_ret: list[float]) -> dict[str, Any] | float:
        """Compute Pearson correlation coefficient.

        Returns float correlation value on success, or dict with data_unavailable marker
        when data is insufficient for calculation.
        """
        if len(x_ret) < 2 or len(y_ret) < 2:
            return {"data_unavailable": True, "reason": "insufficient_returns_data"}
        min_len = min(len(x_ret), len(y_ret))
        if min_len < 2:
            return {"data_unavailable": True, "reason": "insufficient_returns_data"}
        x = x_ret[-min_len:]
        y = y_ret[-min_len:]
        mx = sum(x) / len(x)
        my = sum(y) / len(y)
        num: float = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y, strict=False))
        dx: float = sum((xi - mx) ** 2 for xi in x)
        dy: float = sum((yi - my) ** 2 for yi in y)
        denom = (dx * dy) ** 0.5
        if denom == 0:
            return {"data_unavailable": True, "reason": "zero_deviation"}
        return float(num / denom)

    correlations_data = []
    all_corrs = []
    unavailable_pairs = []

    for sym1 in valid_symbols:
        row_corrs: list[float | None] = []
        for sym2 in valid_symbols:
            if sym1 == sym2:
                corr_val: dict[str, Any] | float | None = 1.0
            else:
                corr_val = pearson_corr(returns_by_symbol[sym1], returns_by_symbol[sym2])
            # Handle case where pearson_corr returns data_unavailable marker
            if isinstance(corr_val, dict):
                row_corrs.append(None)
                if sym1 != sym2:
                    if "reason" not in corr_val or corr_val["reason"] is None:
                        logger.error(
                            f"[MARKET RISK] Correlation data for {sym1}/{sym2} marked unavailable but missing reason field. "
                            f"Dict keys: {list(corr_val.keys())}. "
                            f"Cannot determine why correlation failed. Check pearson_corr() implementation."
                        )
                        raise ValueError(
                            f"[MARKET RISK] Correlation unavailability marker missing 'reason' field for {sym1}/{sym2}. "
                            "Cannot safely evaluate data quality."
                        )
                    unavailable_pairs.append({"pair": [sym1, sym2], "reason": corr_val["reason"]})
            else:
                row_corrs.append(corr_val)
                if sym1 != sym2 and corr_val is not None:
                    all_corrs.append(corr_val)
        correlations_data.append({"symbol": sym1, "correlations": row_corrs})

    max_corr = max(all_corrs) if all_corrs else None
    min_corr = min(all_corrs) if all_corrs else None
    avg_corr = sum(all_corrs) / len(all_corrs) if all_corrs else None

    max_pair = None
    min_pair = None

    if max_corr is not None:
        for i, sym1 in enumerate(valid_symbols):
            for j, sym2 in enumerate(valid_symbols):
                if i < j and correlations_data[i]["correlations"][j] == max_corr:
                    max_pair = [sym1, sym2]
                    break

    if min_corr is not None:
        for i, sym1 in enumerate(valid_symbols):
            for j, sym2 in enumerate(valid_symbols):
                if i < j and correlations_data[i]["correlations"][j] == min_corr:
                    min_pair = [sym1, sym2]
                    break

    # Validate correlation pair discovery
    if max_corr is not None and max_pair is None:
        logger.error(
            f"[MARKET_CORRELATION] Max correlation {max_corr} identified but pair lookup failed. "
            f"Data integrity error in correlation matrix computation."
        )
        raise_api_error(
            500, "correlation_computation_error", "Max correlation pair computation failed-cannot verify data integrity"
        )
    if min_corr is not None and min_pair is None:
        logger.error(
            f"[MARKET_CORRELATION] Min correlation {min_corr} identified but pair lookup failed. "
            f"Data integrity error in correlation matrix computation."
        )
        raise_api_error(
            500, "correlation_computation_error", "Min correlation pair computation failed-cannot verify data integrity"
        )

    avg_corr_val = round(avg_corr, 2) if avg_corr is not None else None

    if avg_corr_val is not None and avg_corr_val > 0.5:
        market_regime = "high_correlation"
    elif avg_corr_val is not None and avg_corr_val > 0.2:
        market_regime = "moderate_correlation"
    else:
        market_regime = "low_correlation"

    diversification_score = round(max(0, 1.0 - (avg_corr_val)) * 100, 1) if avg_corr_val is not None else None

    if avg_corr_val is not None and avg_corr_val > 0.6:
        concentration_risk = "high"
        diversification_benefit = "low"
        portfolio_stability = "volatile"
    elif avg_corr_val is not None and avg_corr_val > 0.3:
        concentration_risk = "moderate"
        diversification_benefit = "moderate"
        portfolio_stability = "moderate"
    else:
        concentration_risk = "low"
        diversification_benefit = "high"
        portfolio_stability = "stable"

    freshness = check_data_freshness(cur, "price_daily", "date", warning_days=1)
    response_data: dict[str, Any] = {
        "correlations": correlations_data,
        "statistics": {
            "avg_correlation": avg_corr_val,
            "max_correlation": {
                "value": round(max_corr, 2) if max_corr else None,
                "pair": max_pair,
            },
            "min_correlation": {
                "value": round(min_corr, 2) if min_corr else None,
                "pair": min_pair,
            },
        },
        "analysis": {
            "market_regime": market_regime,
            "diversification_score": diversification_score,
            "risk_assessment": {
                "concentration_risk": concentration_risk,
                "diversification_benefit": diversification_benefit,
                "portfolio_stability": portfolio_stability,
            },
        },
    }

    # Flag if any correlation pairs have unavailable data
    if unavailable_pairs:
        response_data["correlation_pairs_incomplete"] = True
        response_data["unavailable_pairs_count"] = len(unavailable_pairs)
        response_data["unavailable_pairs_samples"] = unavailable_pairs[:10]
        logger.warning(
            "[MARKET] Correlation pairs incomplete: %d pairs have insufficient data",
            len(unavailable_pairs),
        )

    return json_response(
        200,
        response_data,
        data_freshness=freshness,
    )
