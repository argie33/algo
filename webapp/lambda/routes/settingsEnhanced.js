const express = require("express");
const {
  authenticateToken,
  requireRole,
  rateLimitByUser,
  logApiAccess,
} = require("../middleware/authEnhanced");
const {
  storeApiKey,
  getApiKey,
  validateApiKey,
  deleteApiKey,
  listProviders,
  getHealthStatus,
} = require("../utils/apiKeyService");

const router = express.Router();

// Apply enhanced authentication and logging to all routes
router.use(authenticateToken);
router.use(logApiAccess);
router.use(rateLimitByUser(50)); // 50 requests per minute per user

/**
 * Get all configured API providers for authenticated user
 */
router.get("/api-keys", async (req, res) => {
  try {
    const providers = await listProviders(req.token);

    res.json({
      success: true,
      providers: providers,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching API keys:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch API keys",
      message: error.message,
    });
  }
});

/**
 * Get specific API key configuration (masked for security)
 */
router.get("/api-keys/:provider", async (req, res) => {
  const { provider } = req.params;

  try {
    const apiKeyData = await getApiKey(req.token, provider);

    if (!apiKeyData) {
      return res.status(404).json({
        success: false,
        error: "API key not found",
        provider: provider,
      });
    }

    // Return masked data for security
    const maskedData = {
      provider: provider,
      configured: true,
      isSandbox: apiKeyData.isSandbox,
      description: apiKeyData.description,
      // Mask sensitive data
      apiKey: apiKeyData.apiKey
        ? `${apiKeyData.apiKey.substring(0, 4)}${"*".repeat(apiKeyData.apiKey.length - 4)}`
        : undefined,
      apiSecret: apiKeyData.apiSecret ? "***HIDDEN***" : undefined,
      timestamp: new Date().toISOString(),
    };

    res.json({
      success: true,
      apiKey: maskedData,
    });
  } catch (error) {
    console.error("Error fetching API key:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch API key",
      message: error.message,
    });
  }
});

/**
 * Store new API key configuration
 */
router.post("/api-keys", async (req, res) => {
  const {
    provider,
    apiKey,
    apiSecret,
    isSandbox = true,
    description,
  } = req.body;

  // Validation
  if (!provider || !apiKey) {
    return res.status(400).json({
      success: false,
      error: "Provider and API key are required",
      requiredFields: ["provider", "apiKey"],
    });
  }

  // Validate provider
  const supportedProviders = ["alpaca", "polygon", "finnhub", "alpha_vantage"];
  if (!supportedProviders.includes(provider)) {
    return res.status(400).json({
      success: false,
      error: "Unsupported provider",
      supportedProviders: supportedProviders,
    });
  }

  try {
    const apiKeyData = {
      apiKey: apiKey.trim(),
      apiSecret: apiSecret?.trim(),
      isSandbox: Boolean(isSandbox),
      description: description?.trim(),
      createdAt: new Date().toISOString(),
    };

    const result = await storeApiKey(req.token, provider, apiKeyData);

    res.json({
      success: true,
      message: `${provider} API key stored successfully`,
      result: {
        id: result.id,
        provider: result.provider,
        encrypted: result.encrypted,
        user: result.user,
      },
    });
  } catch (error) {
    console.error("Error storing API key:", error);

    if (error.message.includes("circuit breaker")) {
      return res.status(503).json({
        success: false,
        error: "Service temporarily unavailable",
        message:
          "API key service is experiencing issues. Please try again shortly.",
      });
    }

    res.status(500).json({
      success: false,
      error: "Failed to store API key",
      message: error.message,
    });
  }
});

/**
 * Update API key configuration
 */
