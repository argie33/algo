# Live Price WebSocket Setup

## Overview

The system includes real-time price streaming via WebSocket for live position P&L updates.

## Architecture

1. **Backend**: `algo_websocket_prices.py` 
   - Connects to Alpaca WebSocket API for live prices
   - Broadcasts prices to connected frontend clients
   - Runs on port 8765

2. **Frontend**: `hooks/useLivePrice.js`
   - React hook to subscribe to specific symbols
   - Auto-reconnects on disconnect
   - Falls back to cached prices if unavailable

## Setup

### 1. Install WebSocket Library

```bash
pip install websockets websocket-client
```

### 2. Start WebSocket Server

Option A: Standalone
```bash
python3 algo_websocket_prices.py
```

Option B: Background (systemd service)
```bash
[Unit]
Description=Algo WebSocket Price Stream
After=network.target

[Service]
Type=simple
User=stocks
WorkingDirectory=/path/to/algo
ExecStart=/usr/bin/python3 algo_websocket_prices.py
Restart=always

[Install]
WantedBy=multi-user.target
```

### 3. Use in React Components

```jsx
import { useLivePrice, LivePriceTicker } from '../hooks/useLivePrice';

function MyPosition() {
  const { prices } = useLivePrice(['QQQ', 'SPY']);
  
  return (
    <div>
      <LivePriceTicker symbol="QQQ" currentPrice={450.00} entryPrice={445.00} />
    </div>
  );
}
```

## Features

- ✅ Real-time price updates (sub-second latency)
- ✅ Auto-reconnect on disconnect
- ✅ Graceful fallback to cached prices
- ✅ Multi-symbol subscription
- ✅ Low bandwidth (JSON-based)

## Limitations

- Requires direct network access to Alpaca API
- Paper/live trading account API keys required
- Local network only (not exposed to internet)

## Troubleshooting

### WebSocket won't connect
- Check Alpaca credentials in `.env.local`
- Ensure port 8765 is not blocked
- Verify websockets library installed

### Prices not updating
- Check browser console for WebSocket errors
- Verify Alpaca connection (check logs in terminal)
- Market may be closed (prices only during market hours)

### High CPU usage
- Reduce number of subscribed symbols
- Adjust broadcast frequency in `send_price()`
