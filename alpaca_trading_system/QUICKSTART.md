# Alpaca Trading System - Quick Start Guide

## Overview

This is a production-ready algorithmic trading system built for Alpaca Markets. It includes:

- **Advanced Trading Engine**: Asynchronous processing with risk management
- **Multiple Strategies**: Momentum breakout, mean reversion, pattern recognition
- **Risk Management**: Position sizing, drawdown protection, correlation limits
- **Real-time Monitoring**: Live performance tracking and alerts

## 🚀 Quick Setup

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure API Keys
Copy the environment template:
```bash
cp .env.example .env
```

Edit `.env` with your Alpaca credentials:
```env
ALPACA_PAPER_API_KEY=your_paper_api_key_here
ALPACA_PAPER_API_SECRET=your_paper_api_secret_here
TRADING_MODE=paper
```

### 3. Test Configuration
```bash
python validate_config.py
```

### 4. Start Trading
```bash
python start_trading.py
```

### 5. Monitor Performance
```bash
python monitor.py
```

## 📊 Key Features

### Trading Strategies
- **Momentum Breakout**: Identifies stocks breaking resistance with volume
- **Risk Management**: Kelly criterion position sizing with drawdown protection
- **Multi-timeframe**: Signals across different time horizons

### Risk Controls
- Maximum 5% position size per trade
- 10% daily loss limit
- 20% maximum drawdown protection
- Correlation and sector concentration limits

### Performance Monitoring
- Real-time P&L tracking
- Win rate and Sharpe ratio calculation
- Complete trade history
- Risk analytics (VaR, correlation)

## 🛡️ Safety First

1. **Always start with paper trading**
2. **Test strategies thoroughly**
3. **Start with small position sizes**
4. **Monitor performance closely**
5. **Never risk more than you can afford to lose**

## 📁 File Structure

```
alpaca_trading_system/
├── config.py              # System configuration
├── alpaca_client.py        # Alpaca API client
├── trading_engine.py       # Main trading engine
├── strategies/
│   ├── base_strategy.py    # Base strategy class
│   └── momentum_strategy.py # Momentum breakout strategy
├── start_trading.py        # Main entry point
├── validate_config.py      # Configuration validator
├── monitor.py             # Monitoring dashboard
└── requirements.txt       # Dependencies
```

## 💡 Example Usage

### Basic Trading Session
```python
from trading_engine import TradingEngine, TradingMode

# Create engine in paper mode
engine = TradingEngine(TradingMode.PAPER)

# Start session
session_id = engine.start_trading_session()

# Run trading loop
await engine.run_trading_loop()
```

### Custom Strategy
```python
from strategies.base_strategy import BaseStrategy, Signal, SignalType

class MyStrategy(BaseStrategy):
    def generate_signals(self, data):
        signals = []
        for symbol, df in data.items():
            # Your strategy logic here
            if condition_met:
                signal = Signal(
                    symbol=symbol,
                    signal_type=SignalType.BUY,
                    strength=0.8,
                    confidence=0.7,
                    price=df['close'].iloc[-1]
                )
                signals.append(signal)
        return signals
```

## 🔧 Configuration Options

### Trading Parameters
```python
TRADING_CONFIG = {
    'max_position_size': 0.05,    # 5% max position
    'max_daily_loss': 0.10,       # 10% daily loss limit
    'risk_level': 'moderate',     # Risk tolerance
    'stop_loss_pct': 0.02,        # 2% stop loss
    'take_profit_pct': 0.06       # 6% take profit
}
```

### Strategy Weights
```python
STRATEGY_WEIGHTS = {
    'momentum_breakout': 0.4,
    'mean_reversion': 0.3,
    'pattern_recognition': 0.3
}
```

## 🚨 Important Notes

### Risk Disclaimer
- **This is for educational purposes only**
- **Trading involves substantial risk**
- **Past performance doesn't guarantee future results**
- **Always test in paper trading first**

### Getting Alpaca API Keys
1. Sign up at [Alpaca Markets](https://alpaca.markets)
2. Complete account verification
3. Generate API keys in the dashboard
4. Start with paper trading keys

### Troubleshooting
- Check API keys are correct
- Verify market is open for testing
- Review logs for error messages
- Ensure sufficient buying power

## 🎯 Next Steps

1. **Backtest strategies** on historical data
2. **Optimize parameters** for better performance
3. **Add custom strategies** for your use case
4. **Implement alerts** for important events
5. **Scale up** gradually after testing

## 📞 Support

- Check logs in `trading_system.log`
- Run `python validate_config.py` for diagnostics
- Review error messages in console
- Test with small positions first

---

**Happy Trading! 🚀**

Remember: The best strategy is the one you understand and can manage risk for. Start small, learn continuously, and trade responsibly.