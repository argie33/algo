# Simple Alpaca WebSocket Setup

## Quick Start - Just WebSocket to Alpaca

This is a simple, direct WebSocket connection to Alpaca for live stock data. No complex AWS infrastructure needed.

### 1. Get Your Alpaca API Keys

1. Sign up at [alpaca.markets](https://alpaca.markets)
2. Go to your dashboard and get your API key and secret
3. Choose your data feed:
   - `iex` = Free real-time data
   - `sip` = Premium data (paid subscription)

### 2. Set Environment Variables

Create a `.env` file in `/webapp/frontend/`:

```bash
# Copy the example file
cp .env.example .env

# Edit with your credentials
REACT_APP_ALPACA_API_KEY=your_actual_api_key
REACT_APP_ALPACA_API_SECRET=your_actual_secret
REACT_APP_ALPACA_DATA_FEED=iex
```

### 3. Add to Your React App

```jsx
// In your main App.jsx or wherever you want the data
import SimpleAlpacaData from './components/SimpleAlpacaData';

function App() {
  return (
    <div>
      <SimpleAlpacaData />
    </div>
  );
}
```

### 4. That's It!

The component will:
- Connect directly to Alpaca WebSocket API
- Let you subscribe to quotes, trades, and bars
- Show real-time data in a table
- Handle reconnections automatically

## Features

### Quick Subscribe Buttons
- Big Tech Quotes (AAPL, MSFT, GOOGL, AMZN)
- Growth Stocks Trades (TSLA, NVDA, META) 
- ETF Bars (SPY, QQQ, IWM)

### Manual Subscribe
- Enter any symbol (e.g., AAPL)
- Choose data type: Quotes, Trades, or Bars
- Real-time updates in the table

### Data Types

**Quotes**: Real-time bid/ask prices
```json
{
  "symbol": "AAPL",
  "bid": 150.25,
  "ask": 150.27,
  "bidSize": 100,
  "askSize": 200
}
```

**Trades**: Live trade executions
```json
{
  "symbol": "AAPL", 
  "price": 150.26,
  "size": 100,
  "conditions": ["@"]
}
```

**Bars**: OHLCV data
```json
{
  "symbol": "AAPL",
  "open": 150.00,
  "high": 150.50, 
  "low": 149.75,
  "close": 150.25,
  "volume": 1000000
}
```

## Usage Examples

```javascript
import simpleAlpacaWebSocket from './services/simpleAlpacaWebSocket';

// Connect
simpleAlpacaWebSocket.connect();

// Subscribe to quotes
simpleAlpacaWebSocket.subscribeToQuotes(['AAPL', 'TSLA']);

// Subscribe to trades  
simpleAlpacaWebSocket.subscribeToTrades(['MSFT']);

// Subscribe to bars
simpleAlpacaWebSocket.subscribeToBars(['SPY']);

// Listen for data
simpleAlpacaWebSocket.on('data', ({ type, data }) => {
  console.log(`${type} data for ${data.symbol}:`, data);
});

// Get latest data
const appleQuote = simpleAlpacaWebSocket.getLatestData('AAPL', 'quote');
```

## No AWS Required

This setup:
- ✅ Connects directly to Alpaca WebSocket API
- ✅ Uses your API key for authentication
- ✅ No AWS infrastructure needed
- ✅ No complex deployment
- ✅ Just add to your React app

## Files Created

- `webapp/frontend/src/services/simpleAlpacaWebSocket.js` - WebSocket service
- `webapp/frontend/src/components/SimpleAlpacaData.jsx` - React component
- `webapp/frontend/.env.example` - Environment variables template

## Next Steps

1. Set your API keys in `.env`
2. Add `<SimpleAlpacaData />` to your React app
3. Connect and start subscribing to symbols
4. See real-time data flowing in!

## Troubleshooting

**Not connecting?**
- Check your API keys are correct
- Make sure you're using the right data feed (iex vs sip)
- Check browser console for errors

**No data coming in?**
- Make sure you're subscribed to symbols
- Check if symbols are valid (use uppercase)
- Verify your Alpaca account has data permissions

**Want more features?**
- Add charts and graphs
- Store historical data
- Add alerts and notifications
- Implement trading functionality (requires additional setup)