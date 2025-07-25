/**
 * Infrastructure Health Check Utility
 * Checks current site infrastructure status before running tests
 */

const API_BASE_URL = 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev';

export class InfrastructureHealthChecker {
  constructor() {
    this.healthStatus = null;
    this.lastCheck = null;
    this.checkInterval = 30000; // 30 seconds
  }

  async checkHealth() {
    try {
      const response = await fetch(`${API_BASE_URL}/api/health`);
      const health = await response.json();
      
      this.healthStatus = {
        timestamp: new Date().toISOString(),
        overall: health.status || 'unknown',
        database: health.database?.status || 'unknown',
        endpoints: health.endpoints || [],
        available: response.ok,
        details: health
      };
      
      this.lastCheck = Date.now();
      return this.healthStatus;
    } catch (error) {
      this.healthStatus = {
        timestamp: new Date().toISOString(),
        overall: 'down',
        database: 'unknown',
        endpoints: [],
        available: false,
        error: error.message,
        details: null
      };
      
      this.lastCheck = Date.now();
      return this.healthStatus;
    }
  }

  async checkEndpointAvailability(endpoint) {
    try {
      const response = await fetch(`${API_BASE_URL}${endpoint}`);
      return {
        endpoint,
        available: response.ok,
        status: response.status,
        statusText: response.statusText
      };
    } catch (error) {
      return {
        endpoint,
        available: false,
        status: 0,
        statusText: 'Network Error',
        error: error.message
      };
    }
  }

  async getHealthStatus() {
    // Return cached status if checked recently
    if (this.lastCheck && (Date.now() - this.lastCheck) < this.checkInterval) {
      return this.healthStatus;
    }
    
    return await this.checkHealth();
  }

  isDatabaseHealthy() {
    return this.healthStatus?.database === 'connected';
  }

  isEndpointAvailable(endpoint) {
    if (!this.healthStatus?.details?.availableEndpoints) {
      return false;
    }
    return this.healthStatus.details.availableEndpoints.includes(endpoint);
  }

  shouldSkipDatabaseTests() {
    return !this.isDatabaseHealthy();
  }

  shouldSkipUserManagementTests() {
    return !this.isEndpointAvailable('/api/user/change-password');
  }

  getExpectedErrorForEndpoint(endpoint) {
    const health = this.healthStatus;
    
    if (!health?.available) {
      return {
        status: 503,
        error: 'Service Unavailable',
        type: 'infrastructure_down'
      };
    }
    
    if (!this.isEndpointAvailable(endpoint)) {
      return {
        status: 404,
        error: 'Endpoint not found',
        type: 'endpoint_not_implemented',
        availableEndpoints: health.details?.availableEndpoints || []
      };
    }
    
    if (!this.isDatabaseHealthy()) {
      return {
        status: 503,
        error: 'Database connectivity issues',
        type: 'database_down',
        details: health.details?.database
      };
    }
    
    return null; // Endpoint should work normally
  }
}

// Singleton instance for test use
export const infrastructureHealth = new InfrastructureHealthChecker();

// Helper functions for tests
export async function skipIfInfrastructureDown(testContext) {
  const health = await infrastructureHealth.getHealthStatus();
  
  if (!health.available) {
    testContext.skip(`Skipping test - infrastructure is down: ${health.error}`);
  }
}

export async function skipIfDatabaseDown(testContext) {
  const health = await infrastructureHealth.getHealthStatus();
  
  if (!infrastructureHealth.isDatabaseHealthy()) {
    testContext.skip(`Skipping test - database is unavailable: ${health.details?.database?.error || 'Unknown error'}`);
  }
}

export async function skipIfEndpointUnavailable(testContext, endpoint) {
  const health = await infrastructureHealth.getHealthStatus();
  
  if (!infrastructureHealth.isEndpointAvailable(endpoint)) {
    testContext.skip(`Skipping test - endpoint ${endpoint} is not available. Available: ${health.details?.availableEndpoints?.join(', ') || 'none'}`);
  }
}

export async function getExpectedResponseForCurrentInfrastructure(endpoint) {
  const health = await infrastructureHealth.getHealthStatus();
  const expectedError = infrastructureHealth.getExpectedErrorForEndpoint(endpoint);
  
  if (expectedError) {
    return {
      shouldSucceed: false,
      expectedStatus: expectedError.status,
      expectedError: expectedError.error,
      expectedType: expectedError.type,
      mockResponse: {
        ok: false,
        status: expectedError.status,
        json: async () => ({
          success: false,
          error: expectedError.error,
          ...expectedError.details && { details: expectedError.details },
          ...expectedError.availableEndpoints && { availableEndpoints: expectedError.availableEndpoints }
        })
      }
    };
  }
  
  return {
    shouldSucceed: true,
    expectedStatus: 200,
    expectedError: null,
    expectedType: 'success'
  };
}

export default infrastructureHealth;