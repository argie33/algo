const express = require("express");

const { query } = require("../utils/database");
const { authenticateToken } = require("../middleware/auth");
const {
  storeApiKey,
  getApiKey,
  validateApiKey,
  deleteApiKey,
  listProviders,
  getHealthStatus,
  getDecryptedApiKey: _getDecryptedApiKey,
} = require("../utils/apiKeyService");

const router = express.Router();

// Apply authentication middleware to all settings routes
router.use(authenticateToken);

// Root settings route - returns available endpoints
router.get("/", async (req, res) => {
  res.success({
    message: "Settings API - Ready",
    timestamp: new Date().toISOString(),
    status: "operational",
    endpoints: [
      "/api-keys - Get all API keys",
      "/api-keys/:provider - Get specific provider API key",
      "POST /api-keys - Create new API key", 
      "PUT /api-keys/:provider - Update API key",
      "DELETE /api-keys/:provider - Delete API key"
    ]
  });
});

// Get all API keys for authenticated user
router.get("/api-keys", async (req, res) => {
  try {
    const providers = await listProviders(req.token);

    res.success({
      apiKeys: providers,
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

// Get specific API key configuration (masked for security)
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

    res.success({
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

// Store new API key configuration
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
      keyId: apiKey.trim(),
      secret: apiSecret?.trim(),
      isSandbox: Boolean(isSandbox),
      description: description?.trim(),
      createdAt: new Date().toISOString(),
    };

    const result = await storeApiKey(req.token, provider, apiKeyData);

    res.success({
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

// Update API key configuration
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
      keyId: apiKey?.trim() || existingData.keyId,
      secret: apiSecret?.trim() || existingData.secret,
      isSandbox:
        isSandbox !== undefined ? Boolean(isSandbox) : existingData.isSandbox,
      description: description?.trim() || existingData.description,
      updatedAt: new Date().toISOString(),
    };

    const result = await storeApiKey(req.token, provider, updatedData);

    res.success({
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

// Delete API key configuration
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

    res.success({
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

// Validate API key configuration with optional connection test
router.post("/api-keys/:provider/validate", async (req, res) => {
  const { provider } = req.params;
  const { testConnection = false } = req.body;

  try {
    const validation = await validateApiKey(
      req.token,
      provider,
      testConnection
    );

    res.success({
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

// Test connection to all configured providers
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

    res.success({
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

// Get API key service health status
router.get("/health", async (req, res) => {
  try {
    const health = getHealthStatus();

    res.success({
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

// Create user_profiles table if it doesn't exist
router.post("/init-database", async (req, res) => {
  try {
    // Create the user_profiles table with all required columns
    const createTableSql = `
      CREATE TABLE IF NOT EXISTS user_profiles (
        user_id VARCHAR(255) PRIMARY KEY,
        onboarding_completed BOOLEAN DEFAULT FALSE,
        preferences JSONB DEFAULT '{
          "theme": "light", 
          "notifications": true, 
          "defaultView": "dashboard"
        }'::jsonb,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
      );
      
      CREATE INDEX IF NOT EXISTS idx_user_profiles_user_id ON user_profiles(user_id);
    `;

    await query(createTableSql);

    res.success({
      message: "Database initialized successfully",
      table: "user_profiles",
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error initializing database:", error);
    res.status(500).json({
      success: false,
      error: "Failed to initialize database",
      message: error.message,
    });
  }
});

// Get user profile and settings
router.get("/profile", async (req, res) => {
  try {
    const user = req.user;

    // Add null checking for API key service availability
    let providers = [];
    try {
      providers = await listProviders(req.token);
    } catch (apiKeyError) {
      console.warn("API key service unavailable for profile lookup:", apiKeyError.message);
      // Continue with empty providers array - graceful degradation
    }

    // Handle token expiration time safely
    let tokenExpiresAt = null;
    if (user.tokenExpirationTime && typeof user.tokenExpirationTime === 'number') {
      try {
        tokenExpiresAt = new Date(user.tokenExpirationTime * 1000).toISOString();
      } catch (dateError) {
        console.warn("Invalid token expiration time:", user.tokenExpirationTime);
        tokenExpiresAt = null;
      }
    }

    res.success({
      profile: {
        id: user.sub,
        email: user.email,
        username: user.username,
        role: user.role,
        groups: user.groups,
        sessionId: user.sessionId,
        tokenExpiresAt: tokenExpiresAt,
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

// Get onboarding status
router.get("/onboarding-status", async (req, res) => {
  try {
    const userId = req.user.sub;
    const providers = await listProviders(req.token);

    // Check if user has completed onboarding
    const userResult = await query(
      "SELECT onboarding_completed FROM user_profiles WHERE user_id = $1",
      [userId]
    );

    const hasApiKeys = providers.length > 0;
    
    // Handle database not available case
    let onboardingCompleted = false;
    if (userResult && userResult.rows && userResult.rows[0]) {
      onboardingCompleted = userResult.rows[0].onboarding_completed || false;
    } else {
      // Database not available, default to false for development mode
      console.log("Database not available - using default onboarding status");
      onboardingCompleted = false;
    }

    res.success({
      onboarding: {
        completed: onboardingCompleted,
        hasApiKeys: hasApiKeys,
        configuredProviders: providers.length,
        nextStep: !hasApiKeys ? "configure-api-keys" : "complete",
        fallback: !userResult ? true : false
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error getting onboarding status:", error);
    res.status(500).json({
      success: false,
      error: "Failed to get onboarding status",
      message: error.message,
    });
  }
});

// Mark onboarding as complete
router.post("/onboarding-complete", async (req, res) => {
  try {
    const userId = req.user.sub;

    await query(
      `INSERT INTO user_profiles (user_id, onboarding_completed, created_at)
       VALUES ($1, true, NOW())
       ON CONFLICT (user_id) 
       DO UPDATE SET onboarding_completed = true, updated_at = NOW()`,
      [userId]
    );

    res.success({
      message: "Onboarding completed successfully",
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error completing onboarding:", error);
    res.status(500).json({
      success: false,
      error: "Failed to complete onboarding",
      message: error.message,
    });
  }
});

// Get user preferences
router.get("/preferences", async (req, res) => {
  try {
    const userId = req.user.sub;

    const result = await query(
      `SELECT preferences FROM user_profiles WHERE user_id = $1`,
      [userId]
    );

    const preferences = result.rows[0]?.preferences || {
      theme: "light",
      notifications: true,
      defaultView: "dashboard",
    };

    res.success({
      preferences: preferences,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error getting preferences:", error);
    res.status(500).json({
      success: false,
      error: "Failed to get preferences",
      message: error.message,
    });
  }
});

// Update user preferences
router.post("/preferences", async (req, res) => {
  try {
    const userId = req.user.sub;
    const { preferences } = req.body;

    if (!preferences || typeof preferences !== "object") {
      return res.status(400).json({
        success: false,
        error: "Valid preferences object is required",
      });
    }

    await query(
      `INSERT INTO user_profiles (user_id, preferences, created_at)
       VALUES ($1, $2, NOW())
       ON CONFLICT (user_id) 
       DO UPDATE SET preferences = $2, updated_at = NOW()`,
      [userId, JSON.stringify(preferences)]
    );

    res.success({
      message: "Preferences updated successfully",
      preferences: preferences,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error updating preferences:", error);
    res.status(500).json({
      success: false,
      error: "Failed to update preferences",
      message: error.message,
    });
  }
});

module.exports = router;
