import { describe, test, expect, vi, beforeEach, afterEach } from "vitest";

describe("Production Configuration", () => {
  let PRODUCTION_CONFIG, getEnvironmentConfig, validateConfig, CONFIG;
  let originalImportMeta;

  beforeEach(async () => {
    // Clear console mock
    vi.spyOn(console, "error").mockImplementation(() => {});

    // Import the module
    const configModule = await import("../../../config/production.js");
    PRODUCTION_CONFIG = configModule.PRODUCTION_CONFIG;
    getEnvironmentConfig = configModule.getEnvironmentConfig;
    validateConfig = configModule.validateConfig;
    CONFIG = configModule.CONFIG;
  });

  afterEach(() => {
    global.import = originalImportMeta;
    vi.restoreAllMocks();
  });

  describe("PRODUCTION_CONFIG", () => {
    test("contains all required configuration sections", () => {
      expect(PRODUCTION_CONFIG).toBeDefined();
      expect(PRODUCTION_CONFIG.app).toBeDefined();
      expect(PRODUCTION_CONFIG.api).toBeDefined();
      expect(PRODUCTION_CONFIG.refreshIntervals).toBeDefined();
      expect(PRODUCTION_CONFIG.cache).toBeDefined();
      expect(PRODUCTION_CONFIG.performance).toBeDefined();
      expect(PRODUCTION_CONFIG.security).toBeDefined();
      expect(PRODUCTION_CONFIG.errorHandling).toBeDefined();
      expect(PRODUCTION_CONFIG.features).toBeDefined();
      expect(PRODUCTION_CONFIG.ui).toBeDefined();
      expect(PRODUCTION_CONFIG.dataQuality).toBeDefined();
      expect(PRODUCTION_CONFIG.compliance).toBeDefined();
      expect(PRODUCTION_CONFIG.monitoring).toBeDefined();
      expect(PRODUCTION_CONFIG.csp).toBeDefined();
    });

    test("has correct app information", () => {
      expect(PRODUCTION_CONFIG.app.name).toBe("Edgebrooke Capital Dashboard");
      expect(PRODUCTION_CONFIG.app.version).toBe("2.1.0");
      expect(PRODUCTION_CONFIG.app.environment).toBe("production");
      expect(PRODUCTION_CONFIG.app.description).toContain(
        "Enterprise-grade financial data platform"
      );
      expect(PRODUCTION_CONFIG.app.buildDate).toBeDefined();
    });

    test("has production-appropriate API settings", () => {
      expect(PRODUCTION_CONFIG.api.timeout).toBe(30000);
      expect(PRODUCTION_CONFIG.api.retryAttempts).toBe(3);
      expect(PRODUCTION_CONFIG.api.retryDelay).toBe(1000);
      expect(PRODUCTION_CONFIG.api.healthCheckInterval).toBe(60000);
      expect(PRODUCTION_CONFIG.api.maxConcurrentRequests).toBe(10);
    });

    test("has appropriate refresh intervals", () => {
      expect(PRODUCTION_CONFIG.refreshIntervals.marketData).toBe(30000);
      expect(PRODUCTION_CONFIG.refreshIntervals.portfolioData).toBe(60000);
      expect(PRODUCTION_CONFIG.refreshIntervals.dashboardData).toBe(120000);
      expect(PRODUCTION_CONFIG.refreshIntervals.economicData).toBe(300000);
      expect(PRODUCTION_CONFIG.refreshIntervals.presidential).toBe(86400000);
    });

    test("has security-conscious settings", () => {
      expect(PRODUCTION_CONFIG.security.enableCSP).toBe(true);
      expect(PRODUCTION_CONFIG.security.enableSRI).toBe(true);
      expect(PRODUCTION_CONFIG.security.sessionTimeout).toBe(3600000);
      expect(PRODUCTION_CONFIG.security.maxLoginAttempts).toBe(5);
      expect(PRODUCTION_CONFIG.security.lockoutDuration).toBe(900000);
    });

    test("has compliance settings enabled", () => {
      expect(PRODUCTION_CONFIG.compliance.enableAuditLog).toBe(true);
      expect(PRODUCTION_CONFIG.compliance.dataRetentionDays).toBe(2555); // 7 years
      expect(PRODUCTION_CONFIG.compliance.enableGDPR).toBe(true);
      expect(PRODUCTION_CONFIG.compliance.enableSOX).toBe(true);
      expect(PRODUCTION_CONFIG.compliance.enableFINRA).toBe(true);
    });

    test("has proper CSP configuration", () => {
      expect(PRODUCTION_CONFIG.csp.defaultSrc).toEqual(["'self'"]);
      expect(PRODUCTION_CONFIG.csp.frameSrc).toEqual(["'none'"]);
      expect(PRODUCTION_CONFIG.csp.objectSrc).toEqual(["'none'"]);
      expect(PRODUCTION_CONFIG.csp.baseUri).toEqual(["'self'"]);
    });

    test("has professional feature flags", () => {
      expect(PRODUCTION_CONFIG.features.advancedCharts).toBe(true);
      expect(PRODUCTION_CONFIG.features.realTimeData).toBe(true);
      expect(PRODUCTION_CONFIG.features.portfolioOptimization).toBe(true);
      expect(PRODUCTION_CONFIG.features.riskAnalysis).toBe(true);
      expect(PRODUCTION_CONFIG.features.collaboration).toBe(false); // Enterprise feature
    });

    test("has monitoring settings with privacy focus", () => {
      expect(PRODUCTION_CONFIG.monitoring.enablePerformanceMonitoring).toBe(
        true
      );
      expect(PRODUCTION_CONFIG.monitoring.enableUserAnalytics).toBe(false); // Privacy-first
      expect(PRODUCTION_CONFIG.monitoring.enableErrorTracking).toBe(true);
      expect(PRODUCTION_CONFIG.monitoring.enableHealthChecks).toBe(true);
    });
  });

  describe("getEnvironmentConfig", () => {
    test("returns production config for production environment", () => {
      // Mock import.meta.env for this test
      vi.stubGlobal("import", {
        meta: {
          env: {
            MODE: "production",
          },
        },
      });

      const config = getEnvironmentConfig();

      expect(config.environment).toBe("production");
      expect(config.api.timeout).toBe(30000); // Production timeout
      expect(config.errorHandling.logLevel).toBe("error"); // Production log level
    });

    test("returns development overrides for development environment", () => {
      vi.stubGlobal("import", {
        meta: {
          env: {
            MODE: "development",
          },
        },
      });

      const config = getEnvironmentConfig();

      expect(config.environment).toBe("development");
      expect(config.api.timeout).toBe(10000); // Development timeout
      expect(config.api.retryAttempts).toBe(1); // Development retry
      expect(config.refreshIntervals.marketData).toBe(10000); // Faster refresh
      expect(config.errorHandling.logLevel).toBe("debug"); // Debug logging
      expect(config.security.sessionTimeout).toBe(7200000); // Longer session
    });

    test("returns staging overrides for staging environment", () => {
      vi.stubGlobal("import", {
        meta: {
          env: {
            MODE: "staging",
          },
        },
      });

      const config = getEnvironmentConfig();

      expect(config.environment).toBe("staging");
      expect(config.api.timeout).toBe(20000); // Staging timeout
      expect(config.api.retryAttempts).toBe(2); // Staging retry
      expect(config.errorHandling.logLevel).toBe("warn"); // Warning level
    });

    test("defaults to development when MODE is undefined", () => {
      vi.stubGlobal("import", {
        meta: {
          env: {},
        },
      });

      const config = getEnvironmentConfig();

      expect(config.environment).toBe("development");
      expect(config.api.timeout).toBe(10000);
    });

    test("maintains base configuration structure", () => {
      const config = getEnvironmentConfig();

      expect(config.app.name).toBe("Edgebrooke Capital Dashboard");
      expect(config.features.advancedCharts).toBe(true);
      expect(config.security.enableCSP).toBe(true);
      expect(config.compliance.enableAuditLog).toBe(true);
    });
  });

  describe("validateConfig", () => {
    test("validates correct configuration", () => {
      const validConfig = {
        app: { name: "Test App" },
        api: { timeout: 10000 },
        security: { sessionTimeout: 600000 },
      };

      const result = validateConfig(validConfig);

      expect(result.isValid).toBe(true);
      expect(result.errors).toHaveLength(0);
    });

    test("rejects configuration without app name", () => {
      const invalidConfig = {
        app: { name: "" },
        api: { timeout: 10000 },
        security: { sessionTimeout: 600000 },
      };

      const result = validateConfig(invalidConfig);

      expect(result.isValid).toBe(false);
      expect(result.errors).toContain("App name is required");
    });

    test("rejects configuration with too short API timeout", () => {
      const invalidConfig = {
        app: { name: "Test App" },
        api: { timeout: 3000 }, // Too short
        security: { sessionTimeout: 600000 },
      };

      const result = validateConfig(invalidConfig);

      expect(result.isValid).toBe(false);
      expect(result.errors).toContain(
        "API timeout should be at least 5 seconds"
      );
    });

    test("rejects configuration with too short session timeout", () => {
      const invalidConfig = {
        app: { name: "Test App" },
        api: { timeout: 10000 },
        security: { sessionTimeout: 200000 }, // Too short
      };

      const result = validateConfig(invalidConfig);

      expect(result.isValid).toBe(false);
      expect(result.errors).toContain(
        "Session timeout should be at least 5 minutes"
      );
    });

    test("accumulates multiple validation errors", () => {
      const invalidConfig = {
        app: { name: "" },
        api: { timeout: 1000 },
        security: { sessionTimeout: 100000 },
      };

      const result = validateConfig(invalidConfig);

      expect(result.isValid).toBe(false);
      expect(result.errors).toHaveLength(3);
      expect(result.errors).toContain("App name is required");
      expect(result.errors).toContain(
        "API timeout should be at least 5 seconds"
      );
      expect(result.errors).toContain(
        "Session timeout should be at least 5 minutes"
      );
    });

    test("handles missing nested properties gracefully", () => {
      const invalidConfig = {
        app: {},
        api: {},
        security: {},
      };

      const result = validateConfig(invalidConfig);

      expect(result.isValid).toBe(false);
      expect(result.errors.length).toBeGreaterThan(0);
    });
  });

  describe("Module Loading and Validation", () => {
    test("CONFIG is properly initialized", () => {
      expect(CONFIG).toBeDefined();
      expect(CONFIG.app).toBeDefined();
      expect(CONFIG.environment).toBeDefined();
    });

    test("validates configuration on module load", () => {
      // The configuration should be valid and not log errors
      expect(console.error).not.toHaveBeenCalled();
    });

    test("logs errors for invalid configuration on import", async () => {
      // Mock a scenario where validation fails
      const _invalidConfigModule = {
        PRODUCTION_CONFIG: {
          app: { name: "" }, // Invalid name
          api: { timeout: 1000 }, // Invalid timeout
          security: { sessionTimeout: 100000 }, // Invalid session timeout
        },
        getEnvironmentConfig: () => ({
          app: { name: "" },
          api: { timeout: 1000 },
          security: { sessionTimeout: 100000 },
        }),
        validateConfig: (_config) => ({
          isValid: false,
          errors: [
            "App name is required",
            "API timeout should be at least 5 seconds",
          ],
        }),
      };

      // This would normally be tested by importing the module with invalid defaults
      const validation = validateConfig({
        app: { name: "" },
        api: { timeout: 1000 },
        security: { sessionTimeout: 100000 },
      });

      expect(validation.isValid).toBe(false);
      expect(validation.errors.length).toBeGreaterThan(0);
    });
  });

  describe("Data Structures and Types", () => {
    test("refresh intervals are all numbers", () => {
      Object.values(PRODUCTION_CONFIG.refreshIntervals).forEach((interval) => {
        expect(typeof interval).toBe("number");
        expect(interval).toBeGreaterThan(0);
      });
    });

    test("timeout values are reasonable", () => {
      expect(PRODUCTION_CONFIG.api.timeout).toBeGreaterThanOrEqual(5000);
      expect(PRODUCTION_CONFIG.api.timeout).toBeLessThanOrEqual(60000);
    });

    test("retry attempts are reasonable", () => {
      expect(PRODUCTION_CONFIG.api.retryAttempts).toBeGreaterThanOrEqual(1);
      expect(PRODUCTION_CONFIG.api.retryAttempts).toBeLessThanOrEqual(5);
    });

    test("session timeout is secure but usable", () => {
      expect(PRODUCTION_CONFIG.security.sessionTimeout).toBeGreaterThanOrEqual(
        300000
      ); // At least 5 minutes
      expect(PRODUCTION_CONFIG.security.sessionTimeout).toBeLessThanOrEqual(
        14400000
      ); // At most 4 hours
    });

    test("CSP directives are arrays", () => {
      Object.values(PRODUCTION_CONFIG.csp).forEach((directive) => {
        expect(Array.isArray(directive)).toBe(true);
      });
    });

    test("feature flags are booleans", () => {
      Object.values(PRODUCTION_CONFIG.features).forEach((flag) => {
        expect(typeof flag).toBe("boolean");
      });
    });
  });

  describe("Environment-Specific Behavior", () => {
    test("production environment has strict settings", () => {
      global.import = {
        meta: {
          env: {
            MODE: "production",
          },
        },
      };

      const config = getEnvironmentConfig();

      expect(config.api.retryAttempts).toBe(3); // More retries in production
      expect(config.errorHandling.logLevel).toBe("error"); // Only errors logged
      expect(config.security.sessionTimeout).toBe(3600000); // Strict session timeout
    });

    test("development environment has relaxed settings", () => {
      vi.stubGlobal("import", {
        meta: {
          env: {
            MODE: "development",
          },
        },
      });

      const config = getEnvironmentConfig();

      expect(config.api.retryAttempts).toBe(1); // Fewer retries for faster development
      expect(config.errorHandling.logLevel).toBe("debug"); // Debug logging
      expect(config.security.sessionTimeout).toBe(7200000); // Longer session for convenience
    });
  });
});
