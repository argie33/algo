const {
  SecretsManagerClient,
  GetSecretValueCommand,
} = require("@aws-sdk/client-secrets-manager");
const { query } = require("./database");
const crypto = require("crypto");
const { CognitoJwtVerifier } = require("aws-jwt-verify");

/**
 * Unified API Key Service with JWT Integration
 * Combines resilient design with proper JWT validation and session management
 */
class ApiKeyService {
  constructor() {
    this.secretsManager = new SecretsManagerClient({
      region:
        process.env.WEBAPP_AWS_REGION || process.env.AWS_REGION || "us-east-1",
    });

    // Circuit breaker for API key operations
    this.circuitBreaker = {
      failures: 0,
      lastFailureTime: 0,
      state: "CLOSED", // CLOSED, OPEN, HALF_OPEN
      maxFailures: 5,
      timeout: 60000, // 1 minute
    };

    // JWT verification circuit breaker
    this.jwtCircuitBreaker = {
      failures: 0,
      lastFailureTime: 0,
      state: "CLOSED",
      maxFailures: 3,
      timeout: 30000, // 30 seconds
    };

    // Cache for encryption key and JWT verifier
    this.encryptionKey = null;
    this.jwtVerifier = null;
    this.keyCache = new Map();
    this.sessionCache = new Map();
    this.cacheTimeout = 300000; // 5 minutes

    // Initialize JWT verifier
    this.initializeJwtVerifier();
  }

  /**
   * Initialize JWT verifier with circuit breaker
   */
  async initializeJwtVerifier() {
    try {
      if (process.env.COGNITO_USER_POOL_ID && process.env.COGNITO_CLIENT_ID) {
        this.jwtVerifier = CognitoJwtVerifier.create({
          userPoolId: process.env.COGNITO_USER_POOL_ID,
          tokenUse: "access",
          clientId: process.env.COGNITO_CLIENT_ID,
        });
        console.log("JWT verifier initialized successfully");
      } else {
        console.warn(
          "Cognito environment variables not set - JWT verification disabled"
        );
      }
    } catch (error) {
      console.error("Failed to initialize JWT verifier:", error.message);
      this.recordJwtFailure(error);
    }
  }

  /**
   * Enhanced JWT token validation with circuit breaker
   */
  async validateJwtToken(token) {
    this.checkJwtCircuitBreaker();

    try {
      if (!this.jwtVerifier) {
        throw new Error("JWT verifier not available");
      }

      // Check session cache first
      const cachedSession = this.sessionCache.get(token);
      if (
        cachedSession &&
        Date.now() - cachedSession.timestamp < this.cacheTimeout
      ) {
        this.recordJwtSuccess();
        return cachedSession.user;
      }

      // Verify token
      const payload = await this.jwtVerifier.verify(token);

      const user = {
        sub: payload.sub,
        email: payload.email,
        username: payload.username,
        role: payload["custom:role"] || "user",
        groups: payload["cognito:groups"] || [],
        tokenIssueTime: payload.iat,
        tokenExpirationTime: payload.exp,
        sessionId: crypto.randomUUID(),
      };

      // Cache session
      this.sessionCache.set(token, {
        user,
        timestamp: Date.now(),
      });

      this.recordJwtSuccess();
      return user;
    } catch (error) {
      this.recordJwtFailure(error);
      throw error;
    }
  }

  /**
   * Check JWT circuit breaker state
   */
  checkJwtCircuitBreaker() {
    const now = Date.now();

    if (this.jwtCircuitBreaker.state === "OPEN") {
      if (
        now - this.jwtCircuitBreaker.lastFailureTime >
        this.jwtCircuitBreaker.timeout
      ) {
        this.jwtCircuitBreaker.state = "HALF_OPEN";
        console.log("JWT circuit breaker entering HALF_OPEN state");
      } else {
        throw new Error(
          "JWT circuit breaker is OPEN - authentication temporarily unavailable"
        );
      }
    }
  }

  /**
   * Record JWT success
   */
  recordJwtSuccess() {
    if (this.jwtCircuitBreaker.state === "HALF_OPEN") {
      this.jwtCircuitBreaker.state = "CLOSED";
      this.jwtCircuitBreaker.failures = 0;
      console.log("JWT circuit breaker reset to CLOSED state");
    }
  }

  /**
   * Record JWT failure
   */
  recordJwtFailure(error) {
    this.jwtCircuitBreaker.failures++;
    this.jwtCircuitBreaker.lastFailureTime = Date.now();

    if (this.jwtCircuitBreaker.failures >= this.jwtCircuitBreaker.maxFailures) {
      this.jwtCircuitBreaker.state = "OPEN";
      console.error(
        `JWT circuit breaker OPENED after ${this.jwtCircuitBreaker.failures} failures:`,
        error.message
      );
    }
  }

