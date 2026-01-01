#!/usr/bin/env python3
"""
Stock Scoring System - Sector-Relative Scoring with Statistical Normalization
Calculates factor scores (Quality, Value, Growth, Momentum) using sector-relative z-scores
converted to 0-100 scale for frontend compatibility.

Key improvements:
1. Sector-relative scoring (compares stocks within same sector, not globally)
2. Winsorization to handle outliers (caps at 1st/99th percentile)
3. Proper metric handling (excludes distressed companies with negative P/B, P/E)
4. Statistical z-score methodology converted to intuitive 0-100 scale
5. Frontend-compatible output (50 = sector average, higher is better)

Scoring methodology:
- Calculate z-scores within each sector (sector-relative comparison)
- Convert to 0-100 scale: score = 50 + (z_score * 15)
- Mean = 50, ±1σ ≈ 35-65, ±2σ ≈ 20-80, ±3σ ≈ 5-95

Author: Stock Analysis System
Date: 2025-12-28
"""

import json
import logging
import os
import sys
from datetime import date
from typing import Dict, List, Optional, Tuple

import boto3
import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from scipy.stats import zscore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

# Metric definitions
QUALITY_METRICS = [
    'return_on_equity_pct',
    'return_on_assets_pct',
    'return_on_invested_capital_pct',
    'gross_margin_pct',
    'operating_margin_pct',
    'profit_margin_pct',
    'current_ratio',
    'quick_ratio',
    'operating_cf_to_net_income',
    'fcf_to_net_income',
]

VALUE_METRICS = [
    'trailing_pe',
    'forward_pe',
    'price_to_book',
    'price_to_sales_ttm',
    'peg_ratio',
    'ev_to_ebitda',
    'ev_to_revenue',
]

# Metrics where LOWER is BETTER (will be inverted)
INVERSE_METRICS = [
    'trailing_pe',
    'forward_pe',
    'price_to_book',
    'price_to_sales_ttm',
    'peg_ratio',
    'ev_to_ebitda',
    'ev_to_revenue',
    'debt_to_equity',
]

GROWTH_METRICS = [
    'revenue_growth_3y_cagr',
    'eps_growth_3y_cagr',
    'operating_income_growth_yoy',
    'net_income_growth_yoy',
    'fcf_growth_yoy',
    'sustainable_growth_rate',
]

MOMENTUM_METRICS = [
    'momentum_3m',
    'momentum_6m',
    'momentum_12m',
    'price_vs_sma_50',
    'price_vs_sma_200',
]

STABILITY_METRICS = [
    'volatility_12m',
    'downside_volatility',
    'max_drawdown_52w',
    'beta',
]

# Metrics where LOWER is BETTER for stability
INVERSE_STABILITY = [
    'volatility_12m',
    'downside_volatility',
    'max_drawdown_52w',
]


def get_db_config():
    """Get database configuration - works in AWS and locally"""
    db_secret_arn = os.environ.get("DB_SECRET_ARN")

    if db_secret_arn:
        secret_str = boto3.client("secretsmanager").get_secret_value(
            SecretId=db_secret_arn
        )["SecretString"]
        sec = json.loads(secret_str)
        return {
            "host": sec["host"],
            "port": sec["port"],
            "user": sec["username"],
            "password": sec["password"],
            "database": sec["dbname"],
        }

    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": os.environ.get("DB_PORT", 5432),
        "user": os.environ.get("DB_USER", "stocks"),
        "password": os.environ.get("DB_PASSWORD", "bed0elAn"),
        "database": os.environ.get("DB_NAME", "stocks"),
    }


def winsorize(values: List[float], lower_percentile: float = 1.0, upper_percentile: float = 99.0) -> List[float]:
    """
    Winsorize data by capping outliers at specified percentiles.

    Args:
        values: List of numeric values
        lower_percentile: Lower percentile to cap (default 1st percentile)
        upper_percentile: Upper percentile to cap (default 99th percentile)

    Returns:
        List of winsorized values
    """
    if not values or len(values) < 3:
        return values

    # Remove None values
    clean_values = [v for v in values if v is not None]
    if len(clean_values) < 3:
        return values

    # Calculate percentile bounds
    lower_bound = np.percentile(clean_values, lower_percentile)
    upper_bound = np.percentile(clean_values, upper_percentile)

    # Cap values at bounds
    winsorized = []
    for v in values:
        if v is None:
            winsorized.append(None)
        elif v < lower_bound:
            winsorized.append(lower_bound)
        elif v > upper_bound:
            winsorized.append(upper_bound)
        else:
            winsorized.append(v)

    return winsorized


