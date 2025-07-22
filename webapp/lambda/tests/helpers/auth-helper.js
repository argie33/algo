/**
 * Integration Test Authentication Helper
 * Provides authentication utilities for integration tests
 */

const jwt = require('jsonwebtoken');
const bcrypt = require('bcrypt');

// Load auth configuration
const authConfig = require('../../test-auth-config.json');

class IntegrationAuthHelper {
  static getTestUser() {
    return authConfig.integration.testUser;
  }

  static getAuthToken() {
    return authConfig.integration.authToken;
  }

  static getJWTSecret() {
    return authConfig.integration.jwtSecret;
  }

  static async verifyPassword(plainPassword) {
    const testUser = this.getTestUser();
    return await bcrypt.compare(plainPassword, testUser.passwordHash);
  }

  static generateAuthHeaders() {
    return {
      'Authorization': `Bearer ${this.getAuthToken()}`,
      'Content-Type': 'application/json'
    };
  }

  static isAuthConfigured() {
    return authConfig.integration.configured === true;
  }

  static getTestCredentials() {
    return {
      email: authConfig.integration.testUser.email,
      password: 'IntegrationTest123!' // Known test password
    };
  }
}

module.exports = IntegrationAuthHelper;
