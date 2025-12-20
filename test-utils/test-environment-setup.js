/**
 * Test Environment Setup Utilities
 * 
 * Provides common utilities and helpers for test setup across the entire project.
 * Used by both frontend and backend tests for consistent test environment.
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

/**
 * Environment configuration for different test types
 */
const TEST_ENVIRONMENTS = {
  unit: {
    timeout: 15000,
    retries: 2,
    coverage: true,
    parallel: true
  },
  integration: {
    timeout: 30000,
    retries: 1,
    coverage: true,
    parallel: false
  },
  e2e: {
    timeout: 60000,
    retries: 3,
    coverage: false,
    parallel: false
  },
  performance: {
    timeout: 120000,
    retries: 0,
    coverage: false,
    parallel: false
  },
  security: {
    timeout: 45000,
    retries: 1,
    coverage: true,
    parallel: true
  }
};

/**
 * Test data generators for consistent test data across tests
 */
class TestDataGenerator {
  /**
   * Generate consistent user test data
   */
  static generateTestUser(overrides = {}) {
    return {
      id: 'test-user-' + Date.now(),
      username: 'testuser',
      email: 'test@example.com',
      firstName: 'Test',
      lastName: 'User',
      role: 'user',
      isActive: true,
      createdAt: new Date().toISOString(),
      ...overrides
    };
  }

  /**
   * Generate test portfolio data
   */
  static generateTestPortfolio(overrides = {}) {
    return {
      id: 'portfolio-' + Date.now(),
      userId: 'test-user-123',
      totalValue: 125000.50,
      totalGainLoss: 8500.25,
      totalGainLossPercent: 7.3,
      dayGainLoss: 350.75,
      dayGainLossPercent: 0.28,
      lastUpdated: new Date().toISOString(),
      holdings: [
        {
          symbol: 'AAPL',
          quantity: 100,
          avgPrice: 180.50,
          currentPrice: 195.20,
          totalValue: 19520.00,
          gainLoss: 1470.00,
          gainLossPercent: 8.14,
          sector: 'Technology'
        },
        {
          symbol: 'MSFT',
          quantity: 50,
          avgPrice: 350.00,
          currentPrice: 385.75,
          totalValue: 19287.50,
          gainLoss: 1787.50,
          gainLossPercent: 10.21,
          sector: 'Technology'
        }
      ],
      ...overrides
    };
  }

  /**
   * Generate test API key data
   */
  static generateTestApiKeys(overrides = {}) {
    return {
      userId: 'test-user-123',
      provider: 'alpaca',
      credentials: {
        keyId: 'test-key-id',
        secret: 'test-secret-key'
      },
      isValid: true,
      lastValidated: new Date().toISOString(),
      ...overrides
    };
  }

  /**
   * Generate test market data
   */
  static generateTestMarketData(symbol = 'AAPL', overrides = {}) {
    return {
      symbol: symbol,
      price: 195.20,
      change: 2.15,
      changePercent: 1.11,
      volume: 25000000,
      high: 197.50,
      low: 192.80,
      open: 193.40,
      previousClose: 193.05,
      marketCap: 3000000000000,
      peRatio: 28.5,
      dividendYield: 0.52,
      lastUpdated: new Date().toISOString(),
      ...overrides
    };
  }
}

/**
 * Test environment setup utilities
 */
class TestEnvironmentSetup {
  /**
   * Setup test environment based on test type
   */
  static setupEnvironment(testType = 'unit') {
    const config = TEST_ENVIRONMENTS[testType] || TEST_ENVIRONMENTS.unit;
    
    // Set environment variables
    process.env.NODE_ENV = 'test';
    process.env.CI = process.env.CI || 'false';
    
    // Test-specific environment variables
    if (testType === 'integration' || testType === 'e2e') {
      process.env.TEST_TIMEOUT = config.timeout.toString();
      process.env.API_BASE_URL = 'http://localhost:3001';
      process.env.FRONTEND_BASE_URL = 'http://localhost:3000';
    }

    if (testType === 'security') {
      process.env.JWT_SECRET = 'test-jwt-secret-for-security-testing';
      process.env.API_KEY_ENCRYPTION_SECRET = 'test-encryption-secret-32-characters';
    }

    return config;
  }

  /**
   * Clean up test environment
   */
  static cleanupEnvironment() {
    // Clean up test-specific environment variables
    delete process.env.TEST_TIMEOUT;
    delete process.env.API_BASE_URL;
    delete process.env.FRONTEND_BASE_URL;
    delete process.env.JWT_SECRET;
    delete process.env.API_KEY_ENCRYPTION_SECRET;
  }

