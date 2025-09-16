// Production configuration for Edgebrooke Capital Financial Dashboard
// This file contains production-ready settings for enterprise deployment

export const PRODUCTION_CONFIG = {
  // Application Information
  app: {
    name: "Edgebrooke Capital Dashboard",
    version: "2.1.0",
    environment: "production",
    buildDate: new Date().toISOString(),
    description:
      "Enterprise-grade financial data platform for professional investors",
  },

  // API Configuration
  api: {
    timeout: 30000, // 30 seconds for production
    retryAttempts: 3,
    retryDelay: 1000,
    healthCheckInterval: 60000, // 1 minute
    rateLimitRetryAfter: 5000, // 5 seconds
    maxConcurrentRequests: 10,
  },

  // Data Refresh Intervals (in milliseconds)
  refreshIntervals: {
    marketData: 30000, // 30 seconds
    portfolioData: 60000, // 1 minute
    dashboardData: 120000, // 2 minutes
    economicData: 300000, // 5 minutes
    earnings: 600000, // 10 minutes
    research: 900000, // 15 minutes
    presidential: 86400000, // 24 hours
    static: 3600000, // 1 hour
  },

  // Cache Configuration
  cache: {
    enabled: true,
    maxSize: 100, // Maximum cached items
    ttl: 300000, // 5 minutes default TTL
    staleWhileRevalidate: true,
  },

  // Performance Settings
  performance: {
    enableLazyLoading: true,
    chunkLoadTimeout: 30000,
    maxChartDataPoints: 1000,
    tablePageSize: 25,
    virtualScrollThreshold: 100,
  },

  // Security Settings
  security: {
    enableCSP: true,
    enableSRI: true,
    sessionTimeout: 3600000, // 1 hour
    tokenRefreshThreshold: 300000, // 5 minutes before expiry
    maxLoginAttempts: 5,
    lockoutDuration: 900000, // 15 minutes
  },

  // Error Handling
  errorHandling: {
    enableGlobalHandler: true,
    enableBoundaries: true,
    logLevel: "error",
    enableClientLogging: true,
    maxErrorReports: 10,
    errorReportingThreshold: 5,
  },

  // Feature Flags
  features: {
    advancedCharts: true,
    realTimeData: true,
    portfolioOptimization: true,
    riskAnalysis: true,
    presidentialCycle: true,
    marketResearch: true,
    darkMode: true,
    exportData: true,
    notifications: true,
    collaboration: false, // Enterprise feature
  },

  // UI/UX Settings
  ui: {
    theme: "professional",
    enableAnimations: true,
    loadingMinDuration: 500,
    debounceDelay: 300,
    defaultPageSize: 25,
    maxSelectOptions: 100,
  },

  // Data Quality Settings
  dataQuality: {
    enableValidation: true,
    staleDataThreshold: 300000, // 5 minutes
    missingDataPolicy: "show_placeholder",
    enableDataHealthCheck: true,
  },

  // Compliance Settings
  compliance: {
    enableAuditLog: true,
    dataRetentionDays: 2555, // 7 years
    enableGDPR: true,
    enableSOX: true,
    enableFINRA: true,
  },

  // Monitoring & Analytics
  monitoring: {
    enablePerformanceMonitoring: true,
    enableUserAnalytics: false, // Privacy-first approach
    enableErrorTracking: true,
    enableHealthChecks: true,
    metricsInterval: 60000, // 1 minute
  },

  // Content Security Policy
  csp: {
    defaultSrc: ["'self'"],
    scriptSrc: ["'self'", "'unsafe-inline'"],
    styleSrc: ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com"],
    fontSrc: ["'self'", "https://fonts.gstatic.com"],
    imgSrc: ["'self'", "data:", "https:"],
    connectSrc: ["'self'", "wss:", "https:"],
    frameSrc: ["'none'"],
    objectSrc: ["'none'"],
    baseUri: ["'self'"],
  },
};

// Environment-specific overrides
export const getEnvironmentConfig = () => {
  const env = import.meta.env.MODE || "development";

  const overrides = {
    development: {
      api: {
        timeout: 10000,
        retryAttempts: 1,
      },
      refreshIntervals: {
        marketData: 10000,
        portfolioData: 30000,
      },
      errorHandling: {
        logLevel: "debug",
      },
      security: {
        sessionTimeout: 7200000, // 2 hours for development
      },
    },

    staging: {
      api: {
        timeout: 20000,
        retryAttempts: 2,
      },
      errorHandling: {
        logLevel: "warn",
      },
    },

    production: {
      // Use defaults from PRODUCTION_CONFIG
    },
  };

  return {
    ...PRODUCTION_CONFIG,
    ...overrides[env],
    environment: env,
  };
};

// Validation functions
export const validateConfig = (config) => {
  const errors = [];

  if (!config.app.name) {
    errors.push("App name is required");
  }

  if (config.api.timeout < 5000) {
    errors.push("API timeout should be at least 5 seconds");
  }

  if (config.security.sessionTimeout < 300000) {
    errors.push("Session timeout should be at least 5 minutes");
  }

  return {
    isValid: (errors?.length || 0) === 0,
    errors,
  };
};

// Export the final configuration
export const CONFIG = getEnvironmentConfig();

// Validate configuration on import
const validation = validateConfig(CONFIG);
if (!validation.isValid) {
  console.error("Configuration validation failed:", validation.errors);
}

export default CONFIG;
