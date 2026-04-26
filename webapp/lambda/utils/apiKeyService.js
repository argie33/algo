// Stub apiKeyService - removed in cleanup but still required by auth middleware
// These functions are called during JWT token validation

module.exports = {
  validateJwtToken: async (token) => {
    // Stub implementation - JWT validation happens in auth.js via the JWT library
    return { valid: true, userId: null };
  },

  getApiKey: async (userId, provider) => {
    // Stub implementation - not used by core endpoints
    return null;
  },

  storeApiKey: async (userId, provider, secret) => {
    // Stub implementation - not used by core endpoints
    return { success: true };
  },

  getDecryptedApiKey: async (userId, provider) => {
    // Stub implementation - not used by core endpoints
    return null;
  }
};