  /**
   * Setup test database (for backend tests)
   */
  static async setupTestDatabase() {
    // This would be implemented based on your database setup
    // For now, we'll use pg-mem for in-memory PostgreSQL
    const { newDb } = require('pg-mem');
    
    const db = newDb();
    
    // Create test tables
    db.public.none(`
      CREATE TABLE IF NOT EXISTS users (
        id VARCHAR(255) PRIMARY KEY,
        username VARCHAR(255) UNIQUE NOT NULL,
        email VARCHAR(255) UNIQUE NOT NULL,
        first_name VARCHAR(255),
        last_name VARCHAR(255),
        role VARCHAR(50) DEFAULT 'user',
        is_active BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      );
    `);

    db.public.none(`
      CREATE TABLE IF NOT EXISTS portfolio_holdings (
        id VARCHAR(255) PRIMARY KEY,
        user_id VARCHAR(255) REFERENCES users(id),
        symbol VARCHAR(10) NOT NULL,
        quantity DECIMAL(15,6) NOT NULL,
        avg_price DECIMAL(15,6) NOT NULL,
        current_price DECIMAL(15,6),
        sector VARCHAR(100),
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      );
    `);

    db.public.none(`
      CREATE TABLE IF NOT EXISTS api_keys (
        id VARCHAR(255) PRIMARY KEY,
        user_id VARCHAR(255) REFERENCES users(id),
        provider VARCHAR(50) NOT NULL,
        key_data TEXT NOT NULL,
        is_valid BOOLEAN DEFAULT true,
        last_validated TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      );
    `);

    return db.adapters.createPg();
  }

  /**
   * Wait for service to be available
   */
  static async waitForService(url, maxAttempts = 30, interval = 1000) {
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      try {
        const response = await fetch(url);
        if (response.ok) {
          return true;
        }
      } catch {
        // Service not ready yet
      }

      if (attempt === maxAttempts) {
        throw new Error(`Service not available at ${url} after ${maxAttempts} attempts`);
      }

      await new Promise(resolve => setTimeout(resolve, interval));
    }
  }

  /**
   * Check if test dependencies are installed
   */
  static checkTestDependencies() {
    const requiredPackages = {
      frontend: [
        '@testing-library/react',
        '@testing-library/jest-dom', 
        '@testing-library/user-event',
        'vitest',
        'jsdom',
        '@playwright/test'
      ],
      backend: [
        'jest',
        'supertest',
        'pg-mem'
      ]
    };

    const missing = {
      frontend: [],
      backend: []
    };

    // Check frontend dependencies
    try {
      const frontendPkg = JSON.parse(fs.readFileSync(
        path.join(process.cwd(), 'webapp/frontend/package.json'), 'utf8'
      ));
      const frontendDeps = { ...frontendPkg.dependencies, ...frontendPkg.devDependencies };
      
      requiredPackages.frontend.forEach(pkg => {
        if (!frontendDeps[pkg]) {
          missing.frontend.push(pkg);
        }
      });
    } catch {
      console.warn('Could not check frontend dependencies');
    }

    // Check backend dependencies
    try {
      const backendPkg = JSON.parse(fs.readFileSync(
        path.join(process.cwd(), 'webapp/lambda/package.json'), 'utf8'
      ));
      const backendDeps = { ...backendPkg.dependencies, ...backendPkg.devDependencies };
      
      requiredPackages.backend.forEach(pkg => {
        if (!backendDeps[pkg]) {
          missing.backend.push(pkg);
        }
      });
    } catch {
      console.warn('Could not check backend dependencies');
    }

    return missing;
  }

  /**
   * Install missing test dependencies
   */
  static installMissingDependencies(missing) {
    if (missing.frontend.length > 0) {
      console.log('Installing missing frontend dependencies:', missing.frontend.join(', '));
      try {
        execSync(`cd webapp/frontend && npm install ${missing.frontend.join(' ')}`, 
          { stdio: 'inherit' });
      } catch (error) {
        console.error('Failed to install frontend dependencies:', error.message);
      }
    }

    if (missing.backend.length > 0) {
      console.log('Installing missing backend dependencies:', missing.backend.join(', '));
      try {
        execSync(`cd webapp/lambda && npm install ${missing.backend.join(' ')}`, 
          { stdio: 'inherit' });
      } catch (error) {
        console.error('Failed to install backend dependencies:', error.message);
      }
    }
  }
}

/**
 * Test result aggregation and reporting
 */
class TestResultAggregator {
  constructor() {
    this.results = {
      unit: { passed: 0, failed: 0, total: 0 },
      integration: { passed: 0, failed: 0, total: 0 },
      e2e: { passed: 0, failed: 0, total: 0 },
      security: { passed: 0, failed: 0, total: 0 },
      performance: { passed: 0, failed: 0, total: 0 },
      visual: { passed: 0, failed: 0, total: 0 }
    };
    this.coverage = {
      frontend: { lines: 0, functions: 0, branches: 0, statements: 0 },
      backend: { lines: 0, functions: 0, branches: 0, statements: 0 }
    };
  }

