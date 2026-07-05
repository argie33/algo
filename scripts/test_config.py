#!/usr/bin/env python3
"""Test that config loads without errors."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ['EXECUTION_MODE'] = 'paper'
os.environ['ALPACA_PAPER_TRADING'] = 'true'

from algo.infrastructure.config.main import AlgoConfig

cfg = AlgoConfig()
print('[OK] Config loaded successfully')
print(f'Execution mode: {cfg.get("execution_mode")}')
print(f'Paper trading: {cfg.get("alpaca_paper_trading")}')
print(f'Max positions: {cfg.get("max_positions")}')
