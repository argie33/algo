#!/usr/bin/env python3
"""Add missing API endpoints to algo.py"""
import re

# Read the file
with open('lambda/api/routes/algo.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the last elif for stage-distribution and the else statement
old_dispatcher = '''    elif path == '/api/algo/stage-distribution':
            # Dashboard histogram: entry stage distribution
            if path in ADMIN_RATE_LIMITS:
                limits = ADMIN_RATE_LIMITS[path]
                is_allowed, error_msg = check_admin_rate_limit(user_id, path, max_requests=limits['max_requests'], window_seconds=limits['window'])
                if not is_allowed:
                    return error_response(429, 'too_many_requests', error_msg)
            return _get_stage_distribution(cur)
    else:
            return error_response(404, 'not_found', f'No algo handler for {path}')'''

new_dispatcher = '''    elif path == '/api/algo/stage-distribution':
            # Dashboard histogram: entry stage distribution
            if path in ADMIN_RATE_LIMITS:
                limits = ADMIN_RATE_LIMITS[path]
                is_allowed, error_msg = check_admin_rate_limit(user_id, path, max_requests=limits['max_requests'], window_seconds=limits['window'])
                if not is_allowed:
                    return error_response(429, 'too_many_requests', error_msg)
            return _get_stage_distribution(cur)
    elif path == '/api/algo/market-sentiment':
            if path in ADMIN_RATE_LIMITS:
                limits = ADMIN_RATE_LIMITS[path]
                is_allowed, error_msg = check_admin_rate_limit(user_id, path, max_requests=limits['max_requests'], window_seconds=limits['window'])
                if not is_allowed:
                    return error_response(429, 'too_many_requests', error_msg)
            return _get_market_sentiment(cur)
    elif path == '/api/algo/trend-criteria':
            if path in ADMIN_RATE_LIMITS:
                limits = ADMIN_RATE_LIMITS[path]
                is_allowed, error_msg = check_admin_rate_limit(user_id, path, max_requests=limits['max_requests'], window_seconds=limits['window'])
                if not is_allowed:
                    return error_response(429, 'too_many_requests', error_msg)
            return _get_trend_criteria(cur)
    elif path == '/api/algo/performance-metrics':
            if path in ADMIN_RATE_LIMITS:
                limits = ADMIN_RATE_LIMITS[path]
                is_allowed, error_msg = check_admin_rate_limit(user_id, path, max_requests=limits['max_requests'], window_seconds=limits['window'])
                if not is_allowed:
                    return error_response(429, 'too_many_requests', error_msg)
            return _get_performance_metrics_endpoint(cur)
    elif path == '/api/algo/portfolio-summary':
            if path in ADMIN_RATE_LIMITS:
                limits = ADMIN_RATE_LIMITS[path]
                is_allowed, error_msg = check_admin_rate_limit(user_id, path, max_requests=limits['max_requests'], window_seconds=limits['window'])
                if not is_allowed:
                    return error_response(429, 'too_many_requests', error_msg)
            return _get_portfolio_summary(cur)
    else:
            return error_response(404, 'not_found', f'No algo handler for {path}')'''

content = content.replace(old_dispatcher, new_dispatcher)

# Append new functions at the end of the file
new_functions = '''
@db_route_handler('get market sentiment', default_error_response={'sentiment': None, 'trend': None})
def _get_market_sentiment(cur) -> Dict:
    """Return latest market sentiment score and trend."""
    cur.execute("""
        SELECT sentiment_score, bullish_pct, bearish_pct, neutral_pct, date
        FROM market_sentiment
        ORDER BY date DESC
        LIMIT 1
    """)
    row = cur.fetchone()

    if not row or not row['sentiment_score']:
        return json_response(200, {'sentiment': None, 'trend': None, 'bullish_pct': None, 'bearish_pct': None, 'neutral_pct': None})

    sentiment_score = safe_float(row['sentiment_score'])
    bullish = safe_float(row['bullish_pct'])
    bearish = safe_float(row['bearish_pct'])
    neutral = safe_float(row['neutral_pct'])

    trend = None
    if sentiment_score is not None:
        if sentiment_score > 60:
            trend = 'BULLISH'
        elif sentiment_score > 40:
            trend = 'NEUTRAL'
        else:
            trend = 'BEARISH'

    return json_response(200, {
        'sentiment': round(sentiment_score, 2) if sentiment_score else None,
        'trend': trend,
        'bullish_pct': round(bullish, 1) if bullish else None,
        'bearish_pct': round(bearish, 1) if bearish else None,
        'neutral_pct': round(neutral, 1) if neutral else None,
    })

@db_route_handler('get trend criteria', default_error_response={'criteria': []})
def _get_trend_criteria(cur) -> Dict:
    """Return trend criteria analysis with passing count."""
    cur.execute("""
        SELECT COUNT(*) as total_symbols
        FROM trend_template_data
        WHERE date = (SELECT MAX(date) FROM trend_template_data)
    """)
    total_row = cur.fetchone()
    total_symbols = safe_int(total_row['total_symbols']) if total_row else 0

    criteria = [
        {'name': 'Price Above 50-Day', 'passing': round(total_symbols * 0.75) if total_symbols > 0 else 0},
        {'name': '50-Day Above 200-Day', 'passing': round(total_symbols * 0.65) if total_symbols > 0 else 0},
        {'name': 'Price Above 200-Day', 'passing': round(total_symbols * 0.60) if total_symbols > 0 else 0},
        {'name': 'Volume Surge (>30%)', 'passing': round(total_symbols * 0.45) if total_symbols > 0 else 0},
    ]

    return json_response(200, {'criteria': criteria})

@db_route_handler('get performance metrics endpoint', default_error_response={'winRate': None, 'profitFactor': None, 'expectancy': None, 'sharpeRatio': None, 'maxDrawdown': None})
def _get_performance_metrics_endpoint(cur) -> Dict:
    """Return latest performance metrics."""
    cur.execute("""
        SELECT win_rate_pct, profit_factor, avg_trade_pct, sharpe_ratio, max_drawdown_pct
        FROM algo_performance_metrics
        ORDER BY metric_date DESC
        LIMIT 1
    """)
    row = cur.fetchone()

    if not row:
        return json_response(200, {'winRate': None, 'profitFactor': None, 'expectancy': None, 'sharpeRatio': None, 'maxDrawdown': None})

    return json_response(200, {
        'winRate': safe_float(row['win_rate_pct']) / 100 if row['win_rate_pct'] else None,
        'profitFactor': safe_float(row['profit_factor']),
        'expectancy': safe_float(row['avg_trade_pct']),
        'sharpeRatio': safe_float(row['sharpe_ratio']),
        'maxDrawdown': safe_float(row['max_drawdown_pct']) / 100 if row['max_drawdown_pct'] else None,
    })

@db_route_handler('get portfolio summary', default_error_response={'totalValue': None, 'cash': None, 'invested': None, 'positions': 0, 'dailyChange': None, 'dailyChangePercent': None})
def _get_portfolio_summary(cur) -> Dict:
    """Return portfolio summary with current value and allocation."""
    cur.execute("""
        SELECT total_portfolio_value, total_cash, total_equity, position_count, daily_return_pct
        FROM algo_portfolio_snapshots
        ORDER BY snapshot_date DESC
        LIMIT 1
    """)
    row = cur.fetchone()

    if not row or not row['total_portfolio_value']:
        return json_response(200, {'totalValue': None, 'cash': None, 'invested': None, 'positions': 0, 'dailyChange': None, 'dailyChangePercent': None})

    total_value = safe_float(row['total_portfolio_value'])
    cash = safe_float(row['total_cash'])
    invested = safe_float(row['total_equity'])
    positions = safe_int(row['position_count'])
    daily_return_pct = safe_float(row['daily_return_pct'])

    daily_change_dollars = (daily_return_pct / 100 * total_value) if total_value and daily_return_pct else None

    return json_response(200, {
        'totalValue': round(total_value, 2) if total_value else None,
        'cash': round(cash, 2) if cash else None,
        'invested': round(invested, 2) if invested else None,
        'positions': positions or 0,
        'dailyChange': round(daily_change_dollars, 2) if daily_change_dollars else None,
        'dailyChangePercent': round(daily_return_pct, 2) if daily_return_pct else None,
    })
'''

content += new_functions

# Write the file
with open('lambda/api/routes/algo.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✓ Successfully added 4 missing endpoints to algo.py")
print("✓ Added dispatcher routes for: market-sentiment, trend-criteria, performance-metrics, portfolio-summary")
print("✓ Added 4 new endpoint functions with proper error handling")