def calculate_sector_zscore(value: float, sector_values: List[float], invert: bool = False) -> Optional[float]:
    """
    Calculate z-score for a value within its sector, converted to 0-100 scale.

    Args:
        value: The value to score
        sector_values: All values in the same sector
        invert: If True, negate values before z-scoring (for "lower is better" metrics)

    Returns:
        Score on 0-100 scale (50 = average, higher is better) or None if insufficient data
    """
    if value is None:
        return None

    # CRITICAL: Exclude negative values for inverted metrics (PE, PB, etc.)
    # Negative P/B or P/E indicates distressed companies - exclude from scoring
    if invert and value < 0:
        return None  # Distressed company - exclude from value scoring

    # Remove None values and negatives if inverting
    if invert:
        clean_values = [v for v in sector_values if v is not None and v > 0]
    else:
        clean_values = [v for v in sector_values if v is not None]

    # Need at least 3 stocks for meaningful z-score
    if len(clean_values) < 3:
        return None

    # Winsorize to handle outliers
    winsorized_values = winsorize(clean_values)

    # Invert if needed (for metrics where lower is better)
    if invert:
        winsorized_values = [-v for v in winsorized_values]
        value_to_score = -value
    else:
        value_to_score = value

    # Calculate z-scores using scipy
    try:
        z_scores = zscore(winsorized_values)

        # Find the z-score for our value
        # Find closest match in winsorized values
        if invert:
            value_idx = None
            for i, v in enumerate(clean_values):
                if abs(-v - value_to_score) < 0.0001:  # Float comparison tolerance
                    value_idx = i
                    break
        else:
            value_idx = None
            for i, v in enumerate(clean_values):
                if abs(v - value_to_score) < 0.0001:
                    value_idx = i
                    break

        # If we can't find exact match, calculate z-score manually
        if value_idx is None:
            mean = np.mean(winsorized_values)
            std = np.std(winsorized_values)
            if std == 0:
                return None
            z_score = (value_to_score - mean) / std
        else:
            z_score = float(z_scores[value_idx])

        # Convert z-score to 0-100 scale for frontend compatibility
        # Mean (z=0) = 50, ±3 std devs = 5-95 range
        score_0_100 = 50 + (z_score * 15)

        # Clamp to 0-100 range
        score_0_100 = max(0, min(100, score_0_100))

        return float(round(score_0_100, 2))

    except Exception as e:
        logging.debug(f"Error calculating z-score: {e}")
        return None


def get_all_sectors(cursor) -> List[str]:
    """Get list of all sectors"""
    cursor.execute("SELECT DISTINCT sector FROM company_profile WHERE sector IS NOT NULL ORDER BY sector")
    return [row[0] for row in cursor.fetchall()]


