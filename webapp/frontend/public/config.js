// LOCAL DEVELOPMENT ONLY — deploy-code.yml overwrites dist/config.js with the real
// production API URL after the Vite build, before the S3 upload. This file only
// affects local dev (served from public/ by Vite dev server).
window.__CONFIG__ = {
  "API_URL": "http://localhost:3001",
  "ENVIRONMENT": "development"
};
