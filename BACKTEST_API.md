# Backtesting API Documentation

## Overview

The Backtesting API provides programmatic access to run quantitative trading strategies against historical market data. It includes a comprehensive backtesting engine with professional-grade metrics and risk management features.

## Base URL

```
/api/backtest
```

## Endpoints

### 1. Run Backtest

**POST** `/api/backtest/run`

Execute a backtesting strategy against historical data.

#### Request Body

```json
{
  "strategy": "string",     // JavaScript strategy code
  "config": {               // Configuration options
    "initialCapital": 100000,
    "commission": 0.001,    // 0.1% commission
    "slippage": 0.001,      // 0.1% slippage
    "maxPositions": 10
  },
  "symbols": ["AAPL", "GOOGL", "MSFT"],
  "startDate": "2023-01-01",
  "endDate": "2023-12-31"
}
```

#### Strategy Code Context

Your strategy code has access to the following context:

- `data`: Object containing current market data for each symbol
- `cash`: Available cash balance
- `positions`: Map of current positions
- `buy(symbol, quantity, price, stopLoss?, takeProfit?)`: Buy function
- `sell(symbol, quantity, price)`: Sell function
- `sellAll(prices)`: Sell all positions
- `getPosition(symbol)`: Get current position for symbol
- `log(message)`: Logging function

#### Example Strategy Code

```javascript
// Simple Buy and Hold Strategy
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

#### Response

```json
{
  "success": true,
  "config": {
    "initialCapital": 100000,
    "commission": 0.001,
    "slippage": 0.001,
    "symbols": ["AAPL", "GOOGL", "MSFT"],
    "startDate": "2023-01-01",
    "endDate": "2023-12-31"
  },
  "metrics": {
    "totalReturn": 15.45,
    "annualizedReturn": 12.3,
    "volatility": 18.7,
    "sharpeRatio": 0.85,
    "maxDrawdown": 8.2,
    "winRate": 65.4,
    "profitFactor": 1.8,
    "totalTrades": 156,
    "winningTrades": 102,
    "losingTrades": 54,
    "grossProfit": 45000,
    "grossLoss": 25000,
    "finalValue": 115450,
    "startValue": 100000
  },
  "equity": [
    {"date": "2023-01-01", "value": 100000, "cash": 100000, "positions": 0},
    {"date": "2023-01-02", "value": 101250, "cash": 5000, "positions": 3}
  ],
  "trades": [
    {
      "date": "2023-01-02",
      "symbol": "AAPL",
      "action": "BUY",
      "quantity": 100,
      "price": 150.25,
      "commission": 15.03,
      "slippage": 15.03
    }
  ],
  "finalPositions": [
    {
      "symbol": "AAPL",
      "quantity": 100,
      "avgPrice": 150.25,
      "entryDate": "2023-01-02"
    }
  ]
}
```

### 2. Get Available Symbols

**GET** `/api/backtest/symbols`

Get list of available symbols for backtesting.

#### Query Parameters

- `search` (optional): Search term to filter symbols
- `limit` (optional): Maximum number of results (default: 100)

#### Response

```json
{
  "symbols": [
    {"symbol": "AAPL", "short_name": "Apple Inc."},
    {"symbol": "GOOGL", "short_name": "Alphabet Inc."}
  ]
}
```

### 3. Get Strategy Templates

**GET** `/api/backtest/templates`

Get pre-built strategy templates.

#### Response

```json
{
  "templates": [
    {
      "id": "buy_and_hold",
      "name": "Buy and Hold",
      "description": "Simple buy and hold strategy",
      "code": "// Strategy code here..."
    }
  ]
}
```

### 4. Validate Strategy Code

**POST** `/api/backtest/validate`

Validate strategy code syntax before running backtest.

#### Request Body

```json
{
  "strategy": "console.log('test');"
}
```

#### Response

```json
{
  "valid": true,
  "message": "Strategy code is valid"
}
```

Or if invalid:

```json
{
  "valid": false,
  "error": "SyntaxError: Unexpected token",
  "type": "syntax_error"
}
```

## Performance Metrics Explained

- **Total Return**: Total percentage return over the backtest period
- **Annualized Return**: Annualized percentage return
- **Volatility**: Annualized standard deviation of returns
- **Sharpe Ratio**: Risk-adjusted return metric (return - risk-free rate) / volatility
- **Max Drawdown**: Maximum peak-to-trough decline in portfolio value
- **Win Rate**: Percentage of profitable trades
- **Profit Factor**: Ratio of gross profits to gross losses
- **Total Trades**: Total number of completed trades

## Error Handling

The API returns appropriate HTTP status codes:

- `200`: Success
- `400`: Bad Request (invalid input)
- `500`: Internal Server Error

Error responses include:

```json
{
  "error": "Description of the error",
  "details": "Additional error details (in development mode)"
}
```

## Rate Limits

- Maximum 10 concurrent backtests per user
- Strategy code execution timeout: 30 seconds per day
- Maximum 1000 symbols per backtest

## Usage Examples

### Python Example

```python
import requests
import json

def run_backtest():
    url = "https://your-api-domain.com/api/backtest/run"
    
    strategy = '''
    // Moving Average Strategy
    const symbols = ['AAPL', 'GOOGL'];
    
    for (const symbol of symbols) {
        if (data[symbol]) {
            const price = data[symbol].close;
            const position = getPosition(symbol);
            
            if (!position) {
                const quantity = Math.floor(cash / (price * 2));
                if (quantity > 0) {
                    buy(symbol, quantity, price);
                }
            }
        }
    }
    '''
    
    payload = {
        "strategy": strategy,
        "config": {
            "initialCapital": 100000,
            "commission": 0.001
        },
        "symbols": ["AAPL", "GOOGL"],
        "startDate": "2023-01-01",
        "endDate": "2023-12-31"
    }
    
    response = requests.post(url, json=payload)
    
    if response.status_code == 200:
        result = response.json()
        print(f"Total Return: {result['metrics']['totalReturn']:.2f}%")
        print(f"Sharpe Ratio: {result['metrics']['sharpeRatio']:.2f}")
    else:
        print(f"Error: {response.json()}")

run_backtest()
```

### JavaScript/Node.js Example

```javascript
const axios = require('axios');

async function runBacktest() {
    const strategy = `
        // RSI Strategy
        const symbols = ['AAPL', 'MSFT'];
        
        for (const symbol of symbols) {
            if (data[symbol]) {
                const price = data[symbol].close;
                // Strategy logic here...
            }
        }
    `;
    
    try {
        const response = await axios.post('https://your-api-domain.com/api/backtest/run', {
            strategy,
            config: { initialCapital: 100000 },
            symbols: ['AAPL', 'MSFT'],
            startDate: '2023-01-01',
            endDate: '2023-12-31'
        });
        
        console.log('Backtest Results:', response.data.metrics);
    } catch (error) {
        console.error('Error:', error.response?.data || error.message);
    }
}

runBacktest();
```

## Best Practices

1. **Strategy Development**: Start with simple strategies and gradually add complexity
2. **Risk Management**: Always include proper position sizing and risk controls
3. **Data Quality**: Ensure you understand the data limitations and adjust accordingly
4. **Overfitting**: Use out-of-sample testing to validate strategy robustness
5. **Transaction Costs**: Include realistic commission and slippage estimates
6. **Market Regime**: Test strategies across different market conditions

## Support

For technical support and questions about the Backtesting API, please contact the development team or refer to the main API documentation.
