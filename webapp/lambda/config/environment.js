/**
 * Centralized environment variable configuration
 * Single source of truth for all required and optional environment variables
 */

const requiredInProduction = {
  DB_HOST: "PostgreSQL hostname",
  DB_PORT: "PostgreSQL port",
  DB_USER: "PostgreSQL username",
  DB_PASSWORD: "PostgreSQL password",
  DB_NAME: "PostgreSQL database name",
  COGNITO_CLIENT_ID: "AWS Cognito Client ID",
  JWT_SECRET: "JWT signing secret",
};

const optional = {
  AWS_REGION: { default: "us-east-1" },
  WEBAPP_AWS_REGION: { default: "us-east-1" },
  FRED_API_KEY: { default: "" },
  ALPACA_API_KEY: { default: "" },
  ALPACA_API_SECRET: { default: "" },
  ALPACA_PAPER_TRADING: { default: "true" },
  VITE_API_URL: { default: "" },
  FRONTEND_URL: { default: "" },
  NODE_ENV: { default: "development" },
  PORT: { default: 3001 },
  LOG_LEVEL: { default: "info" },
  DB_INIT_TIMEOUT: { default: 30000 },
  DB_QUERY_TIMEOUT: { default: 30000 },
  API_REQUEST_TIMEOUT: { default: 30000 },
};

/**
 * Validate environment on startup
 */
function validateEnvironment() {
  const env = process.env.NODE_ENV || "development";
  const missing = [];

  if (env === "production") {
    for (const [key, description] of Object.entries(requiredInProduction)) {
      if (!process.env[key]) {
        missing.push(`${key} (${description})`);
      }
    }

    if (missing.length > 0) {
      console.error("❌ CRITICAL: Missing required environment variables in production:");
      missing.forEach(v => console.error(`   - ${v}`));
      throw new Error("Missing required environment variables");
    }
  }
}

/**
 * Get environment config
 */
const config = {
  environment: process.env.NODE_ENV || "development",
  isProduction: process.env.NODE_ENV === "production",
  isDevelopment: process.env.NODE_ENV !== "production",

  database: {
    host: process.env.DB_HOST || "localhost",
    port: parseInt(process.env.DB_PORT || 5432),
    user: process.env.DB_USER || "stocks",
    password: process.env.DB_PASSWORD || "",
    database: process.env.DB_NAME || "stocks",
    secretArn: process.env.DB_SECRET_ARN,
    queryTimeout: parseInt(process.env.DB_QUERY_TIMEOUT || 30000),
    initTimeout: parseInt(process.env.DB_INIT_TIMEOUT || 30000),
  },

  aws: {
    region: process.env.AWS_REGION || process.env.WEBAPP_AWS_REGION || "us-east-1",
  },

  auth: {
    cognitoClientId: process.env.COGNITO_CLIENT_ID,
    jwtSecret: process.env.JWT_SECRET,
  },

  api: {
    port: parseInt(process.env.PORT || 3001),
    requestTimeout: parseInt(process.env.API_REQUEST_TIMEOUT || 30000),
    frontendUrl: process.env.FRONTEND_URL || process.env.VITE_API_URL,
  },

  logging: {
    level: process.env.LOG_LEVEL || "info",
  },

  // Data source APIs
  dataApis: {
    fred: process.env.FRED_API_KEY,
    alpaca: {
      apiKey: process.env.ALPACA_API_KEY,
      apiSecret: process.env.ALPACA_API_SECRET,
      paperTrading: process.env.ALPACA_PAPER_TRADING === "true",
    },
  },
};

// Validate on load
validateEnvironment();

module.exports = config;
