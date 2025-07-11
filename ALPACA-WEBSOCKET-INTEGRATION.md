# Alpaca WebSocket Integration Guide

## Overview

This document provides a comprehensive guide for integrating the Alpaca WebSocket real-time data capability into your application. The system is designed to be super user-friendly, flexible, and HFT-ready.

## Architecture

### Components

1. **AWS API Gateway WebSocket** - Real-time WebSocket endpoint
2. **Lambda Functions** - Message processing and routing
3. **DynamoDB Tables** - Connection and subscription management
4. **ElastiCache Redis** - High-performance data caching
5. **Kinesis Data Streams** - HFT data ingestion pipeline
6. **React Dashboard** - User-friendly subscription management

### Data Flow

```
Alpaca WebSocket API → Lambda Connector → DynamoDB/Redis → API Gateway → React Client
```

## Quick Start

### 1. Deploy Infrastructure

```bash
# Deploy the CloudFormation stack
aws cloudformation deploy \
  --stack-name alpaca-websocket-stack \
  --template-file template-alpaca-websocket.yml \
  --parameter-overrides \
    AlpacaApiKey="your-api-key" \
    AlpacaApiSecret="your-secret" \
    AlpacaDataFeed="iex" \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM
```

### 2. Deploy Lambda Function

```bash
cd lambda
./deploy-lambda.sh
```

### 3. Integrate Frontend

```javascript
import alpacaWebSocketService from './services/alpacaWebSocketService';
import AlpacaDataDashboard from './components/AlpacaDataDashboard';

// In your React component
function App() {
  return (
    <div>
      <AlpacaDataDashboard />
    </div>
  );
}
```

## WebSocket Service API

### Connection Management

```javascript
// Connect to WebSocket
await alpacaWebSocketService.connect();

// Disconnect
alpacaWebSocketService.disconnect();

// Check connection status
const status = alpacaWebSocketService.getConnectionStatus();
```

### Subscription Management

```javascript
// Subscribe to quotes
alpacaWebSocketService.subscribeToQuotes(['AAPL', 'TSLA']);

// Subscribe to trades
alpacaWebSocketService.subscribeToTrades(['MSFT', 'GOOGL']);

// Subscribe to bars
alpacaWebSocketService.subscribeToBars(['SPY', 'QQQ'], '5Min');

// Subscribe to news
alpacaWebSocketService.subscribeToNews(['AAPL']);

// Subscribe to crypto
alpacaWebSocketService.subscribeToCrypto(['BTCUSD', 'ETHUSD']);
```

### Event Handling

```javascript
// Market data events
alpacaWebSocketService.on('marketData', (data) => {
  console.log('Market data:', data);
});

// Specific data type events
alpacaWebSocketService.on('marketData:quotes', (data) => {
  console.log('Quote:', data);
});

// Connection events
alpacaWebSocketService.on('connected', () => {
  console.log('Connected to Alpaca WebSocket');
});

alpacaWebSocketService.on('disconnected', () => {
  console.log('Disconnected from Alpaca WebSocket');
});
```

## Data Types

### Quotes
```javascript
{
  symbol: 'AAPL',
  bid: 150.25,
  ask: 150.27,
  bid_size: 100,
  ask_size: 200,
  timestamp: 1634567890000
}
```

### Trades
```javascript
{
  symbol: 'AAPL',
  price: 150.26,
  size: 100,
  timestamp: 1634567890000,
  conditions: ['@'],
  exchange: 'NASDAQ'
}
```

### Bars
```javascript
{
  symbol: 'AAPL',
  open: 150.00,
  high: 150.50,
  low: 149.75,
  close: 150.25,
  volume: 1000000,
  timestamp: 1634567890000
}
```

### News
```javascript
{
  id: 'news-123',
  headline: 'Apple Reports Strong Q3 Earnings',
  summary: 'Apple exceeded expectations...',
  symbols: ['AAPL'],
  created_at: '2023-10-01T10:00:00Z'
}
```

