// Runtime configuration placeholder — overwritten at deploy time by GitHub Actions.
// In production, this file is replaced with dynamically resolved values from AWS.
// For local dev, use VITE_API_URL env var or the Vite proxy (empty = relative paths).
window.__CONFIG__ = {
  "API_URL": "",
  "USER_POOL_ID": "",
  "USER_POOL_CLIENT_ID": "",
  "USER_POOL_DOMAIN": "",
  "ENVIRONMENT": "development",
  "AWS_REGION": "us-east-1"
};
