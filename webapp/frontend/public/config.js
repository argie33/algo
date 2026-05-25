// Runtime configuration - Dynamic Environment Detection
// In development (localhost): empty API_URL to use Vite dev server proxy (/api → localhost:3001)
// In production: use AWS API Gateway URL
window.__CONFIG__ = {
  "API_URL": (typeof window !== 'undefined' && window.location.hostname === 'localhost')
    ? ""
    : "https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com",
  "USER_POOL_ID": "us-east-1_DUMMY",
  "USER_POOL_CLIENT_ID": "dummy-client-id",
  "USER_POOL_DOMAIN": "dummy-domain",
  "BUILD_TIME": "2026-05-24T12:46:33.624Z",
  "VERSION": "1.0.0-live",
  "ENVIRONMENT": window.location.hostname === 'localhost' ? "development" : "production"
};
