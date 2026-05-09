import { useEffect, useState, useCallback } from 'react';

/**
 * Hook to subscribe to live price updates via WebSocket.
 * Usage: const prices = useLivePrice(['QQQ', 'SPY']);
 */
export function useLivePrice(symbols = []) {
  const [prices, setPrices] = useState({});
  const [connected, setConnected] = useState(false);
  const [ws, setWs] = useState(null);

  useEffect(() => {
    if (!symbols || symbols.length === 0) return;

    // Connect to local WebSocket server
    const wsUrl = `ws://${window.location.hostname}:8765`;
    const websocket = new WebSocket(wsUrl);

    websocket.onopen = () => {
      console.log('[LivePrice] Connected');
      setConnected(true);

      // Subscribe to symbols
      websocket.send(JSON.stringify({
        action: 'subscribe',
        symbols: symbols
      }));
    };

    websocket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.type === 'price_update') {
          setPrices(prev => ({
            ...prev,
            [data.symbol]: {
              price: data.price,
              timestamp: data.timestamp,
            }
          }));
        }
      } catch (e) {
        console.error('[LivePrice] Parse error:', e);
      }
    };

    websocket.onerror = (error) => {
      console.error('[LivePrice] Error:', error);
      setConnected(false);
    };

    websocket.onclose = () => {
      console.log('[LivePrice] Disconnected');
      setConnected(false);
    };

    setWs(websocket);

    return () => {
      if (websocket.readyState === WebSocket.OPEN) {
        websocket.close();
      }
    };
  }, [symbols.join(',')]);

  const unsubscribe = useCallback((symbolsToRemove) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        action: 'unsubscribe',
        symbols: symbolsToRemove
      }));
    }
  }, [ws]);

  return {
    prices,
    connected,
    unsubscribe
  };
}

/**
 * Component to display live price ticker.
 */
export function LivePriceTicker({ symbol, currentPrice, entryPrice }) {
  const { prices, connected } = useLivePrice([symbol]);
  const livePrice = prices[symbol]?.price || currentPrice;
  const priceChange = livePrice - entryPrice;
  const priceChangePercent = (priceChange / entryPrice) * 100;

  return (
    <div style={{
      padding: '12px',
      background: 'var(--bg-secondary)',
      borderRadius: '4px',
      border: `1px solid ${priceChange > 0 ? '#10b981' : '#ef4444'}`
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{symbol}</div>
          <div style={{ fontSize: '20px', fontWeight: 'bold', color: priceChange > 0 ? '#10b981' : '#ef4444' }}>
            ${livePrice.toFixed(2)}
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: '14px', color: priceChange > 0 ? '#10b981' : '#ef4444' }}>
            {priceChange > 0 ? '+' : ''}{priceChange.toFixed(2)}
          </div>
          <div style={{ fontSize: '12px', color: priceChange > 0 ? '#10b981' : '#ef4444' }}>
            ({priceChangePercent > 0 ? '+' : ''}{priceChangePercent.toFixed(2)}%)
          </div>
        </div>
      </div>
      {!connected && (
        <div style={{ fontSize: '10px', color: '#f59e0b', marginTop: '6px' }}>
          ⚠ Live prices unavailable (using cached)
        </div>
      )}
    </div>
  );
}
