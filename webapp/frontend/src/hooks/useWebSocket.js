import { useCallback, useRef, useEffect } from 'react';

export function useWebSocket(url, options = {}) {
  const webSocketRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);

  const onMessage = options.onMessage || (() => {});
  const onError = options.onError || (() => {});
  const onOpen = options.onOpen || (() => {});
  const onClose = options.onClose || (() => {});
  const autoReconnect = options.autoReconnect !== false;

  const connect = useCallback(() => {
    if (webSocketRef.current) {
      return;
    }

    try {
      webSocketRef.current = new WebSocket(url);

      webSocketRef.current.onopen = () => {
        onOpen();
      };

      webSocketRef.current.onmessage = (event) => {
        onMessage(event.data);
      };

      webSocketRef.current.onerror = (error) => {
        onError(error);
      };

      webSocketRef.current.onclose = () => {
        onClose();
        webSocketRef.current = null;

        if (autoReconnect) {
          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, 3000);
        }
      };
    } catch (error) {
      onError(error);
    }
  }, [url, onMessage, onError, onOpen, onClose, autoReconnect]);

  const disconnect = useCallback(() => {
    if (webSocketRef.current) {
      webSocketRef.current.close();
      webSocketRef.current = null;
    }
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
  }, []);

  const send = useCallback((data) => {
    if (webSocketRef.current && webSocketRef.current.readyState === WebSocket.OPEN) {
      webSocketRef.current.send(data);
    }
  }, []);

  useEffect(() => {
    connect();

    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

  return {
    send,
    disconnect,
    isConnected: webSocketRef.current?.readyState === WebSocket.OPEN,
  };
}
