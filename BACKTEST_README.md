# 🚀 Professional Backtesting API

A comprehensive backtesting engine for quantitative trading strategies, built for hedge funds and professional traders.

## ✨ Features

- **Professional-Grade Backtesting Engine**: Full-featured backtesting with realistic transaction costs
- **Comprehensive Performance Metrics**: 15+ key metrics including Sharpe ratio, max drawdown, win rate
- **Flexible Strategy Development**: Write strategies in JavaScript with full market data access
- **Risk Management**: Built-in position sizing, stop losses, and risk controls
- **Multiple Asset Support**: Test strategies across multiple symbols simultaneously
- **RESTful API**: Programmatic access for integration with existing systems
- **Strategy Templates**: Pre-built templates for common strategies
- **Real Market Data**: Backtest against actual historical price data
- **Professional UI**: Web interface for strategy development and analysis (coming soon)

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend UI   │    │   RESTful API   │    │   Database      │
│                 │    │                 │    │                 │
│ • Code Editor   │◄──►│ • Strategy Exec │◄──►│ • Price Data    │
│ • Charts        │    │ • Metrics Calc  │    │ • Company Info  │
│ • Metrics       │    │ • Risk Mgmt     │    │ • Market Data   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 📊 Performance Metrics

The backtesting engine calculates comprehensive performance metrics:

### Returns & Risk
- **Total Return**: Overall percentage return
- **Annualized Return**: Compound annual growth rate
- **Volatility**: Annualized standard deviation of returns
- **Sharpe Ratio**: Risk-adjusted return metric

### Drawdown Analysis
- **Maximum Drawdown**: Largest peak-to-trough decline
- **Drawdown Duration**: Time spent in drawdown periods
- **Recovery Factor**: Return/Max Drawdown ratio

### Trading Statistics
- **Win Rate**: Percentage of profitable trades
- **Profit Factor**: Gross profit / Gross loss ratio
- **Average Win/Loss**: Mean profit/loss per trade
- **Trade Frequency**: Average trades per period

## 🛠️ API Endpoints

### Core Backtesting
- `POST /api/backtest/run` - Execute backtest strategy
- `POST /api/backtest/validate` - Validate strategy syntax
- `GET /api/backtest/symbols` - Get available symbols
- `GET /api/backtest/templates` - Get strategy templates

### Data Access
- Market data automatically fetched from database
- Support for daily, weekly, monthly timeframes
- Corporate actions and dividend adjustments
- Real-time data integration capabilities

## 💡 Strategy Development

### Available Context
Your strategy code has access to:

```javascript
// Market data for current date
data[symbol] = {
  date: '2023-01-15',
  open: 150.25,
  high: 152.10,
  low: 149.80,
  close: 151.45,
  volume: 1000000,
  adj_close: 151.45
}

// Portfolio management
cash              // Available cash
positions         // Current positions map
buy(symbol, qty, price, stopLoss?, takeProfit?)
sell(symbol, qty, price)
sellAll(prices)
getPosition(symbol)
log(message)      // Logging function
```

### Example Strategies

#### 1. Buy and Hold
```javascript
// Equal-weight buy and hold
const symbols = ['AAPL', 'GOOGL', 'MSFT'];

for (const symbol of symbols) {
  if (data[symbol] && !getPosition(symbol)) {
    const price = data[symbol].close;
    const quantity = Math.floor(cash / (price * symbols.length));
    
    if (quantity > 0) {
      buy(symbol, quantity, price);
      log(`Bought ${quantity} shares of ${symbol} at $${price.toFixed(2)}`);
    }
  }
}
```

#### 2. Moving Average Crossover
```javascript
// MA crossover with position management
const symbols = ['AAPL', 'MSFT'];
const shortMA = 20;
const longMA = 50;

for (const symbol of symbols) {
  if (data[symbol]) {
    const price = data[symbol].close;
    const position = getPosition(symbol);
    
    // Buy signal: short MA > long MA (simplified)
    if (!position && shouldBuy(symbol)) {
      const quantity = Math.floor(cash / (price * 2));
      buy(symbol, quantity, price, price * 0.95); // 5% stop loss
    }
    
    // Sell signal: short MA < long MA
    if (position && shouldSell(symbol)) {
      sell(symbol, position.quantity, price);
    }
  }
}
```

#### 3. Mean Reversion
```javascript
// RSI-based mean reversion
const symbols = ['SPY', 'QQQ'];
const RSI_OVERSOLD = 30;
const RSI_OVERBOUGHT = 70;

for (const symbol of symbols) {
  if (data[symbol]) {
    const price = data[symbol].close;
    const position = getPosition(symbol);
    const rsi = calculateRSI(symbol); // Your RSI calculation
    
    if (!position && rsi < RSI_OVERSOLD) {
      const quantity = Math.floor(cash / price);
      buy(symbol, quantity, price);
    }
    
    if (position && rsi > RSI_OVERBOUGHT) {
      sell(symbol, position.quantity, price);
    }
  }
}
```

