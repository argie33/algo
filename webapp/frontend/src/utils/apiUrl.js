/**
 * Dynamic API URL resolver
 * Works in local, development, and production AWS environments
 */

export const getApiUrl = () => {
  // 1. Check runtime config (set by AWS deployment)
  if (typeof window !== 'undefined' && window.__CONFIG__?.API_URL) {
    return window.__CONFIG__.API_URL;
  }

  // 2. Check environment variables (set during build)
  if (import.meta.env?.VITE_API_URL) {
    return import.meta.env.VITE_API_URL;
  }

  // 3. Infer from current location (works in all environments)
  if (typeof window !== 'undefined') {
    const { hostname, origin, _port } = window.location;

    // Local development
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return 'http://localhost:3001';
    }

    // AWS or production - replace port with 3001
    return origin.replace(/:\d+$/, ':3001');
  }

  // Fallback (shouldn't reach here)
  return 'http://localhost:3001';
};

export const getWebSocketUrl = () => {
  const apiUrl = getApiUrl();
  return apiUrl
    .replace(/^https:/, 'wss:')
    .replace(/^http:/, 'ws:') + '/ws';
};