def fetch_sector_stocks(cursor, sector: str, latest_date: date) -> List[Dict]:
    """
    Fetch all stocks in a sector with their metrics.

    Returns list of dictionaries with stock data.
    """
    query = """
    WITH latest_metrics AS (
        -- Quality metrics
        SELECT
            qm.symbol,
            qm.return_on_equity_pct,
            qm.return_on_assets_pct,
            qm.return_on_invested_capital_pct,
            qm.gross_margin_pct,
            qm.operating_margin_pct,
            qm.profit_margin_pct,
            qm.current_ratio,
            qm.quick_ratio,
            qm.operating_cf_to_net_income,
            qm.fcf_to_net_income,
            qm.debt_to_equity
        FROM quality_metrics qm
        WHERE qm.date = (SELECT MAX(date) FROM quality_metrics WHERE symbol = qm.symbol)
    ),
    latest_value AS (
        -- Value metrics
        SELECT
            vm.symbol,
            vm.trailing_pe,
            vm.forward_pe,
            vm.price_to_book,
            vm.price_to_sales_ttm,
            vm.peg_ratio,
            vm.ev_to_ebitda,
            vm.ev_to_revenue,
            vm.dividend_yield
        FROM value_metrics vm
        WHERE vm.date = (SELECT MAX(date) FROM value_metrics WHERE symbol = vm.symbol)
    ),
    latest_growth AS (
        -- Growth metrics
        SELECT
            gm.symbol,
            gm.revenue_growth_3y_cagr,
            gm.eps_growth_3y_cagr,
            gm.operating_income_growth_yoy,
            gm.net_income_growth_yoy,
            gm.fcf_growth_yoy,
            gm.sustainable_growth_rate
        FROM growth_metrics gm
        WHERE gm.date = (SELECT MAX(date) FROM growth_metrics WHERE symbol = gm.symbol)
    ),
    latest_momentum AS (
        -- Momentum metrics
        SELECT
            mm.symbol,
            mm.momentum_3m,
            mm.momentum_6m,
            mm.momentum_12m,
            mm.price_vs_sma_50,
            mm.price_vs_sma_200
        FROM momentum_metrics mm
        WHERE mm.date = (SELECT MAX(date) FROM momentum_metrics WHERE symbol = mm.symbol)
    ),
    latest_stability AS (
        -- Stability metrics
        SELECT
            sm.symbol,
            sm.volatility_12m,
            sm.downside_volatility,
            sm.max_drawdown_52w,
            sm.beta
        FROM stability_metrics sm
        WHERE sm.date = (SELECT MAX(date) FROM stability_metrics WHERE symbol = sm.symbol)
    )
    SELECT
        cp.ticker as symbol,
        COALESCE(cp.display_name, cp.long_name, cp.short_name) as company_name,
        cp.sector,
        lq.*,
        lv.*,
        lg.*,
        lm.*,
        ls.*
    FROM company_profile cp
    LEFT JOIN latest_metrics lq ON cp.ticker = lq.symbol
    LEFT JOIN latest_value lv ON cp.ticker = lv.symbol
    LEFT JOIN latest_growth lg ON cp.ticker = lg.symbol
    LEFT JOIN latest_momentum lm ON cp.ticker = lm.symbol
    LEFT JOIN latest_stability ls ON cp.ticker = ls.symbol
    WHERE cp.sector = %s
    """

    cursor.execute(query, (sector,))
    columns = [desc[0] for desc in cursor.description]
    stocks = []

    for row in cursor.fetchall():
        stock_dict = dict(zip(columns, row))
        stocks.append(stock_dict)

    return stocks