## 🔧 Configuration Options

```javascript
const config = {
  initialCapital: 100000,    // Starting capital
  commission: 0.001,         // 0.1% per trade
  slippage: 0.001,          // 0.1% market impact
  maxPositions: 10,         // Position limit
  riskPerTrade: 0.02,       // 2% risk per trade
  maxDrawdown: 0.20,        // 20% max drawdown limit
  rebalanceFreq: 'monthly'  // Rebalancing frequency
};
```

## 📈 Usage Examples

### Python Integration
```python
import requests
import pandas as pd
import matplotlib.pyplot as plt

def run_backtest(strategy_code, symbols, start_date, end_date):
    url = "https://your-api.com/api/backtest/run"
    
    payload = {
        "strategy": strategy_code,
        "symbols": symbols,
        "startDate": start_date,
        "endDate": end_date,
        "config": {
            "initialCapital": 100000,
            "commission": 0.001
        }
    }
    
    response = requests.post(url, json=payload)
    return response.json()

# Run backtest
result = run_backtest(
    strategy_code=open('my_strategy.js').read(),
    symbols=['AAPL', 'GOOGL', 'MSFT'],
    start_date='2023-01-01',
    end_date='2023-12-31'
)

# Analyze results
print(f"Total Return: {result['metrics']['totalReturn']:.2f}%")
print(f"Sharpe Ratio: {result['metrics']['sharpeRatio']:.2f}")
print(f"Max Drawdown: {result['metrics']['maxDrawdown']:.2f}%")

# Plot equity curve
equity_df = pd.DataFrame(result['equity'])
equity_df['date'] = pd.to_datetime(equity_df['date'])
equity_df.set_index('date')['value'].plot(title='Equity Curve')
plt.show()
```

### Node.js Integration
```javascript
const axios = require('axios');

class BacktestClient {
  constructor(baseUrl) {
    this.baseUrl = baseUrl;
  }
  
  async runBacktest(strategy, config) {
    try {
      const response = await axios.post(`${this.baseUrl}/api/backtest/run`, {
        strategy: strategy,
        ...config
      });
      
      return response.data;
    } catch (error) {
      throw new Error(`Backtest failed: ${error.response?.data?.error || error.message}`);
    }
  }
  
  async getSymbols(search = '') {
    const response = await axios.get(`${this.baseUrl}/api/backtest/symbols`, {
      params: { search }
    });
    return response.data.symbols;
  }
}

// Usage
const client = new BacktestClient('https://your-api.com');

const result = await client.runBacktest(`
  // Your strategy code here
  for (const symbol of ['AAPL', 'MSFT']) {
    if (data[symbol] && !getPosition(symbol)) {
      const price = data[symbol].close;
      buy(symbol, Math.floor(cash / price / 2), price);
    }
  }
`, {
  symbols: ['AAPL', 'MSFT'],
  startDate: '2023-01-01',
  endDate: '2023-12-31'
});

console.log('Backtest Results:', result.metrics);
```

## 🔒 Security & Limits

- **Sandboxed Execution**: Strategy code runs in isolated context
- **Resource Limits**: CPU and memory limits prevent abuse
- **Rate Limiting**: API calls are rate-limited per user
- **Input Validation**: All inputs are validated and sanitized
- **Timeout Protection**: Long-running strategies are terminated

## 🚀 Deployment

### Local Development
```bash
cd webapp/lambda
npm install
npm start
```

### Production Deployment
```bash
# AWS Lambda deployment
npm run package
aws lambda update-function-code --function-name backtest-api --zip-file fileb://function.zip

# Or use serverless framework
serverless deploy
```

## 🧪 Testing

```bash
# Run API tests
node test-backtest-api.js

# Run unit tests
npm test

# Load test with custom scenarios
npm run load-test
```

## 📚 Resources

- **API Documentation**: See `BACKTEST_API.md`
- **Postman Collection**: Import `Backtesting_API.postman_collection.json`
- **Strategy Examples**: Check `/examples` directory
- **Performance Benchmarks**: See `/benchmarks` directory

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

- **Documentation**: Full API docs and examples
- **Issue Tracking**: GitHub issues for bugs and features
- **Community**: Discord server for discussions
- **Professional Support**: Available for enterprise users

---

**Built for professional traders and quantitative researchers who demand institutional-grade backtesting capabilities.**
