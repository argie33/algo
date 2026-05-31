/**
 * Amplify Configuration Unit Tests
 * Tests for AWS Amplify configuration helper functions
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// Mock Amplify
const mockAmplify = {
  configure: vi.fn(),
};

vi.mock("aws-amplify", () => ({
  Amplify: mockAmplify,
}));

// Mock console methods
const consoleMock = {
  log: vi.fn(),
  warn: vi.fn(),
  error: vi.fn(),
};

global.console = consoleMock;

// Mock window object
const windowMock = {
  __CONFIG__: undefined,
  location: {
    origin: "http://localhost:5173",
  },
};

global.window = windowMock;

describe("Amplify Configuration", () => {
  let originalImportMetaEnv;

  beforeEach(async () => {
    vi.clearAllMocks();

    originalImportMetaEnv = globalThis.import?.meta?.env;
    vi.stubGlobal("import.meta", {
      env: {
        VITE_COGNITO_USER_POOL_ID: "",
        VITE_COGNITO_CLIENT_ID: "",
        VITE_AWS_REGION: "us-east-1",
      },
    });

    windowMock.__CONFIG__ = undefined;
    vi.resetModules();
    await import("../../../config/amplify.js");
  });

  afterEach(() => {
    if (originalImportMetaEnv) {
      vi.stubGlobal("import.meta", { env: originalImportMetaEnv });
    }
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  describe("getRuntimeConfig", () => {
    it("should return window.__CONFIG__ when available", async () => {
      windowMock.__CONFIG__ = {
        USER_POOL_ID: "runtime-pool-id",
        USER_POOL_CLIENT_ID: "runtime-client-id",
      };

      vi.resetModules();
      const { default: getAmplifyConfig } = await import("../../../config/amplify.js");
      const config = getAmplifyConfig();

      expect(config.Auth.Cognito.userPoolId).toBe("runtime-pool-id");
      expect(config.Auth.Cognito.userPoolClientId).toBe("runtime-client-id");
    });

    it("should return empty object when window.__CONFIG__ is not available", async () => {
      windowMock.__CONFIG__ = undefined;

      vi.resetModules();
      const { default: getAmplifyConfig } = await import("../../../config/amplify.js");
      const config = getAmplifyConfig();

      expect(config.Auth.Cognito.userPoolId).toBe("us-east-1_DUMMY");
      expect(config.Auth.Cognito.userPoolClientId).toBe("dummy-client-id");
    });

    it("should handle window being undefined", async () => {
      const originalWindow = global.window;
      delete global.window;

      try {
        vi.resetModules();
        const { default: getAmplifyConfig } = await import("../../../config/amplify.js");
        const config = getAmplifyConfig();

        expect(config).toBeDefined();
        expect(config.Auth.Cognito.userPoolId).toBe("us-east-1_DUMMY");
      } finally {
        global.window = originalWindow;
      }
    });
  });

  describe("isCognitoConfigured", () => {
    it("should return true when valid runtime config is provided", async () => {
      windowMock.__CONFIG__ = {
        USER_POOL_ID: "us-east-1_ValidPoolId",
        USER_POOL_CLIENT_ID: "valid-client-id",
      };

      vi.resetModules();
      const { isCognitoConfigured } = await import("../../../config/amplify.js");

      expect(isCognitoConfigured()).toBe(true);
    });

    it("should return true when valid environment variables are provided", async () => {
      windowMock.__CONFIG__ = {
        USER_POOL_ID: "us-east-1_ValidPoolId",
        USER_POOL_CLIENT_ID: "valid-client-id",
      };

      vi.resetModules();
      const { isCognitoConfigured } = await import("../../../config/amplify.js");

      expect(isCognitoConfigured()).toBe(true);
    });

    it("should return false when using dummy values", async () => {
      windowMock.__CONFIG__ = {
        USER_POOL_ID: "us-east-1_DUMMY",
        USER_POOL_CLIENT_ID: "dummy-client-id",
      };

      vi.resetModules();
      const { isCognitoConfigured } = await import("../../../config/amplify.js");

      expect(isCognitoConfigured()).toBe(false);
    });

    it("should return false when values are empty strings", async () => {
      windowMock.__CONFIG__ = {
        USER_POOL_ID: "",
        USER_POOL_CLIENT_ID: "",
      };

      vi.resetModules();
      const { isCognitoConfigured } = await import("../../../config/amplify.js");

      expect(isCognitoConfigured()).toBe(false);
    });

    it("should return false when values are missing", async () => {
      windowMock.__CONFIG__ = {};

      vi.resetModules();
      const { isCognitoConfigured } = await import("../../../config/amplify.js");

      expect(isCognitoConfigured()).toBe(false);
    });

    it("should prioritize runtime config over environment variables", async () => {
      windowMock.__CONFIG__ = {
        USER_POOL_ID: "us-east-1_RuntimePoolId",
        USER_POOL_CLIENT_ID: "runtime-client-id",
      };

      vi.stubGlobal("import.meta", {
        env: {
          VITE_COGNITO_USER_POOL_ID: "us-east-1_DUMMY",
          VITE_COGNITO_CLIENT_ID: "dummy-client-id",
        },
      });

      vi.resetModules();
      const { isCognitoConfigured } = await import("../../../config/amplify.js");

      expect(isCognitoConfigured()).toBe(true);
    });
  });

  describe("getAmplifyConfig", () => {
    it("should generate config with runtime pool ID", async () => {
      windowMock.__CONFIG__ = {
        USER_POOL_ID: "us-east-1_RuntimePool",
        USER_POOL_CLIENT_ID: "runtime-client",
      };

      vi.resetModules();
      const { default: getAmplifyConfig } = await import("../../../config/amplify.js");
      const config = getAmplifyConfig();

      expect(config.Auth.Cognito.userPoolId).toBe("us-east-1_RuntimePool");
      expect(config.Auth.Cognito.userPoolClientId).toBe("runtime-client");
    });

    it("should generate config with env pool ID", async () => {
      windowMock.__CONFIG__ = {
        USER_POOL_ID: "us-east-1_EnvPool",
        USER_POOL_CLIENT_ID: "env-client",
      };

      vi.resetModules();
      const { default: getAmplifyConfig } = await import("../../../config/amplify.js");
      const config = getAmplifyConfig();

      expect(config.Auth.Cognito.userPoolId).toBe("us-east-1_EnvPool");
      expect(config.Auth.Cognito.userPoolClientId).toBe("env-client");
    });

    it("should use dummy values when no config is provided", async () => {
      windowMock.__CONFIG__ = undefined;

      vi.stubGlobal("import.meta", {
        env: {
          VITE_AWS_REGION: "us-east-1",
        },
      });

      vi.resetModules();
      const { default: getAmplifyConfig } = await import("../../../config/amplify.js");
      const config = getAmplifyConfig();

      expect(config.Auth.Cognito.userPoolId).toBe("us-east-1_DUMMY");
      expect(config.Auth.Cognito.userPoolClientId).toBe("dummy-client-id");
    });

    it("should include correct Cognito Auth config structure", async () => {
      vi.resetModules();
      const { default: getAmplifyConfig } = await import("../../../config/amplify.js");
      const config = getAmplifyConfig();

      expect(config.Auth).toBeDefined();
      expect(config.Auth.Cognito).toBeDefined();
      expect(config.Auth.Cognito.signUpVerificationMethod).toBe("code");
      expect(config.Auth.Cognito.userPoolId).toBeDefined();
      expect(config.Auth.Cognito.userPoolClientId).toBeDefined();
    });

    it("should derive region from user pool ID", async () => {
      windowMock.__CONFIG__ = {
        USER_POOL_ID: "eu-west-1_TestPool",
        USER_POOL_CLIENT_ID: "test-client",
      };

      vi.resetModules();
      const { default: getAmplifyConfig } = await import("../../../config/amplify.js");
      const config = getAmplifyConfig();

      expect(config.Auth.Cognito.region).toBe("eu-west-1");
    });
  });

  describe("configureAmplify", () => {
    it("should call Amplify.configure with valid config", async () => {
      windowMock.__CONFIG__ = {
        USER_POOL_ID: "us-east-1_ValidPool",
        USER_POOL_CLIENT_ID: "valid-client",
      };

      vi.resetModules();
      const { configureAmplify } = await import("../../../config/amplify.js");

      configureAmplify();

      expect(mockAmplify.configure).toHaveBeenCalledWith(
        expect.objectContaining({
          Auth: expect.objectContaining({
            Cognito: expect.objectContaining({
              userPoolId: "us-east-1_ValidPool",
              userPoolClientId: "valid-client",
            }),
          }),
        })
      );
    });

    it("should log warning when Cognito is not configured", async () => {
      windowMock.__CONFIG__ = undefined;

      vi.resetModules();
      const { configureAmplify } = await import("../../../config/amplify.js");

      configureAmplify();

      expect(consoleMock.warn).toHaveBeenCalledWith(
        expect.stringContaining("fallback")
      );
    });

    it("should handle configuration errors gracefully", async () => {
      mockAmplify.configure.mockImplementationOnce(() => {
        throw new Error("Configuration failed");
      });

      vi.resetModules();
      const { configureAmplify } = await import("../../../config/amplify.js");

      expect(() => configureAmplify()).not.toThrow();

      expect(consoleMock.error).toHaveBeenCalledWith(
        "Failed to configure Amplify:",
        expect.any(Error)
      );
    });

    it("should not reconfigure if pool ID has not changed", async () => {
      windowMock.__CONFIG__ = {
        USER_POOL_ID: "us-east-1_StablePool",
        USER_POOL_CLIENT_ID: "stable-client",
      };

      vi.resetModules();
      const { configureAmplify } = await import("../../../config/amplify.js");

      configureAmplify();
      configureAmplify();

      // Should only configure once (deduplication)
      expect(mockAmplify.configure).toHaveBeenCalledTimes(1);
    });
  });

  describe("Module Exports", () => {
    it("should export all required functions", async () => {
      vi.resetModules();
      const amplifyModule = await import("../../../config/amplify.js");

      expect(amplifyModule.isCognitoConfigured).toBeDefined();
      expect(amplifyModule.getAmplifyConfig).toBeDefined();
      expect(amplifyModule.configureAmplify).toBeDefined();
      expect(amplifyModule.default).toBeDefined();
      expect(amplifyModule.default).toBe(amplifyModule.getAmplifyConfig);
    });
  });
});
