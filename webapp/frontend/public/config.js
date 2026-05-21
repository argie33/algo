// Runtime configuration - Environment-aware (works for both local and AWS)
// This file detects the environment and configures accordingly

(function() {
  // Auto-detect API URL based on hostname
  const getApiUrl = () => {
    const hostname = window.location.hostname;

    // Local development
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return 'http://localhost:3002';
    }

    // AWS CloudFront/CloudFlare (production)
    if (hostname.includes('cloudfront.net') || hostname.includes('d5j1h4wzrkvw7')) {
      return 'https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com';
    }

    // Fallback for unknown environments
    return window.location.origin;
  };

  window.__CONFIG__ = {
    "API_URL": getApiUrl(),
    "BUILD_TIME": "2026-05-21T12:42:00.000Z",
    "VERSION": "1.0.0",
    "ENVIRONMENT": window.location.hostname === 'localhost' ? 'development' : 'production',
    "USER_POOL_ID": "us-east-1_XJpLb9SKX",
    "USER_POOL_CLIENT_ID": "6smb0vrcidd9kvhju2kn2a3qrl",
    "USER_POOL_DOMAIN": "stocks-trading-dev-626216981288.auth.626216981288.amazoncognito.com"
  };

  console.log('[CONFIG] Environment detected:', window.__CONFIG__.ENVIRONMENT, 'API URL:', window.__CONFIG__.API_URL);
})();
