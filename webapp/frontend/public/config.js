// This file is dynamically generated during deployment
// See .github/workflows/deploy-webapp.yml lines 782-800
// Local development: use VITE_API_URL environment variable instead
window.__CONFIG__ = window.__CONFIG__ || {
  API_URL: 'http://localhost:3001', // Default for local development
  ENVIRONMENT: 'development',
  VERSION: 'dev',
  BUILD_TIME: new Date().toISOString(),
  COGNITO: {
    USER_POOL_ID: '',
    CLIENT_ID: '',
    REGION: 'us-east-1',
    DOMAIN: '',
    REDIRECT_SIGN_IN: window.location.origin,
    REDIRECT_SIGN_OUT: window.location.origin
  }
};
console.log('Development config loaded:', window.__CONFIG__);