router.put("/api-keys/:provider", async (req, res) => {
  const { provider } = req.params;
  const { apiKey, apiSecret, isSandbox, description } = req.body;

  try {
    // Get existing configuration
    const existingData = await getApiKey(req.token, provider);

    if (!existingData) {
      return res.status(404).json({
        success: false,
        error: "API key configuration not found",
        provider: provider,
      });
    }

    // Merge with new data
    const updatedData = {
      apiKey: apiKey?.trim() || existingData.apiKey,
      apiSecret: apiSecret?.trim() || existingData.apiSecret,
      isSandbox:
        isSandbox !== undefined ? Boolean(isSandbox) : existingData.isSandbox,
      description: description?.trim() || existingData.description,
      updatedAt: new Date().toISOString(),
    };

    const result = await storeApiKey(req.token, provider, updatedData);

    res.json({
      success: true,
      message: `${provider} API key updated successfully`,
      result: {
        id: result.id,
        provider: result.provider,
        encrypted: result.encrypted,
      },
    });
  } catch (error) {
    console.error("Error updating API key:", error);
    res.status(500).json({
      success: false,
      error: "Failed to update API key",
      message: error.message,
    });
  }
});

/**
 * Delete API key configuration
 */
router.delete("/api-keys/:provider", async (req, res) => {
  const { provider } = req.params;

  try {
    const result = await deleteApiKey(req.token, provider);

    if (!result.deleted) {
      return res.status(404).json({
        success: false,
        error: "API key not found",
        provider: provider,
      });
    }

    res.json({
      success: true,
      message: `${provider} API key deleted successfully`,
      provider: provider,
    });
  } catch (error) {
    console.error("Error deleting API key:", error);
    res.status(500).json({
      success: false,
      error: "Failed to delete API key",
      message: error.message,
    });
  }
});

/**
 * Validate API key configuration with optional connection test
 */
router.post("/api-keys/:provider/validate", async (req, res) => {
  const { provider } = req.params;
  const { testConnection = false } = req.body;

  try {
    const validation = await validateApiKey(
      req.token,
      provider,
      testConnection
    );

    res.json({
      success: true,
      validation: validation,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error validating API key:", error);
    res.status(500).json({
      success: false,
      error: "Failed to validate API key",
      message: error.message,
    });
  }
});

/**
 * Test connection to all configured providers
 */
router.post("/api-keys/test-all", async (req, res) => {
  try {
    const providers = await listProviders(req.token);
    const testResults = [];

    for (const provider of providers) {
      try {
        const validation = await validateApiKey(
          req.token,
          provider.provider,
          true
        );
        testResults.push({
          provider: provider.provider,
          ...validation,
        });
      } catch (error) {
        testResults.push({
          provider: provider.provider,
          valid: false,
          error: error.message,
        });
      }
    }

    res.json({
      success: true,
      testResults: testResults,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error testing API keys:", error);
    res.status(500).json({
      success: false,
      error: "Failed to test API keys",
      message: error.message,
    });
  }
});

/**
 * Get API key service health status
 */
router.get("/health", async (req, res) => {
  try {
    const health = getHealthStatus();

    res.json({
      success: true,
      health: health,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error getting health status:", error);
    res.status(500).json({
      success: false,
      error: "Failed to get health status",
      message: error.message,
    });
  }
});

/**
 * Get user profile and settings
 */
router.get("/profile", async (req, res) => {
  try {
    const user = req.user;
    const providers = await listProviders(req.token);

    res.json({
      success: true,
      profile: {
        id: user.sub,
        email: user.email,
        username: user.username,
        role: user.role,
        groups: user.groups,
        sessionId: user.sessionId,
        tokenExpiresAt: new Date(user.tokenExpirationTime * 1000).toISOString(),
      },
      settings: {
        configuredProviders: providers.length,
        providers: providers.map((p) => ({
          provider: p.provider,
          configured: p.configured,
          lastUsed: p.lastUsed,
        })),
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error getting profile:", error);
    res.status(500).json({
      success: false,
      error: "Failed to get profile",
      message: error.message,
    });
  }
});

/**
 * Admin-only endpoint to get service metrics
 */
router.get("/admin/metrics", requireRole(["admin"]), async (req, res) => {
  try {
    const health = getHealthStatus();

    // Add additional metrics for admin
    const metrics = {
      ...health,
      adminAccess: true,
      timestamp: new Date().toISOString(),
      environment: process.env.NODE_ENV || "development",
    };

    res.json({
      success: true,
      metrics: metrics,
    });
  } catch (error) {
    console.error("Error getting admin metrics:", error);
    res.status(500).json({
      success: false,
      error: "Failed to get admin metrics",
      message: error.message,
    });
  }
});

module.exports = router;