### Crypto
```javascript
{
  symbol: 'BTCUSD',
  price: 45000.00,
  size: 0.5,
  timestamp: 1634567890000
}
```

## Dashboard Features

### Connection Management
- Real-time connection status
- Auto-reconnect toggle
- Connection metrics

### Subscription Management
- Quick subscription buttons for common assets
- Custom symbol subscription
- Data type selection (quotes, trades, bars, news, crypto)
- Frequency selection for bars
- Active subscriptions table

### Market Data Display
- Live market data table
- Real-time price updates
- Data type indicators
- Last update timestamps

### Performance Metrics
- Average latency
- Messages per second
- Connection uptime
- Data type specific counters

### Activity Log
- Real-time activity feed
- Color-coded message types
- Timestamp tracking
- Connection events

## Configuration

### Environment Variables

```bash
# WebSocket endpoint
REACT_APP_ALPACA_WS_URL=wss://your-websocket-api.execute-api.us-east-1.amazonaws.com/dev

# Auto-connect on startup
REACT_APP_AUTO_CONNECT_ALPACA=true
```

### Alpaca Credentials

Store in AWS Secrets Manager:
```json
{
  "api_key": "your-alpaca-api-key",
  "api_secret": "your-alpaca-secret",
  "data_feed": "iex",
  "base_url": "https://paper-api.alpaca.markets",
  "data_url": "https://data.alpaca.markets"
}
```

## Data Feeds

### IEX (Free)
- Real-time quotes and trades
- US equities and ETFs
- No subscription required

### SIP (Premium)
- Professional market data
- All US exchanges
- Requires subscription

### Crypto
- Real-time cryptocurrency data
- Major crypto pairs
- BTC, ETH, LTC, etc.

## HFT Optimization

### Low Latency Features
- Direct WebSocket connections
- Redis caching for sub-millisecond access
- Kinesis streams for parallel processing
- Optimized Lambda functions

### Performance Monitoring
- Real-time latency tracking
- Message throughput metrics
- Connection health monitoring
- Data freshness indicators

### Scalability
- Auto-scaling Lambda functions
- DynamoDB on-demand scaling
- Redis cluster support
- Multiple AZ deployment

## Error Handling

### Connection Errors
- Automatic reconnection
- Exponential backoff
- Max retry limits
- Error notifications

### Data Errors
- Message validation
- Malformed data handling
- Missing field defaults
- Error logging

### Subscription Errors
- Invalid symbol handling
- Rate limit management
- Permission errors
- Subscription conflicts

## Security

### Authentication
- AWS IAM roles
- Alpaca API key management
- Secrets Manager integration
- Connection-based access control

### Data Protection
- TLS/SSL encryption
- VPC endpoints
- Private subnets
- Security groups

## Monitoring

### CloudWatch Metrics
- Lambda execution metrics
- DynamoDB performance
- WebSocket connections
- Error rates

### Custom Metrics
- Market data latency
- Subscription counts
- Connection health
- Data throughput

## Troubleshooting

### Common Issues

1. **Connection Failures**
   - Check Alpaca credentials
   - Verify WebSocket endpoint
   - Review IAM permissions

2. **No Data Received**
   - Confirm active subscriptions
   - Check symbol validity
   - Verify data feed permissions

3. **High Latency**
   - Monitor Redis performance
   - Check Lambda cold starts
   - Review network connectivity

### Debug Mode

Enable debug logging:
```javascript
// In browser console
localStorage.setItem('alpaca-debug', 'true');
```

## Support

For issues or questions:
1. Check the activity log in the dashboard
2. Review CloudWatch logs
3. Verify Alpaca account status
4. Check AWS service health

## Next Steps

### HFT Enhancements
1. Add more data feeds (Level 2, Options)
2. Implement order routing
3. Add risk management
4. Create backtesting framework

### UI Improvements
1. Add charts and visualizations
2. Create watchlists
3. Add alerts and notifications
4. Mobile responsiveness

### Performance Optimizations
1. Implement data compression
2. Add request batching
3. Optimize Lambda memory
4. Use CloudFront for static assets