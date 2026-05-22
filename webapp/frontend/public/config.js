// Runtime configuration - Auto-detect based on hostname
window.__CONFIG__ = {
  "API_URL": 'https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com',
  "USER_POOL_ID": window.location.hostname === 'localhost' ? 'us-east-1_DUMMY' : 'us-east-1_XJpLb9SKX',
  "USER_POOL_CLIENT_ID": window.location.hostname === 'localhost' ? 'dummy-client-id' : '6smb0vrcidd9kvhju2kn2a3qrl',
  "USER_POOL_DOMAIN": window.location.hostname === 'localhost' ? 'dummy-domain' : 'stocks-trading-dev-626216981288.auth.626216981288.amazoncognito.com',
  "BUILD_TIME": "2026-05-21T14:10:00.000Z",
  "VERSION": "1.0.1",
  "ENVIRONMENT": window.location.hostname === 'localhost' ? 'development' : 'production'
};