  /**
   * Add test results
   */
  addResults(testType, results) {
    if (this.results[testType]) {
      this.results[testType].passed += results.passed || 0;
      this.results[testType].failed += results.failed || 0;
      this.results[testType].total += results.total || 0;
    }
  }

  /**
   * Add coverage results
   */
  addCoverage(component, coverage) {
    if (this.coverage[component]) {
      this.coverage[component] = { ...this.coverage[component], ...coverage };
    }
  }

  /**
   * Generate comprehensive test report
   */
  generateReport() {
    const totalTests = Object.values(this.results)
      .reduce((sum, result) => sum + result.total, 0);
    const totalPassed = Object.values(this.results)
      .reduce((sum, result) => sum + result.passed, 0);
    const totalFailed = Object.values(this.results)
      .reduce((sum, result) => sum + result.failed, 0);

    const report = {
      summary: {
        totalTests,
        totalPassed,
        totalFailed,
        successRate: totalTests > 0 ? (totalPassed / totalTests * 100).toFixed(2) : 0
      },
      byType: this.results,
      coverage: this.coverage,
      timestamp: new Date().toISOString()
    };

    return report;
  }

  /**
   * Generate HTML report
   */
  generateHtmlReport() {
    const report = this.generateReport();
    
    const html = `
<!DOCTYPE html>
<html>
<head>
    <title>Test Results Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .summary { background: #f5f5f5; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
        .success { color: #28a745; }
        .failure { color: #dc3545; }
        .warning { color: #ffc107; }
        table { width: 100%; border-collapse: collapse; margin-bottom: 20px; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background-color: #f8f9fa; }
        .metric { display: inline-block; margin: 10px 20px 10px 0; }
        .progress { width: 100%; height: 20px; background: #e9ecef; border-radius: 10px; overflow: hidden; }
        .progress-bar { height: 100%; transition: width 0.3s ease; }
        .progress-success { background: #28a745; }
        .progress-failure { background: #dc3545; }
    </style>
</head>
<body>
    <h1>🧪 Test Results Report</h1>
    
    <div class="summary">
        <h2>📊 Summary</h2>
        <div class="metric">
            <strong>Total Tests:</strong> ${report.summary.totalTests}
        </div>
        <div class="metric">
            <strong class="success">Passed:</strong> ${report.summary.totalPassed}
        </div>
        <div class="metric">
            <strong class="failure">Failed:</strong> ${report.summary.totalFailed}
        </div>
        <div class="metric">
            <strong>Success Rate:</strong> ${report.summary.successRate}%
        </div>
        
        <div class="progress">
            <div class="progress-bar progress-success" 
                 style="width: ${report.summary.successRate}%"></div>
        </div>
    </div>

    <h2>🔍 Results by Test Type</h2>
    <table>
        <thead>
            <tr>
                <th>Test Type</th>
                <th>Total</th>
                <th>Passed</th>
                <th>Failed</th>
                <th>Success Rate</th>
            </tr>
        </thead>
        <tbody>
            ${Object.entries(report.byType).map(([type, results]) => {
              const successRate = results.total > 0 ? (results.passed / results.total * 100).toFixed(2) : 0;
              return `
                <tr>
                    <td><strong>${type.charAt(0).toUpperCase() + type.slice(1)}</strong></td>
                    <td>${results.total}</td>
                    <td class="success">${results.passed}</td>
                    <td class="failure">${results.failed}</td>
                    <td>${successRate}%</td>
                </tr>
              `;
            }).join('')}
        </tbody>
    </table>

    <h2>📈 Coverage Results</h2>
    <table>
        <thead>
            <tr>
                <th>Component</th>
                <th>Lines</th>
                <th>Functions</th>
                <th>Branches</th>
                <th>Statements</th>
            </tr>
        </thead>
        <tbody>
            ${Object.entries(report.coverage).map(([component, coverage]) => `
                <tr>
                    <td><strong>${component.charAt(0).toUpperCase() + component.slice(1)}</strong></td>
                    <td>${coverage.lines}%</td>
                    <td>${coverage.functions}%</td>
                    <td>${coverage.branches}%</td>
                    <td>${coverage.statements}%</td>
                </tr>
            `).join('')}
        </tbody>
    </table>

    <footer>
        <p><small>Generated on ${report.timestamp}</small></p>
    </footer>
</body>
</html>
    `;

    return html;
  }
}

module.exports = {
  TEST_ENVIRONMENTS,
  TestDataGenerator,
  TestEnvironmentSetup,
  TestResultAggregator
};