def calculate_factor_scores(stocks: List[Dict]) -> List[Dict]:
    """
    Calculate factor scores for all stocks in a sector using z-scores.

    Args:
        stocks: List of stock dictionaries with metrics

    Returns:
        List of stocks with added z-score fields and factor scores
    """
    # Extract metric values for each factor
    quality_values = {metric: [] for metric in QUALITY_METRICS}
    value_values = {metric: [] for metric in VALUE_METRICS}
    growth_values = {metric: [] for metric in GROWTH_METRICS}
    momentum_values = {metric: [] for metric in MOMENTUM_METRICS}
    stability_values = {metric: [] for metric in STABILITY_METRICS}

    # Collect all values
    for stock in stocks:
        for metric in QUALITY_METRICS:
            quality_values[metric].append(stock.get(metric))
        for metric in VALUE_METRICS:
            value_values[metric].append(stock.get(metric))
        for metric in GROWTH_METRICS:
            growth_values[metric].append(stock.get(metric))
        for metric in MOMENTUM_METRICS:
            momentum_values[metric].append(stock.get(metric))
        for metric in STABILITY_METRICS:
            stability_values[metric].append(stock.get(metric))

    # Calculate z-scores for each stock
    for stock in stocks:
        quality_zscores = []
        value_zscores = []
        growth_zscores = []
        momentum_zscores = []
        stability_zscores = []

        # Quality metrics
        for metric in QUALITY_METRICS:
            if stock.get(metric) is not None:
                invert = metric in INVERSE_METRICS
                z = calculate_sector_zscore(
                    stock[metric],
                    quality_values[metric],
                    invert=invert
                )
                if z is not None:
                    stock[f"{metric}_zscore"] = z
                    quality_zscores.append(z)

        # Value metrics
        for metric in VALUE_METRICS:
            if stock.get(metric) is not None:
                invert = metric in INVERSE_METRICS
                z = calculate_sector_zscore(
                    stock[metric],
                    value_values[metric],
                    invert=invert
                )
                if z is not None:
                    stock[f"{metric}_zscore"] = z
                    value_zscores.append(z)

        # Growth metrics
        for metric in GROWTH_METRICS:
            if stock.get(metric) is not None:
                z = calculate_sector_zscore(
                    stock[metric],
                    growth_values[metric],
                    invert=False
                )
                if z is not None:
                    stock[f"{metric}_zscore"] = z
                    growth_zscores.append(z)

        # Momentum metrics
        for metric in MOMENTUM_METRICS:
            if stock.get(metric) is not None:
                z = calculate_sector_zscore(
                    stock[metric],
                    momentum_values[metric],
                    invert=False
                )
                if z is not None:
                    stock[f"{metric}_zscore"] = z
                    momentum_zscores.append(z)

        # Stability metrics (inverted - lower volatility is better)
        for metric in STABILITY_METRICS:
            if stock.get(metric) is not None:
                invert = metric in INVERSE_STABILITY
                z = calculate_sector_zscore(
                    stock[metric],
                    stability_values[metric],
                    invert=invert
                )
                if z is not None:
                    stock[f"{metric}_zscore"] = z
                    stability_zscores.append(z)

        # Calculate factor scores as mean of z-scores
        stock['quality_score'] = float(np.mean(quality_zscores)) if quality_zscores else None
        stock['value_score'] = float(np.mean(value_zscores)) if value_zscores else None
        stock['growth_score'] = float(np.mean(growth_zscores)) if growth_zscores else None
        stock['momentum_score'] = float(np.mean(momentum_zscores)) if momentum_zscores else None
        stock['stability_score'] = float(np.mean(stability_zscores)) if stability_zscores else None

        # Calculate composite score (weighted average)
        # Weights: Quality 25%, Value 20%, Growth 20%, Momentum 20%, Stability 15%
        factor_scores = []
        weights = []

        if stock['quality_score'] is not None:
            factor_scores.append(stock['quality_score'])
            weights.append(0.25)
        if stock['value_score'] is not None:
            factor_scores.append(stock['value_score'])
            weights.append(0.20)
        if stock['growth_score'] is not None:
            factor_scores.append(stock['growth_score'])
            weights.append(0.20)
        if stock['momentum_score'] is not None:
            factor_scores.append(stock['momentum_score'])
            weights.append(0.20)
        if stock['stability_score'] is not None:
            factor_scores.append(stock['stability_score'])
            weights.append(0.15)

        if factor_scores:
            total_weight = sum(weights)
            normalized_weights = [w / total_weight for w in weights]
            stock['composite_score'] = float(np.average(factor_scores, weights=normalized_weights))
        else:
            stock['composite_score'] = None

    return stocks


def save_stock_scores(conn, cursor, stocks: List[Dict]):
    """Save stock scores to database"""

    # Clear existing scores
    cursor.execute("TRUNCATE TABLE stock_scores")

    # Prepare rows for insertion
    rows = []
    for stock in stocks:
        if stock['composite_score'] is None or stock.get('symbol') is None:
            continue  # Skip stocks with no composite score or missing symbol

        rows.append((
            stock['symbol'],
            stock.get('company_name'),
            stock.get('composite_score'),
            stock.get('quality_score'),
            stock.get('value_score'),
            stock.get('growth_score'),
            stock.get('momentum_score'),
            stock.get('stability_score'),
            # Store some key raw metrics for reference
            stock.get('trailing_pe'),
            stock.get('price_to_book'),
            stock.get('price_to_sales_ttm'),
            stock.get('return_on_equity_pct'),
            stock.get('return_on_assets_pct'),
            stock.get('revenue_growth_3y_cagr'),
            stock.get('eps_growth_3y_cagr'),
            stock.get('momentum_3m'),
            stock.get('momentum_6m'),
            stock.get('momentum_12m'),
            stock.get('volatility_12m'),
            stock.get('beta'),
        ))

    if not rows:
        logging.warning("No stocks to save - all have NULL composite scores")
        return

    # Insert scores
    insert_sql = """
        INSERT INTO stock_scores (
            symbol, company_name, composite_score,
            quality_score, value_score, growth_score, momentum_score, stability_score,
            pe_ratio, pb_ratio, ps_ratio,
            roe, roa,
            revenue_growth, earnings_growth,
            momentum_3m, momentum_6m, momentum_12m,
            volatility, beta
        ) VALUES %s
    """

    execute_values(cursor, insert_sql, rows)
    conn.commit()

    logging.info(f"Saved {len(rows)} stock scores to database")


