# WebSocket Live Data API

This document describes the WebSocket-based live data API implementation for real-time market data feeds.

## Overview

The WebSocket API provides real-time market data, options data, and other financial information with built-in data validation, automatic reconnection, and comprehensive monitoring capabilities.

## Architecture

### Server Components

1. **WebSocket Server** (`websocket_server.py`)
   - Handles client connections and message routing
   - Generates realistic market data simulation
   - Provides data validation and quality control
   - Supports multiple data feeds (market data, options, etc.)

2. **Data Simulator** (`MarketDataSimulator`)
   - Generates realistic market data using random walk with mean reversion
   - Calculates options pricing using simplified Black-Scholes
   - Provides Greeks calculations (Delta, Gamma, Theta, Vega, Rho)
   - Simulates market volatility and trading volumes

3. **Data Validator** (`DataValidator`)
   - Validates incoming market data for accuracy
   - Checks data types, ranges, and logical consistency
   - Prevents bad data from propagating to clients

### Client Components

1. **WebSocket Service** (`websocketService.js`)
   - Manages WebSocket connections with auto-reconnection
   - Handles subscription management
   - Provides data caching and validation
   - Implements heartbeat/ping-pong for connection health

2. **Live Data Monitor** (`LiveDataMonitor.jsx`)
   - React component for monitoring live data feeds
   - Displays connection status and statistics
   - Provides subscription management interface
   - Shows real-time market data in tables and charts

## Features

### Real-time Data Feeds
- **Market Data**: Price, bid/ask, volume, change
- **Options Data**: Full options chain with Greeks
- **Sector Analysis**: Sector-level flow and sentiment
- **Data Quality Metrics**: Latency, accuracy, validation

### Connection Management
- **Auto Reconnection**: Exponential backoff on connection loss
- **Heartbeat Monitoring**: Ping/pong to detect dead connections
- **Message Queuing**: Queues messages during disconnection
- **Connection Statistics**: Detailed metrics and monitoring

### Data Validation
- **Structure Validation**: Ensures all required fields are present
- **Range Validation**: Checks for reasonable price and volume ranges
- **Consistency Checks**: Validates bid/ask spreads and option pricing
- **Error Tracking**: Counts and reports validation errors

## API Reference

### Connection

```javascript
// Connect to WebSocket server
await websocketService.connect();

// Check connection status
const status = websocketService.getConnectionStatus();
// Returns: 'CONNECTING' | 'CONNECTED' | 'CLOSING' | 'DISCONNECTED'
```

### Subscriptions

```javascript
// Subscribe to market data for symbols
websocketService.subscribeMarketData(['AAPL', 'MSFT', 'GOOGL']);

// Subscribe to options data for a symbol
websocketService.subscribeOptionsData('AAPL');

// Unsubscribe from a feed
websocketService.unsubscribe('market_data');
```

### Event Handling

```javascript
// Listen for market data updates
websocketService.on('marketData', (data) => {
  console.log('Market data:', data);
  // { symbol, price, bid, ask, volume, timestamp, change, change_percent }
});

// Listen for options data updates
websocketService.on('optionsData', ({ symbol, data }) => {
  console.log('Options data for', symbol, ':', data);
  // Array of options with strike, expiry, type, bid, ask, greeks, etc.
});

// Listen for connection events
websocketService.on('connected', () => console.log('Connected'));
websocketService.on('disconnected', () => console.log('Disconnected'));
websocketService.on('error', (error) => console.error('Error:', error));
```

### Data Access

```javascript
// Get cached market data
const appleData = websocketService.getMarketData('AAPL');

// Get all cached market data
const allData = websocketService.getAllMarketData();

// Check if data is stale
const isStale = websocketService.isDataStale('market', 'AAPL', 60000); // 1 minute
```

## Message Protocol

### Client → Server Messages

#### Subscribe to Market Data
```json
{
  "type": "subscribe",
  "channel": "market_data",
  "symbols": ["AAPL", "MSFT", "GOOGL"]
}
```

#### Subscribe to Options Data
```json
{
  "type": "subscribe",
  "channel": "options_data",
  "symbol": "AAPL"
}
```

#### Unsubscribe
```json
{
  "type": "unsubscribe",
  "channel": "market_data"
}
```

#### Ping (Heartbeat)
```json
{
  "type": "ping",
  "timestamp": 1640995200000
}
```

### Server → Client Messages

#### Market Data Update
```json
{
  "type": "market_data",
  "data": {
    "symbol": "AAPL",
    "price": 150.25,
    "bid": 150.20,
    "ask": 150.30,
    "volume": 1234567,
    "timestamp": 1640995200.123,
    "change": 2.50,
    "change_percent": 1.69
  }
}
```

#### Options Data Update
```json
{
  "type": "options_data",
  "symbol": "AAPL",
  "data": [
    {
      "symbol": "AAPL",
      "strike": 150.0,
      "expiry": "2024-02-16",
      "type": "CALL",
      "bid": 5.20,
      "ask": 5.30,
      "last": 5.25,
      "volume": 1500,
      "open_interest": 12000,
      "implied_volatility": 0.285,
      "delta": 0.523,
      "gamma": 0.0143,
      "theta": -0.087,
      "vega": 0.234,
      "timestamp": 1640995200.123
    }
  ]
}
```

