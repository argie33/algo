/**
 * Mock Database Circuit Breaker for Unit Tests
 */

class MockDatabaseCircuitBreaker {
  constructor() {
    this.state = 'closed';
    this.failures = 0;
    this.isOpen = false;
    this.threshold = 5;
    this.timeout = 60000;
  }

  async execute(operation, operationName = 'unknown') {
    console.log(`🔍 [MOCK] Circuit breaker executing: ${operationName}`);
    // Always succeed in tests
    const result = await operation();
    this.recordSuccess();
    return result;
  }

  recordSuccess() {
    this.failures = 0;
    this.state = 'closed';
    this.isOpen = false;
  }

  recordFailure(operationName, duration = 0, error = null) {
    this.failures++;
    console.log(`🔍 [MOCK] Circuit breaker recorded failure for: ${operationName}`);
  }

  canExecute() {
    return true; // Always allow execution in tests
  }

  getStats() {
    return {
      state: this.state,
      failures: this.failures,
      isOpen: this.isOpen,
      threshold: this.threshold
    };
  }
}

module.exports = MockDatabaseCircuitBreaker;