def main():
    """Main scoring workflow"""
    logging.info("Starting sector-based stock scoring...")

    try:
        db_config = get_db_config()
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()

        # Get all sectors
        sectors = get_all_sectors(cursor)
        logging.info(f"Found {len(sectors)} sectors to process")

        all_stocks = []

        # Process each sector
        for sector in sectors:
            logging.info(f"\n{'='*60}")
            logging.info(f"Processing sector: {sector}")
            logging.info(f"{'='*60}")

            # Fetch stocks in sector
            stocks = fetch_sector_stocks(cursor, sector, date.today())
            logging.info(f"Found {len(stocks)} stocks in {sector}")

            if len(stocks) < 3:
                logging.warning(f"Sector {sector} has < 3 stocks, skipping...")
                continue

            # Calculate scores
            stocks_with_scores = calculate_factor_scores(stocks)

            # Print top stocks by each factor
            for factor in ['composite', 'quality', 'value', 'growth', 'momentum', 'stability']:
                sorted_stocks = sorted(
                    [s for s in stocks_with_scores if s.get(f'{factor}_score') is not None],
                    key=lambda x: x[f'{factor}_score'],
                    reverse=True
                )

                if sorted_stocks:
                    logging.info(f"\nTop 5 {factor.title()} Stocks in {sector}:")
                    for stock in sorted_stocks[:5]:
                        symbol = stock.get('symbol') or 'N/A'
                        if symbol is None:
                            symbol = 'N/A'
                        score_val = stock.get(f'{factor}_score')
                        score_str = f"{score_val:6.2f}" if score_val is not None else "  N/A "
                        logging.info(
                            f"  {str(symbol):6s} - {factor.title()} Score: {score_str}"
                        )

            all_stocks.extend(stocks_with_scores)

        # Save all scores to database
        logging.info(f"\n{'='*60}")
        logging.info("Saving scores to database...")
        save_stock_scores(conn, cursor, all_stocks)

        # Print overall summary
        logging.info(f"\n{'='*60}")
        logging.info("Overall Top 20 Stocks by Composite Score:")
        logging.info(f"{'='*60}")

        top_stocks = sorted(
            [s for s in all_stocks if s.get('composite_score') is not None],
            key=lambda x: x['composite_score'],
            reverse=True
        )[:20]

        for i, stock in enumerate(top_stocks, 1):
            symbol = stock.get('symbol', 'N/A')
            sector = stock.get('sector', 'Unknown')
            comp_score = stock.get('composite_score', 0)
            qual_score = stock.get('quality_score', 0) or 0
            val_score = stock.get('value_score', 0) or 0
            grow_score = stock.get('growth_score', 0) or 0
            mom_score = stock.get('momentum_score', 0) or 0
            stab_score = stock.get('stability_score', 0) or 0

            logging.info(
                f"{i:2d}. {symbol:6s} ({sector:20s}) - "
                f"Composite: {comp_score:6.2f} "
                f"[Q:{qual_score:5.2f} "
                f"V:{val_score:5.2f} "
                f"G:{grow_score:5.2f} "
                f"M:{mom_score:5.2f} "
                f"S:{stab_score:5.2f}]"
            )

        cursor.close()
        conn.close()

        logging.info("\n✅ Sector-based scoring completed successfully!")

    except Exception as e:
        logging.error(f"Error in scoring: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