#### Subscription Confirmation
```json
{
  "type": "subscribed",
  "channel": "market_data",
  "symbols": ["AAPL", "MSFT"]
}
```

#### Pong (Heartbeat Response)
```json
{
  "type": "pong",
  "timestamp": 1640995200000
}
```

#### Error
```json
{
  "type": "error",
  "message": "Invalid symbol: INVALID"
}
```

## Setup and Deployment

### Development Setup

1. **Install Python Dependencies**
   ```bash
   cd /home/stocks/algo/webapp/api
   pip install -r requirements.txt
   ```

2. **Start WebSocket Server**
   ```bash
   python start_websocket.py --host 0.0.0.0 --port 8765 --log-level INFO
   ```

3. **Configure Frontend**
   ```bash
   # Set WebSocket URL in environment
   export REACT_APP_WS_URL=ws://localhost:8765
   
   # Or add to .env file
   echo "REACT_APP_WS_URL=ws://localhost:8765" >> .env
   ```

### Production Deployment

1. **Docker Deployment**
   ```dockerfile
   FROM python:3.9-slim
   WORKDIR /app
   COPY requirements.txt .
   RUN pip install -r requirements.txt
   COPY websocket_server.py start_websocket.py ./
   EXPOSE 8765
   CMD ["python", "start_websocket.py", "--host", "0.0.0.0", "--port", "8765"]
   ```

2. **Nginx WebSocket Proxy**
   ```nginx
   location /ws {
       proxy_pass http://localhost:8765;
       proxy_http_version 1.1;
       proxy_set_header Upgrade $http_upgrade;
       proxy_set_header Connection "Upgrade";
       proxy_set_header Host $host;
       proxy_cache_bypass $http_upgrade;
   }
   ```

3. **Environment Variables**
   - `REACT_APP_WS_URL`: WebSocket server URL
   - `REACT_APP_AUTO_CONNECT_WS`: Auto-connect on load (default: true)

## Data Sources Integration

### Real Market Data Integration

To connect to real market data providers, replace the simulator with actual data feeds:

```python
class AlpacaDataFeed(MarketDataSimulator):
    def __init__(self, api_key, secret_key):
        self.alpaca = tradeapi.REST(api_key, secret_key, base_url='https://paper-api.alpaca.markets')
    
    def get_real_market_data(self, symbol):
        # Fetch from Alpaca API
        quote = self.alpaca.get_latest_quote(symbol)
        return MarketData(
            symbol=symbol,
            price=quote.bid_price,
            bid=quote.bid_price,
            ask=quote.ask_price,
            # ... etc
        )
```

### Supported Data Providers
- **Alpaca Markets**: Free real-time quotes
- **Alpha Vantage**: Historical and real-time data
- **IEX Cloud**: Market data API
- **Yahoo Finance**: Free delayed quotes
- **Custom APIs**: Integration with proprietary feeds

## Monitoring and Debugging

### Connection Statistics
- Messages sent/received
- Connection uptime
- Reconnection attempts
- Data validation errors
- Cache hit rates

### Logging
- Server logs to `websocket_server.log`
- Client logs to browser console
- Error tracking and alerting
- Performance metrics

### Debug Tools
- Live Data Monitor component
- WebSocket connection tester
- Data validation dashboard
- Network latency monitoring

## Security Considerations

### Authentication
- JWT token validation for premium features
- Rate limiting per connection
- IP-based access control

### Data Protection
- No sensitive data in WebSocket messages
- Client-side data validation
- Secure WebSocket (WSS) in production

### Performance
- Message size limits (1MB default)
- Connection limits per IP
- Automatic cleanup of stale connections
- Memory usage monitoring

## Future Enhancements

1. **Enhanced Data Sources**
   - Level 2 order book data
   - News feed integration
   - Economic indicators
   - Social sentiment data

2. **Advanced Features**
   - Data replay functionality
   - Historical data streaming
   - Custom indicator calculations
   - Alert system integration

3. **Performance Optimizations**
   - Message compression
   - Delta updates only
   - Connection pooling
   - Edge caching

4. **Analytics Integration**
   - Real-time pattern detection
   - Anomaly detection
   - Market microstructure analysis
   - Performance analytics

## Troubleshooting

### Common Issues

1. **Connection Fails**
   - Check if server is running on correct port
   - Verify firewall settings
   - Check network connectivity

2. **No Data Received**
   - Ensure symbols are subscribed
   - Check server logs for errors
   - Verify data feed is active

3. **High Latency**
   - Check network conditions
   - Monitor server CPU usage
   - Reduce message frequency if needed

4. **Memory Leaks**
   - Clear cache periodically
   - Limit data history retention
   - Monitor browser memory usage

For additional support, check the server logs and client console for detailed error messages.