  /**
   * Get encryption key from AWS Secrets Manager with fallback
   */
  async getEncryptionKey() {
    if (this.encryptionKey) {
      return this.encryptionKey;
    }

    try {
      const secretArn = process.env.API_KEY_ENCRYPTION_SECRET_ARN;
      if (!secretArn) {
        // Fallback to environment variable
        const envKey = process.env.API_KEY_ENCRYPTION_SECRET;
        if (envKey) {
          console.warn(
            "Using environment variable for encryption key - consider using AWS Secrets Manager"
          );
          this.encryptionKey = envKey;
          return this.encryptionKey;
        }
        throw new Error("No encryption key available");
      }

      const command = new GetSecretValueCommand({ SecretId: secretArn });
      const result = await this.secretsManager.send(command);

      let secret;
      if (typeof result.SecretString === "string") {
        secret = JSON.parse(result.SecretString);
      } else {
        secret = result.SecretString;
      }

      this.encryptionKey =
        secret.encryptionKey || secret.API_KEY_ENCRYPTION_SECRET;
      return this.encryptionKey;
    } catch (error) {
      console.error("Failed to get encryption key:", error.message);
      throw new Error("Encryption key not available");
    }
  }

  /**
   * Check API key circuit breaker state
   */
  checkCircuitBreaker() {
    const now = Date.now();

    if (this.circuitBreaker.state === "OPEN") {
      if (
        now - this.circuitBreaker.lastFailureTime >
        this.circuitBreaker.timeout
      ) {
        this.circuitBreaker.state = "HALF_OPEN";
        console.log("API key circuit breaker entering HALF_OPEN state");
      } else {
        throw new Error(
          "API key circuit breaker is OPEN - service temporarily unavailable"
        );
      }
    }
  }

  /**
   * Record API key operation success
   */
  recordSuccess() {
    if (this.circuitBreaker.state === "HALF_OPEN") {
      this.circuitBreaker.state = "CLOSED";
      this.circuitBreaker.failures = 0;
      console.log("API key circuit breaker reset to CLOSED state");
    }
  }

  /**
   * Record API key operation failure
   */
  recordFailure(error) {
    this.circuitBreaker.failures++;
    this.circuitBreaker.lastFailureTime = Date.now();

    if (this.circuitBreaker.failures >= this.circuitBreaker.maxFailures) {
      this.circuitBreaker.state = "OPEN";
      console.error(
        `API key circuit breaker OPENED after ${this.circuitBreaker.failures} failures:`,
        error.message
      );
    }
  }

  /**
   * Enhanced encryption with improved security
   */
  async encryptApiKey(data, userSalt) {
    try {
      const encryptionKey = await this.getEncryptionKey();
      const algorithm = "aes-256-gcm";
      const key = crypto.scryptSync(encryptionKey, userSalt, 32);
      const iv = crypto.randomBytes(16);

      const cipher = crypto.createCipherGCM(algorithm, key, iv);
      cipher.setAAD(Buffer.from(userSalt));

      let encrypted = cipher.update(JSON.stringify(data), "utf8", "hex");
      encrypted += cipher.final("hex");

      const authTag = cipher.getAuthTag();

      return {
        encrypted,
        iv: iv.toString("hex"),
        authTag: authTag.toString("hex"),
        algorithm,
        version: "2.0", // Version for migration tracking
      };
    } catch (error) {
      console.error("Encryption error:", error);
      throw new Error("Failed to encrypt API key data");
    }
  }

  /**
   * Enhanced decryption with version support
   */
  async decryptApiKey(encryptedData, userSalt) {
    try {
      const encryptionKey = await this.getEncryptionKey();
      const { encrypted, iv, authTag, algorithm, version } = encryptedData;
      const key = crypto.scryptSync(encryptionKey, userSalt, 32);

      const decipher = crypto.createDecipherGCM(
        algorithm,
        key,
        Buffer.from(iv, "hex")
      );
      decipher.setAAD(Buffer.from(userSalt));
      decipher.setAuthTag(Buffer.from(authTag, "hex"));

      let decrypted = decipher.update(encrypted, "hex", "utf8");
      decrypted += decipher.final("utf8");

      return JSON.parse(decrypted);
    } catch (error) {
      console.error("Decryption error:", error);
      throw new Error("Failed to decrypt API key data");
    }
  }

