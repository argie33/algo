"""
Setup script for Alpaca Trading System
Installs dependencies and sets up the trading environment
"""

import os
import sys
import subprocess
from pathlib import Path

def install_requirements():
    """Install required packages"""
    requirements = [
        "alpaca-trade-api>=3.0.0",
        "pandas>=1.3.0",
        "numpy>=1.21.0",
        "scikit-learn>=1.0.0",
        "matplotlib>=3.5.0",
        "seaborn>=0.11.0",
        "plotly>=5.0.0",
        "yfinance>=0.1.87",
        "ta>=0.10.0",
        "asyncio-mqtt>=0.11.0",
        "aiohttp>=3.8.0",
        "python-dotenv>=0.19.0",
        "schedule>=1.1.0",
        "psutil>=5.8.0",
        "sqlalchemy>=1.4.0",
        "redis>=4.0.0",
        "websockets>=10.0"
    ]
    
    print("Installing required packages...")
    for package in requirements:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
            print(f"✓ {package}")
        except subprocess.CalledProcessError:
            print(f"✗ Failed to install {package}")
            return False
    
    return True

def create_env_file():
    """Create .env file template"""
    env_content = """# Alpaca Trading System Environment Variables

# Paper Trading (Testing)
ALPACA_PAPER_API_KEY=your_paper_api_key_here
ALPACA_PAPER_API_SECRET=your_paper_api_secret_here
ALPACA_PAPER_BASE_URL=https://paper-api.alpaca.markets

# Live Trading (Production)
ALPACA_LIVE_API_KEY=your_live_api_key_here
ALPACA_LIVE_API_SECRET=your_live_api_secret_here
ALPACA_LIVE_BASE_URL=https://api.alpaca.markets

# Trading Configuration
TRADING_MODE=paper
MAX_POSITION_SIZE=0.05
MAX_DAILY_LOSS=0.10
RISK_LEVEL=moderate

# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=trading_system
DB_USER=postgres
DB_PASSWORD=your_db_password

# Monitoring and Alerts
EMAIL_ALERTS=true
SLACK_WEBHOOK_URL=your_slack_webhook_url
DISCORD_WEBHOOK_URL=your_discord_webhook_url

# Logging
LOG_LEVEL=INFO
LOG_FILE=trading_system.log
"""
    
    env_file = Path(".env")
    if not env_file.exists():
        with open(env_file, "w") as f:
            f.write(env_content)
        print("✓ Created .env file template")
        print("  Please update with your actual API keys and configuration")
    else:
        print("✓ .env file already exists")

