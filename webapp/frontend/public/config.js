// Runtime configuration - Environment-aware (works for both local and AWS)
// This file detects the environment and configures accordingly

(function() {
  // Auto-detect environment and API configuration
  const getConfig = () => {
    const hostname = window.location.hostname;

    // Local development - use relative paths, let Vite proxy handle /api requests
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return {
        API_URL: '', // Empty for local dev - use Vite proxy
        ENVIRONMENT: 'development',
        BUILD_TIME: new Date().toISOString(),
        VERSION: '1.0.0-dev',
        USER_POOL_ID: '',
        USER_POOL_CLIENT_ID: '',
        USER_POOL_DOMAIN: ''
      };
    }

    // AWS CloudFront/Production - use absolute API URL
    if (hostname.includes('cloudfront.net') || hostname.includes('d5j1h4wzrkvw7')) {
      return {
        API_URL: 'https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com',
        ENVIRONMENT: 'production',
        BUILD_TIME: new Date().toISOString(),
        VERSION: '1.0.0',
        USER_POOL_ID: 'us-east-1_XJpLb9SKX',
        USER_POOL_CLIENT_ID: '6smb0vrcidd9kvhju2kn2a3qrl',
        USER_POOL_DOMAIN: 'stocks-trading-dev-626216981288.auth.626216981288.amazoncognito.com'
      };
    }

    // Unknown environment - fallback to relative paths
    return {
      API_URL: '',
      ENVIRONMENT: 'development',
      BUILD_TIME: new Date().toISOString(),
      VERSION: '1.0.0-dev',
      USER_POOL_ID: '',
      USER_POOL_CLIENT_ID: '',
      USER_POOL_DOMAIN: ''
    };
  };

  window.__CONFIG__ = getConfig();
  console.log('[CONFIG] Environment:', window.__CONFIG__.ENVIRONMENT, 'API:', window.__CONFIG__.API_URL || '(relative paths - Vite proxy)');
})();