  /**
   * Store API key with JWT validation
   */
  async storeApiKey(token, provider, apiKeyData) {
    this.checkCircuitBreaker();

    try {
      // Validate JWT token
      const user = await this.validateJwtToken(token);
      const userId = user.sub;

      // Generate user-specific salt
      const userSalt = crypto.randomBytes(32).toString("hex");

      // Encrypt the API key data
      const encryptedData = await this.encryptApiKey(apiKeyData, userSalt);

      // Store in database with audit trail
      const result = await query(
        `
        INSERT INTO user_api_keys (user_id, provider, encrypted_data, user_salt, created_at, updated_at)
        VALUES ($1, $2, $3, $4, NOW(), NOW())
        ON CONFLICT (user_id, provider) 
        DO UPDATE SET 
          encrypted_data = EXCLUDED.encrypted_data,
          user_salt = EXCLUDED.user_salt,
          updated_at = NOW()
        RETURNING id
      `,
        [userId, provider, JSON.stringify(encryptedData), userSalt]
      );

      // Clear cache
      const cacheKey = `${userId}:${provider}`;
      this.keyCache.delete(cacheKey);

      // Log audit event
      await this.logAuditEvent(
        userId,
        "API_KEY_STORED",
        provider,
        user.sessionId
      );

      this.recordSuccess();

      return {
        success: true,
        id: result.rows[0].id,
        provider: provider,
        encrypted: true,
        user: {
          id: userId,
          email: user.email,
          sessionId: user.sessionId,
        },
      };
    } catch (error) {
      this.recordFailure(error);
      console.error("API key storage error:", error);
      throw new Error(
        `Failed to store API key for ${provider}: ${error.message}`
      );
    }
  }

  /**
   * Retrieve API key with JWT validation
   */
  async getApiKey(token, provider) {
    this.checkCircuitBreaker();

    try {
      // Validate JWT token
      const user = await this.validateJwtToken(token);
      const userId = user.sub;

      const cacheKey = `${userId}:${provider}`;
      const cached = this.keyCache.get(cacheKey);

      // Return cached result if valid
      if (cached && Date.now() - cached.timestamp < this.cacheTimeout) {
        return cached.data;
      }

      // Get encrypted data from database
      const result = await query(
        `
        SELECT encrypted_data, user_salt, updated_at
        FROM user_api_keys 
        WHERE user_id = $1 AND provider = $2
      `,
        [userId, provider]
      );

      if (result.rows.length === 0) {
        this.recordSuccess();
        return null;
      }

      const { encrypted_data, user_salt } = result.rows[0];
      const encryptedData = JSON.parse(encrypted_data);

      // Decrypt the data
      const decryptedData = await this.decryptApiKey(encryptedData, user_salt);

      // Cache the result
      this.keyCache.set(cacheKey, {
        data: decryptedData,
        timestamp: Date.now(),
      });

      // Update last used timestamp
      await query(
        `
        UPDATE user_api_keys 
        SET last_used = NOW() 
        WHERE user_id = $1 AND provider = $2
      `,
        [userId, provider]
      );

      // Log audit event
      await this.logAuditEvent(
        userId,
        "API_KEY_ACCESSED",
        provider,
        user.sessionId
      );

      this.recordSuccess();
      return decryptedData;
    } catch (error) {
      this.recordFailure(error);
      console.error("API key retrieval error:", error);

      if (error.message.includes("circuit breaker")) {
        throw error;
      }

      return null;
    }
  }

  /**
   * Log audit events
   */
  async logAuditEvent(userId, action, provider, sessionId) {
    try {
      await query(
        `
        INSERT INTO api_key_audit_log (user_id, action, provider, session_id, timestamp, ip_address)
        VALUES ($1, $2, $3, $4, NOW(), $5)
      `,
        [userId, action, provider, sessionId, null]
      ); // IP address can be added later
    } catch (error) {
      console.error("Audit logging error:", error);
      // Don't throw - audit logging failures shouldn't break main functionality
    }
  }

  /**
   * Validate API key configuration with connection test
   */
  async validateApiKey(token, provider, testConnection = false) {
    try {
      const user = await this.validateJwtToken(token);
      const apiKeyData = await this.getApiKey(token, provider);

      if (!apiKeyData) {
        return {
          valid: false,
          error: "API key not configured",
          provider: provider,
        };
      }

      const requiredFields = this.getRequiredFields(provider);
      const missingFields = requiredFields.filter(
        (field) => !apiKeyData[field]
      );

      if (missingFields.length > 0) {
        return {
          valid: false,
          error: `Missing required fields: ${missingFields.join(", ")}`,
          provider: provider,
          missingFields,
        };
      }

      // Connection test for supported providers
      if (testConnection) {
        const testResult = await this.testConnection(provider, apiKeyData);
        await this.logAuditEvent(
          user.sub,
          "API_KEY_TESTED",
          provider,
          user.sessionId
        );
        return testResult;
      }

      return {
        valid: true,
        provider: provider,
        environment: apiKeyData.isSandbox ? "sandbox" : "live",
      };
    } catch (error) {
      console.error("API key validation error:", error);
      return {
        valid: false,
        error: error.message,
        provider: provider,
      };
    }
  }