def create_directories():
    """Create necessary directories"""
    directories = [
        "logs",
        "data",
        "backtest_results",
        "reports",
        "strategies/custom"
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        print(f"✓ Created directory: {directory}")

def create_startup_script():
    """Create startup script"""
    startup_content = """#!/usr/bin/env python3
'''
Alpaca Trading System Startup Script
'''

import os
import sys
import logging
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO')),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.getenv('LOG_FILE', 'trading_system.log')),
        logging.StreamHandler()
    ]
)

from trading_engine import TradingEngine, TradingMode
import asyncio

async def main():
    # Determine trading mode
    mode_str = os.getenv('TRADING_MODE', 'paper').lower()
    mode = TradingMode.PAPER if mode_str == 'paper' else TradingMode.LIVE
    
    print(f"Starting Alpaca Trading System in {mode.value} mode")
    
    # Create and start trading engine
    engine = TradingEngine(mode)
    session_id = engine.start_trading_session()
    
    print(f"Trading session started: {session_id}")
    
    try:
        # Run trading loop
        await engine.run_trading_loop()
    
    except KeyboardInterrupt:
        print("\\nShutting down trading system...")
    
    finally:
        engine.stop_trading_session()
        print("Trading system stopped")

if __name__ == "__main__":
    asyncio.run(main())
"""
    
    with open("start_trading.py", "w") as f:
        f.write(startup_content)
    
    # Make executable
    os.chmod("start_trading.py", 0o755)
    print("✓ Created startup script: start_trading.py")

def create_config_validator():
    """Create configuration validator script"""
    validator_content = """#!/usr/bin/env python3
'''
Configuration Validator for Alpaca Trading System
'''

import os
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

def validate_alpaca_config():
    '''Validate Alpaca configuration'''
    required_vars = [
        'ALPACA_PAPER_API_KEY',
        'ALPACA_PAPER_API_SECRET'
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print("❌ Missing required environment variables:")
        for var in missing_vars:
            print(f"   {var}")
        return False
    
    # Test connection
    try:
        from alpaca_client import AlpacaClient
        client = AlpacaClient()
        account = client.get_account()
        print(f"✓ Connected to Alpaca {client.config.environment.value} account")
        print(f"  Account status: {account['status']}")
        print(f"  Buying power: ${account['buying_power']:,.2f}")
        return True
    except Exception as e:
        print(f"❌ Failed to connect to Alpaca: {e}")
        return False

def validate_trading_config():
    '''Validate trading configuration'''
    from config import validate_config
    
    errors = validate_config()
    if errors:
        print("❌ Trading configuration errors:")
        for error in errors:
            print(f"   {error}")
        return False
    
    print("✓ Trading configuration is valid")
    return True

def validate_strategies():
    '''Validate strategy configuration'''
    try:
        from strategies.momentum_strategy import MomentumBreakoutStrategy
        
        strategy = MomentumBreakoutStrategy()
        print(f"✓ Momentum strategy loaded: {strategy.name}")
        
        # Test with sample data
        import pandas as pd
        import numpy as np
        
        # Create sample data
        dates = pd.date_range('2023-01-01', periods=50, freq='D')
        data = pd.DataFrame({
            'open': np.random.uniform(100, 110, 50),
            'high': np.random.uniform(110, 120, 50),
            'low': np.random.uniform(90, 100, 50),
            'close': np.random.uniform(100, 110, 50),
            'volume': np.random.uniform(1000000, 2000000, 50)
        }, index=dates)
        
        signals = strategy.generate_signals({'TEST': data})
        print(f"✓ Strategy generated {len(signals)} signals from test data")
        
        return True
        
    except Exception as e:
        print(f"❌ Strategy validation failed: {e}")
        return False

def main():
    print("Validating Alpaca Trading System Configuration...")
    print("=" * 50)
    
    all_valid = True
    
    # Validate Alpaca connection
    print("\\n1. Validating Alpaca connection...")
    if not validate_alpaca_config():
        all_valid = False
    
    # Validate trading configuration
    print("\\n2. Validating trading configuration...")
    if not validate_trading_config():
        all_valid = False
    
    # Validate strategies
    print("\\n3. Validating strategies...")
    if not validate_strategies():
        all_valid = False
    
    print("\\n" + "=" * 50)
    if all_valid:
        print("✓ All validations passed! System is ready to trade.")
        print("\\nTo start trading, run: python start_trading.py")
    else:
        print("❌ Some validations failed. Please fix the issues above.")
        sys.exit(1)

if __name__ == "__main__":
    main()
"""
    
    with open("validate_config.py", "w") as f:
        f.write(validator_content)
    
    os.chmod("validate_config.py", 0o755)
    print("✓ Created configuration validator: validate_config.py")

def create_monitoring_dashboard():
    """Create simple monitoring dashboard"""
    dashboard_content = """#!/usr/bin/env python3
'''
Simple Monitoring Dashboard for Alpaca Trading System
'''

import os
import sys
import sqlite3
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

def get_trading_summary():
    '''Get trading summary from database'''
    db_path = Path("trading_data.db")
    
    if not db_path.exists():
        print("No trading data found. Start a trading session first.")
        return
    
    conn = sqlite3.connect(db_path)
    
    # Get latest session
    sessions_df = pd.read_sql_query(
        "SELECT * FROM trading_sessions ORDER BY start_time DESC LIMIT 1",
        conn
    )
    
    if sessions_df.empty:
        print("No trading sessions found.")
        conn.close()
        return
    
    session = sessions_df.iloc[0]
    session_id = session['session_id']
    
    print(f"Trading Session: {session_id}")
    print(f"Start Time: {session['start_time']}")
    print(f"Mode: {session['mode']}")
    print(f"Total Trades: {session['total_trades']}")
    print(f"Profitable Trades: {session['profitable_trades']}")
    print(f"Win Rate: {session['profitable_trades'] / max(session['total_trades'], 1):.2%}")
    print(f"Total P&L: ${session['total_pnl']:.2f}")
    print(f"Max Drawdown: {session['max_drawdown']:.2%}")
    
    # Get recent signals
    signals_df = pd.read_sql_query(
        f"SELECT * FROM signals WHERE session_id = '{session_id}' ORDER BY timestamp DESC LIMIT 10",
        conn
    )
    
    if not signals_df.empty:
        print("\\nRecent Signals:")
        print("-" * 80)
        for _, signal in signals_df.iterrows():
            print(f"{signal['timestamp'][:19]} | {signal['symbol']:6} | {signal['signal_type']:4} | "
                  f"Strength: {signal['strength']:.2f} | Confidence: {signal['confidence']:.2f}")
    
    # Get recent trades
    trades_df = pd.read_sql_query(
        f"SELECT * FROM trades WHERE session_id = '{session_id}' ORDER BY timestamp DESC LIMIT 10",
        conn
    )
    
    if not trades_df.empty:
        print("\\nRecent Trades:")
        print("-" * 80)
        for _, trade in trades_df.iterrows():
            print(f"{trade['timestamp'][:19]} | {trade['symbol']:6} | {trade['side']:4} | "
                  f"Qty: {trade['quantity']:8.2f} | Price: ${trade['price']:8.2f}")
    
    # Get performance metrics
    performance_df = pd.read_sql_query(
        f"SELECT * FROM performance WHERE session_id = '{session_id}' ORDER BY timestamp DESC LIMIT 1",
        conn
    )
    
    if not performance_df.empty:
        perf = performance_df.iloc[0]
        print("\\nCurrent Performance:")
        print("-" * 40)
        print(f"Portfolio Value: ${perf['portfolio_value']:,.2f}")
        print(f"Cash: ${perf['cash']:,.2f}")
        print(f"Positions Value: ${perf['positions_value']:,.2f}")
        print(f"Daily P&L: ${perf['daily_pnl']:,.2f}")
        print(f"Total P&L: ${perf['total_pnl']:,.2f}")
        print(f"Drawdown: {perf['drawdown']:.2%}")
    
    conn.close()

def get_live_status():
    '''Get live trading status'''
    try:
        from alpaca_client import AlpacaClient
        
        client = AlpacaClient()
        account = client.get_account()
        positions = client.get_positions()
        orders = client.get_orders(status='open')
        
        print("\\nLive Account Status:")
        print("-" * 40)
        print(f"Account Status: {account['status']}")
        print(f"Buying Power: ${account['buying_power']:,.2f}")
        print(f"Portfolio Value: ${account['portfolio_value']:,.2f}")
        print(f"Day Trade Count: {account['daytrade_count']}")
        print(f"Pattern Day Trader: {account['pattern_day_trader']}")
        
        print(f"\\nPositions ({len(positions)}):")
        if positions:
            for pos in positions:
                print(f"  {pos.symbol}: {pos.qty} shares @ ${pos.avg_entry_price:.2f} "
                      f"(P&L: ${pos.unrealized_pl:.2f})")
        
        print(f"\\nOpen Orders ({len(orders)}):")
        if orders:
            for order in orders:
                print(f"  {order.symbol}: {order.side} {order.qty} @ {order.order_type} "
                      f"({order.status})")
        
        print(f"\\nMarket Status: {'Open' if client.is_market_open() else 'Closed'}")
        
    except Exception as e:
        print(f"Error getting live status: {e}")

def main():
    print("Alpaca Trading System - Monitoring Dashboard")
    print("=" * 60)
    
    # Get trading summary
    get_trading_summary()
    
    # Get live status
    get_live_status()
    
    print("\\n" + "=" * 60)
    print("Dashboard updated:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

if __name__ == "__main__":
    main()
"""
    
    with open("monitor.py", "w") as f:
        f.write(dashboard_content)
    
    os.chmod("monitor.py", 0o755)
    print("✓ Created monitoring dashboard: monitor.py")

def create_readme():
    """Create comprehensive README"""
    readme_content = """# Alpaca Trading System

An advanced algorithmic trading system built for Alpaca Markets API, featuring institutional-grade risk management, multiple trading strategies, and comprehensive monitoring.

## Features

### 🚀 Core Trading Engine
- **Asynchronous Trading Loop**: High-performance async processing
- **Multiple Strategy Support**: Momentum, mean reversion, pattern recognition
- **Risk Management**: Portfolio risk limits, position sizing, drawdown controls
- **Real-time Monitoring**: Live performance tracking and alerts

### 📊 Trading Strategies
- **Momentum Breakout**: Identifies stocks breaking out with volume confirmation
- **Mean Reversion**: Statistical arbitrage and oversold/overbought signals
- **Pattern Recognition**: Technical chart patterns with ML validation
- **Multi-timeframe Analysis**: Signals across different time horizons

### 🛡️ Risk Management
- **Position Sizing**: Kelly criterion and risk-parity based sizing
- **Portfolio Limits**: Maximum position size, sector concentration limits
- **Drawdown Protection**: Automatic shutdown on excessive losses
- **Pre-trade Checks**: Comprehensive risk validation before execution

### 📈 Performance Monitoring
- **Real-time Metrics**: Live P&L, win rate, Sharpe ratio tracking
- **Historical Analysis**: Complete trade history and performance attribution
- **Risk Analytics**: VaR, correlation analysis, stress testing
- **Alerting System**: Email, Slack, Discord notifications

## Quick Start

### 1. Installation
```bash
# Clone the repository
git clone <repository-url>
cd alpaca_trading_system

# Run setup script
python setup.py
```

### 2. Configuration
Edit the `.env` file with your Alpaca API credentials:
```env
ALPACA_PAPER_API_KEY=your_paper_api_key_here
ALPACA_PAPER_API_SECRET=your_paper_api_secret_here
TRADING_MODE=paper
```

### 3. Validation
Validate your configuration:
```bash
python validate_config.py
```

### 4. Start Trading
Start the trading system:
```bash
python start_trading.py
```

### 5. Monitor Performance
View live performance:
```bash
python monitor.py
```

## Configuration

### Trading Parameters
- `MAX_POSITION_SIZE`: Maximum position size as % of portfolio (default: 5%)
- `MAX_DAILY_LOSS`: Maximum daily loss limit (default: 10%)
- `RISK_LEVEL`: Risk tolerance level (conservative/moderate/aggressive)

### Strategy Configuration
Strategies can be configured in `config.py`:
```python
STRATEGY_PARAMS = {
    "momentum_breakout": {
        "lookback_period": 20,
        "volume_threshold": 1.5,
        "rsi_threshold": 60
    }
}
```

## Trading Strategies

### Momentum Breakout Strategy
- Identifies stocks breaking out of consolidation patterns
- Requires 1.5x average volume for confirmation
- Uses RSI > 60 for momentum validation
- ATR-based stop losses and profit targets

### Risk Management Features
- **Pre-trade Risk Checks**: Validates every trade against risk limits
- **Position Sizing**: Kelly criterion with risk-parity adjustments
- **Drawdown Protection**: Automatic shutdown on excessive losses
- **Correlation Limits**: Prevents over-concentration in correlated assets

## File Structure

```
alpaca_trading_system/
├── config.py              # System configuration
├── alpaca_client.py        # Alpaca API client
├── trading_engine.py       # Main trading engine
├── strategies/
│   ├── base_strategy.py    # Base strategy class
│   ├── momentum_strategy.py # Momentum breakout strategy
│   └── custom/            # Custom strategies
├── setup.py               # Setup script
├── start_trading.py       # Main entry point
├── validate_config.py     # Configuration validator
├── monitor.py             # Monitoring dashboard
└── README.md             # This file
```

## API Reference

### Trading Engine
```python
from trading_engine import TradingEngine, TradingMode

# Create engine
engine = TradingEngine(TradingMode.PAPER)

# Start trading session
session_id = engine.start_trading_session()

# Run trading loop
await engine.run_trading_loop()
```

### Strategy Development
```python
from strategies.base_strategy import BaseStrategy, Signal, SignalType

class MyStrategy(BaseStrategy):
    def generate_signals(self, data):
        # Implement your strategy logic
        pass
```

### Risk Management
```python
from trading_engine import RiskManager

risk_manager = RiskManager()
risk_ok, msg = risk_manager.check_pre_trade_risk(signal, portfolio_value, positions)
```

## Safety Features

### Paper Trading First
- Always test strategies in paper trading mode
- Validate performance before live trading
- Use small position sizes initially

### Risk Controls
- Hard stops on daily losses
- Position size limits
- Drawdown protection
- Correlation limits

### Monitoring
- Real-time performance tracking
- Automated alerts on issues
- Complete audit trail

## Troubleshooting

### Common Issues

1. **API Connection Error**
   - Verify API keys in `.env` file
   - Check network connectivity
   - Ensure market is open for testing

2. **Strategy Not Generating Signals**
   - Check data availability
   - Verify strategy parameters
   - Review filtering criteria

3. **Risk Checks Failing**
   - Review position sizing
   - Check account balance
   - Verify risk parameters

### Support
- Check logs in `logs/` directory
- Run `python validate_config.py` for diagnostics
- Review error messages in console output

## Disclaimer

This software is for educational and research purposes only. Trading involves substantial risk and may not be suitable for all investors. Past performance is not indicative of future results. Always test strategies thoroughly in paper trading before using real money.

## License

MIT License - see LICENSE file for details
"""
    
    with open("README.md", "w") as f:
        f.write(readme_content)
    
    print("✓ Created comprehensive README.md")

def main():
    print("Setting up Alpaca Trading System...")
    print("=" * 50)
    
    # Install requirements
    if not install_requirements():
        print("❌ Failed to install requirements")
        return False
    
    # Create environment file
    create_env_file()
    
    # Create directories
    create_directories()
    
    # Create scripts
    create_startup_script()
    create_config_validator()
    create_monitoring_dashboard()
    create_readme()
    
    print("\n" + "=" * 50)
    print("✓ Setup complete!")
    print("\nNext steps:")
    print("1. Edit .env file with your Alpaca API credentials")
    print("2. Run: python validate_config.py")
    print("3. Run: python start_trading.py")
    print("4. Monitor with: python monitor.py")
    print("\nHappy trading! 🚀")

if __name__ == "__main__":
    main()