#!/usr/bin/env python3
"""
Generate comprehensive market data JSON from database
"""

import json
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import os

DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'user': 'stocks',
    'password': os.environ.get('DB_PASSWORD', 'bed0elAn'),
    'database': 'stocks'
}

def query_db(sql, params=None):
    """Execute a database query"""
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(sql, params or [])
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

def get_fear_greed_data():
    """Get Fear & Greed data"""
    sql = """
        SELECT
            date,
            index_value as value,
            rating
        FROM fear_greed_index
        ORDER BY date DESC
        LIMIT 30
    """
    return list(reversed(query_db(sql)))

def get_aaii_data():
    """Get AAII sentiment data"""
    sql = """
        SELECT
            date,
            bullish,
            bearish,
            neutral
        FROM aaii_sentiment
        ORDER BY date DESC
        LIMIT 30
    """
    return list(reversed(query_db(sql)))

def get_naaim_data():
    """Get NAAIM data"""
    sql = """
        SELECT
            date,
            naaim_number_mean as mean
        FROM naaim
        ORDER BY date DESC
        LIMIT 30
    """
    return list(reversed(query_db(sql)))

def get_market_breadth():
    """Get latest market data"""
    sql = """
        SELECT
            COUNT(*) as total_stocks,
            SUM(CASE WHEN return_1d > 0 THEN 1 ELSE 0 END) as advancing,
            SUM(CASE WHEN return_1d < 0 THEN 1 ELSE 0 END) as declining,
            SUM(CASE WHEN return_1d = 0 THEN 1 ELSE 0 END) as unchanged,
            date
        FROM market_data
        WHERE date = (SELECT MAX(date) FROM market_data)
        GROUP BY date
    """
    result = query_db(sql)
    if result:
        r = result[0]
        advancing = r['advancing'] or 0
        declining = r['declining'] or 0
        total = r['total_stocks'] or 1
        ratio = advancing / declining if declining > 0 else 0
        return {
            'advancing': advancing,
            'declining': declining,
            'unchanged': r['unchanged'] or 0,
            'total_stocks': total,
            'advance_decline_ratio': float(ratio),
            'date': str(r['date']) if r['date'] else ''
        }
    return {}

def get_seasonality_data():
    """Get seasonality data"""
    monthly = []
    sql = "SELECT month, avg_return, win_rate FROM seasonality_monthly ORDER BY month"
    for row in query_db(sql):
        monthly.append({
            'month': row['month'],
            'avgReturn': float(row['avg_return']),
            'winRate': float(row['win_rate'])
        })

    return {
        'monthly': monthly,
        'quarterly': [],
        'current': 'February'
    }

def generate_comprehensive_data():
    """Generate comprehensive market data"""
    print("🔄 Generating comprehensive market data from database...")

    data = {
        'timestamp': datetime.now().isoformat(),
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'sentiment': {
            'aaii': get_aaii_data(),
            'fear_greed': get_fear_greed_data(),
            'naaim': get_naaim_data()
        },
        'market_breadth': get_market_breadth(),
        'seasonality': get_seasonality_data(),
        'indices': {},
        'sectors': {},
        'market_internals': {}
    }

    # Write to file
    output_path = '/tmp/comprehensive_market_data.json'
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2, default=str)

    print(f"✅ Comprehensive market data generated: {output_path}")
    print(f"   - AAII records: {len(data['sentiment']['aaii'])}")
    print(f"   - Fear & Greed records: {len(data['sentiment']['fear_greed'])}")
    print(f"   - NAAIM records: {len(data['sentiment']['naaim'])}")
    print(f"   - Seasonality records: {len(data['seasonality']['monthly'])}")

if __name__ == '__main__':
    try:
        generate_comprehensive_data()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