  /**
   * Test connection to provider
   */
  async testConnection(provider, apiKeyData) {
    try {
      switch (provider) {
        case "alpaca":
          const AlpacaService = require("./alpacaService");
          const alpacaService = new AlpacaService(
            apiKeyData.apiKey,
            apiKeyData.apiSecret,
            apiKeyData.isSandbox
          );
          return await alpacaService.validateCredentials();

        case "polygon":
          // Add polygon validation
          return { valid: true, provider: "polygon" };

        case "finnhub":
          // Add finnhub validation
          return { valid: true, provider: "finnhub" };

        default:
          return { valid: true, provider: provider };
      }
    } catch (error) {
      return {
        valid: false,
        error: `Connection test failed: ${error.message}`,
        provider: provider,
      };
    }
  }

  /**
   * Get required fields for provider
   */
  getRequiredFields(provider) {
    const fieldMap = {
      alpaca: ["apiKey", "apiSecret"],
      polygon: ["apiKey"],
      finnhub: ["apiKey"],
      alpha_vantage: ["apiKey"],
    };

    return fieldMap[provider] || ["apiKey"];
  }

  /**
   * Delete API key with JWT validation
   */
  async deleteApiKey(token, provider) {
    this.checkCircuitBreaker();

    try {
      const user = await this.validateJwtToken(token);
      const userId = user.sub;

      const result = await query(
        `
        DELETE FROM user_api_keys 
        WHERE user_id = $1 AND provider = $2
        RETURNING id
      `,
        [userId, provider]
      );

      // Clear cache
      const cacheKey = `${userId}:${provider}`;
      this.keyCache.delete(cacheKey);

      // Log audit event
      await this.logAuditEvent(
        userId,
        "API_KEY_DELETED",
        provider,
        user.sessionId
      );

      this.recordSuccess();

      return {
        success: true,
        deleted: result.rowCount > 0,
        provider: provider,
      };
    } catch (error) {
      this.recordFailure(error);
      console.error("API key deletion error:", error);
      throw new Error(
        `Failed to delete API key for ${provider}: ${error.message}`
      );
    }
  }

  /**
   * List providers with JWT validation
   */
  async listProviders(token) {
    this.checkCircuitBreaker();

    try {
      const user = await this.validateJwtToken(token);
      const userId = user.sub;

      const result = await query(
        `
        SELECT provider, updated_at, created_at, last_used
        FROM user_api_keys 
        WHERE user_id = $1
        ORDER BY provider
      `,
        [userId]
      );

      this.recordSuccess();

      return result.rows.map((row) => ({
        provider: row.provider,
        configured: true,
        lastUpdated: row.updated_at,
        createdAt: row.created_at,
        lastUsed: row.last_used,
      }));
    } catch (error) {
      this.recordFailure(error);
      console.error("Provider listing error:", error);
      return [];
    }
  }

  /**
   * Invalidate session cache
   */
  invalidateSession(token) {
    this.sessionCache.delete(token);
  }

  /**
   * Clear all caches
   */
  clearCaches() {
    this.keyCache.clear();
    this.sessionCache.clear();
  }

  /**
   * Get comprehensive service health status
   */
  getHealthStatus() {
    return {
      apiKeyCircuitBreaker: {
        state: this.circuitBreaker.state,
        failures: this.circuitBreaker.failures,
        lastFailureTime: this.circuitBreaker.lastFailureTime,
      },
      jwtCircuitBreaker: {
        state: this.jwtCircuitBreaker.state,
        failures: this.jwtCircuitBreaker.failures,
        lastFailureTime: this.jwtCircuitBreaker.lastFailureTime,
      },
      cache: {
        keyCache: this.keyCache.size,
        sessionCache: this.sessionCache.size,
        timeout: this.cacheTimeout,
      },
      services: {
        encryptionAvailable: !!this.encryptionKey,
        jwtVerifierAvailable: !!this.jwtVerifier,
      },
    };
  }
}

// Export singleton instance
const apiKeyService = new ApiKeyService();

module.exports = {
  // JWT-validated methods
  storeApiKey: (token, provider, apiKeyData) =>
    apiKeyService.storeApiKey(token, provider, apiKeyData),
  getApiKey: (token, provider) => apiKeyService.getApiKey(token, provider),
  validateApiKey: (token, provider, testConnection) =>
    apiKeyService.validateApiKey(token, provider, testConnection),
  deleteApiKey: (token, provider) =>
    apiKeyService.deleteApiKey(token, provider),
  listProviders: (token) => apiKeyService.listProviders(token),

  // Session management
  invalidateSession: (token) => apiKeyService.invalidateSession(token),
  clearCaches: () => apiKeyService.clearCaches(),

  // Health and monitoring
  getHealthStatus: () => apiKeyService.getHealthStatus(),

  // Direct JWT validation (for middleware use)
  validateJwtToken: (token) => apiKeyService.validateJwtToken(token),
};
