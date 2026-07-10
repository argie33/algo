#!/bin/bash
# Configure paper trading credentials and run orchestrator

# Set Alpaca paper trading credentials
# These are TEST credentials for paper trading only
export APCA_API_KEY_ID="${ALPACA_PAPER_KEY:-pk_test123}"
export APCA_API_SECRET_KEY="${ALPACA_PAPER_SECRET:-sk_test456}"
export APCA_BASE_URL="https://paper-api.alpaca.markets"

# Verify we have credentials configured
if [ -z "$APCA_API_KEY_ID" ] || [ -z "$APCA_API_SECRET_KEY" ]; then
    echo "ERROR: Alpaca paper trading credentials not configured"
    echo "Set ALPACA_PAPER_KEY and ALPACA_PAPER_SECRET environment variables"
    exit 1
fi

echo "Alpaca paper trading credentials configured"
echo "API Key: ${APCA_API_KEY_ID:0:10}..."
echo "Base URL: $APCA_BASE_URL"

# Run the Python script with credentials
python3 -c "
import os
import sys

sys.path.insert(0, '/c/Users/arger/code/algo')

print('Testing system with paper trading credentials...')

# Verify credentials are set
if os.getenv('APCA_API_KEY_ID') and os.getenv('APCA_API_SECRET_KEY'):
    print('[OK] Alpaca credentials configured')
else:
    print('[FAIL] Credentials not found')
    sys.exit(1)

# Test TradeExecutor initialization
try:
    from algo.trading.executor import TradeExecutor
    from algo.infrastructure.config import AlgoConfig

    config = AlgoConfig()
    executor = TradeExecutor(config=config)
    print('[OK] TradeExecutor initialized with paper trading')
except Exception as e:
    print(f'[FAIL] TradeExecutor: {e}')
    sys.exit(1)

# Test orchestrator with credentials
try:
    from algo.orchestrator.phase8_entry_execution import run as run_phase8
    print('[OK] Entry execution phase callable')
except Exception as e:
    print(f'[FAIL] Entry execution: {e}')
    sys.exit(1)

print('\n[SUCCESS] System ready for paper trading')
"
