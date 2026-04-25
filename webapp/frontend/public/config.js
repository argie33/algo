// Runtime configuration - loads at startup
window.__CONFIG__ = {
  API_URL: "http://localhost:3001",
  ENVIRONMENT: "development",
  DEBUG: true,
  VERSION: "1.0.0"
};
console.log("✅ Config loaded - API URL:", window.__CONFIG__.API_URL);
