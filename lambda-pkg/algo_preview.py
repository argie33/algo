#!/usr/bin/env python3
"""Pre-trade position preview - show impact before submitting."""

import sys
import json
import logging
from pathlib import Path
from dotenv import load_dotenv

from algo_position_sizer import PositionSizer
from algo_config import DATABASE_CONFIG, ALGO_CONFIG

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

logger = logging.getLogger(__name__)

def get_preview(symbol, entry_price, stop_loss_price):
    """Get position preview for a trade."""
    try:
        sizer = PositionSizer(DATABASE_CONFIG, ALGO_CONFIG)
        
        # Get position sizing
        shares, risk_amount, pct_allocated = sizer.calculate_position_size(
            symbol, entry_price, stop_loss_price
        )
        
        # Get portfolio value
        portfolio_value = sizer._get_portfolio_value()
        position_value = shares * entry_price
        
        # Calculate targets (1.5R, 3R, 4R)
        risk_per_share = entry_price - stop_loss_price
        t1_price = round(entry_price + (risk_per_share * 1.5), 2)
        t2_price = round(entry_price + (risk_per_share * 3.0), 2)
        t3_price = round(entry_price + (risk_per_share * 4.0), 2)
        
        # Calculate potential profit at each target
        t1_profit = (t1_price - entry_price) * shares
        t2_profit = (t2_price - entry_price) * shares
        t3_profit = (t3_price - entry_price) * shares
        
        result = {
            'symbol': symbol,
            'entry_price': entry_price,
            'stop_loss': stop_loss_price,
            'shares': round(shares, 2),
            'risk_per_share': round(risk_per_share, 2),
            'position_value': round(position_value, 2),
            'risk_amount': round(risk_amount, 2),
            'pct_of_portfolio': round(pct_allocated, 2),
            'portfolio_value': round(portfolio_value, 2),
            'targets': {
                'target_1': {
                    'price': t1_price,
                    'r_multiple': 1.5,
                    'shares_to_sell': round(shares * 0.5, 2),
                    'profit_at_target': round(t1_profit, 2),
                },
                'target_2': {
                    'price': t2_price,
                    'r_multiple': 3.0,
                    'shares_to_sell': round(shares * 0.25, 2),
                    'profit_at_target': round(t2_profit, 2),
                },
                'target_3': {
                    'price': t3_price,
                    'r_multiple': 4.0,
                    'shares_to_sell': round(shares * 0.25, 2),
                    'profit_at_target': round(t3_profit, 2),
                },
            },
            'worst_case': {
                'stop_loss_price': stop_loss_price,
                'shares_lost': shares,
                'loss_amount': round(-risk_amount, 2),
            },
        }
        
        print(json.dumps(result))
        sys.exit(0)
    except Exception as e:
        print(json.dumps({'error': str(e)}))
        sys.exit(1)

if __name__ == '__main__':
    if len(sys.argv) < 4:
        print(json.dumps({'error': 'Usage: symbol entry_price stop_loss_price'}))
        sys.exit(1)
    
    symbol = sys.argv[1]
    try:
        entry_price = float(sys.argv[2])
        stop_loss_price = float(sys.argv[3])
    except ValueError:
        print(json.dumps({'error': 'Invalid price format'}))
        sys.exit(1)
    
    get_preview(symbol, entry_price, stop_loss_price)
