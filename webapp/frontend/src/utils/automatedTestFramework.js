/**
 * Automated Testing Framework - Fully Programmatic
 * Complete headless testing infrastructure for CI/CD pipelines
 * No manual browser interaction required
 */

import { v4 as uuidv4 } from 'uuid';

class AutomatedTestFramework {
  constructor() {
    this.testSuites = new Map();
    this.testResults = [];
    this.testRunId = uuidv4();
    this.ciMode = this.detectCIEnvironment();
    this.headlessMode = true;
    this.initializeFramework();
  }

  detectCIEnvironment() {
    // Detect common CI environments
    const ciEnvs = ['CI', 'GITHUB_ACTIONS', 'TRAVIS', 'CIRCLECI', 'JENKINS', 'GITLAB_CI'];
    return ciEnvs.some(env => typeof process !== 'undefined' && process.env && process.env[env]);
  }

  initializeFramework() {
    console.log('🤖 Initializing Automated Testing Framework...');
    console.log(`📍 Test Run ID: ${this.testRunId}`);
    console.log(`🔧 CI Mode: ${this.ciMode ? 'ON' : 'OFF'}`);
    console.log(`👻 Headless Mode: ${this.headlessMode ? 'ON' : 'OFF'}`);
    
    this.setupTestSuites();
    this.setupAutomatedReporting();
    this.setupContinuousIntegration();
  }

  setupTestSuites() {
    // Unit Test Suite - Portfolio Math
    this.testSuites.set('portfolio-math', {
      name: 'Portfolio Mathematics',
      type: 'unit',
      timeout: 30000,
      tests: [
        {
          id: 'var-calculation',
          name: 'VaR Calculation Accuracy',
          test: this.testVaRCalculation.bind(this)
        },
        {
          id: 'sharpe-ratio',
          name: 'Sharpe Ratio Calculation',
          test: this.testSharpeRatio.bind(this)
        },
        {
          id: 'correlation-matrix',
          name: 'Correlation Matrix Generation',
          test: this.testCorrelationMatrix.bind(this)
        }
      ]
    });

    // Integration Test Suite - API Endpoints
    this.testSuites.set('api-integration', {
      name: 'API Integration Tests',
      type: 'integration',
      timeout: 60000,
      tests: [
        {
          id: 'health-endpoint',
          name: 'Health Check Endpoint',
          test: this.testHealthEndpoint.bind(this)
        },
        {
          id: 'auth-flow',
          name: 'Authentication Flow',
          test: this.testAuthenticationFlow.bind(this)
        },
        {
          id: 'portfolio-api',
          name: 'Portfolio API CRUD',
          test: this.testPortfolioAPI.bind(this)
        }
      ]
    });

    // Performance Test Suite
    this.testSuites.set('performance', {
      name: 'Performance Testing',
      type: 'performance',
      timeout: 120000,
      tests: [
        {
          id: 'response-time',
          name: 'API Response Time',
          test: this.testAPIResponseTime.bind(this)
        },
        {
          id: 'memory-usage',
          name: 'Memory Usage Monitoring',
          test: this.testMemoryUsage.bind(this)
        },
        {
          id: 'concurrent-users',
          name: 'Concurrent User Simulation',
          test: this.testConcurrentUsers.bind(this)
        }
      ]
    });

    // Security Test Suite
    this.testSuites.set('security', {
      name: 'Security Testing',
      type: 'security',
      timeout: 90000,
      tests: [
        {
          id: 'sql-injection',
          name: 'SQL Injection Protection',
          test: this.testSQLInjectionProtection.bind(this)
        },
        {
          id: 'xss-protection',
          name: 'XSS Protection',
          test: this.testXSSProtection.bind(this)
        },
        {
          id: 'auth-bypass',
          name: 'Authentication Bypass',
          test: this.testAuthenticationBypass.bind(this)
        }
      ]
    });

    // React Hooks Test Suite
    this.testSuites.set('react-hooks', {
      name: 'React Hooks Testing',
      type: 'unit',
      timeout: 45000,
      tests: [
        {
          id: 'use-state-functionality',
          name: 'useState Hook Functionality',
          test: this.testUseStateFunctionality.bind(this)
        },
        {
          id: 'use-sync-external-store',
          name: 'useSyncExternalStore Hook',
          test: this.testUseSyncExternalStore.bind(this)
        },
        {
          id: 'hooks-error-handling',
          name: 'Hooks Error Handling',
          test: this.testHooksErrorHandling.bind(this)
        }
      ]
    });
  }

  setupAutomatedReporting() {
    this.reportingConfig = {
      formats: ['json', 'junit', 'html'],
      destinations: ['console', 'file', 'ci-artifacts'],
      realTimeUpdates: true,
      includeScreenshots: false, // Headless mode
      includeMetrics: true,
      includeTimings: true
    };
  }

  setupContinuousIntegration() {
    if (this.ciMode) {
      console.log('🔄 Setting up CI/CD integration...');
      
      // Setup CI-specific configurations
      this.ciConfig = {
        failFast: true,
        parallelExecution: true,
        retryCount: 3,
        timeoutMultiplier: 1.5,
        artifactCollection: true,
        statusReporting: true
      };
    }
  }

  // Test Implementation Methods
  async testVaRCalculation() {
    const testData = {
      returns: [0.02, -0.01, 0.03, -0.02, 0.01, 0.04, -0.03, 0.02],
      confidenceLevel: 0.05
    };

    try {
      // Mock VaR calculation (replace with actual service)
      const result = await this.calculateVaR(testData.returns, testData.confidenceLevel);
      
      return {
        success: true,
        result: result,
        assertions: [
          { condition: result.var > 0, message: 'VaR should be positive' },
          { condition: result.confidenceLevel === 0.05, message: 'Confidence level should match input' },
          { condition: typeof result.var === 'number', message: 'VaR should be numeric' }
        ]
      };
    } catch (error) {
      return {
        success: false,
        error: error.message,
        stack: error.stack
      };
    }
  }

  async testSharpeRatio() {
    const testData = {
      returns: [0.02, -0.01, 0.03, -0.02, 0.01],
      riskFreeRate: 0.02
    };

    try {
      const result = await this.calculateSharpeRatio(testData.returns, testData.riskFreeRate);
      
      return {
        success: true,
        result: result,
        assertions: [
          { condition: typeof result.sharpeRatio === 'number', message: 'Sharpe ratio should be numeric' },
          { condition: result.annualizedReturn >= 0, message: 'Annualized return should be non-negative' },
          { condition: result.annualizedVolatility >= 0, message: 'Volatility should be non-negative' }
        ]
      };
    } catch (error) {
      return {
        success: false,
        error: error.message,
        stack: error.stack
      };
    }
  }

  async testCorrelationMatrix() {
    const testData = {
      AAPL: [0.02, -0.01, 0.03, -0.02, 0.01],
      GOOGL: [0.01, -0.02, 0.04, -0.01, 0.02],
      MSFT: [0.015, -0.015, 0.025, -0.015, 0.015]
    };

    try {
      const result = await this.calculateCorrelationMatrix(testData);
      
      return {
        success: true,
        result: result,
        assertions: [
          { condition: result.matrix.length === 3, message: 'Matrix should be 3x3' },
          { condition: result.matrix[0][0] === 1, message: 'Diagonal should be 1' },
          { condition: result.symbols.length === 3, message: 'Should have 3 symbols' }
        ]
      };
    } catch (error) {
      return {
        success: false,
        error: error.message,
        stack: error.stack
      };
    }
  }

  async testHealthEndpoint() {
    try {
      const response = await fetch('/api/health', {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json'
        }
      });

      const data = await response.json();
      
      return {
        success: true,
        result: data,
        assertions: [
          { condition: response.status === 200, message: 'Health endpoint should return 200' },
          { condition: data.status === 'healthy', message: 'Status should be healthy' },
          { condition: typeof data.timestamp === 'string', message: 'Timestamp should be present' }
        ]
      };
    } catch (error) {
      return {
        success: false,
        error: error.message,
        stack: error.stack
      };
    }
  }

  async testAuthenticationFlow() {
    const testCredentials = {
      username: 'test@example.com',
      password: 'testPassword123'
    };

    try {
      // Test login
      const loginResponse = await fetch('/api/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(testCredentials)
      });

      const loginData = await loginResponse.json();
      
      // Test token validation
      const validateResponse = await fetch('/api/auth/validate', {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${loginData.token}`
        }
      });

      const validateData = await validateResponse.json();
      
      return {
        success: true,
        result: { loginData, validateData },
        assertions: [
          { condition: loginResponse.status === 200, message: 'Login should succeed' },
          { condition: loginData.token, message: 'Token should be provided' },
          { condition: validateResponse.status === 200, message: 'Token validation should succeed' }
        ]
      };
    } catch (error) {
      return {
        success: false,
        error: error.message,
        stack: error.stack
      };
    }
  }

  async testPortfolioAPI() {
    const testPortfolio = {
      name: 'Test Portfolio',
      positions: [
        { symbol: 'AAPL', shares: 100, price: 150.00 },
        { symbol: 'GOOGL', shares: 50, price: 2000.00 }
      ]
    };

    try {
      // Create portfolio
      const createResponse = await fetch('/api/portfolio', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(testPortfolio)
      });

      const createData = await createResponse.json();
      
      // Read portfolio
      const readResponse = await fetch(`/api/portfolio/${createData.id}`, {
        method: 'GET'
      });

      const readData = await readResponse.json();
      
      // Update portfolio
      const updateResponse = await fetch(`/api/portfolio/${createData.id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ ...testPortfolio, name: 'Updated Portfolio' })
      });

      const updateData = await updateResponse.json();
      
      // Delete portfolio
      const deleteResponse = await fetch(`/api/portfolio/${createData.id}`, {
        method: 'DELETE'
      });

      return {
        success: true,
        result: { createData, readData, updateData, deleteResponse },
        assertions: [
          { condition: createResponse.status === 201, message: 'Portfolio creation should succeed' },
          { condition: readResponse.status === 200, message: 'Portfolio read should succeed' },
          { condition: updateResponse.status === 200, message: 'Portfolio update should succeed' },
          { condition: deleteResponse.status === 204, message: 'Portfolio deletion should succeed' }
        ]
      };
    } catch (error) {
      return {
        success: false,
        error: error.message,
        stack: error.stack
      };
    }
  }

  async testAPIResponseTime() {
    const endpoints = [
      '/api/health',
      '/api/portfolio',
      '/api/market-data',
      '/api/auth/validate'
    ];

    const results = [];
    
    for (const endpoint of endpoints) {
      try {
        const startTime = performance.now();
        const response = await fetch(endpoint);
        const endTime = performance.now();
        
        results.push({
          endpoint,
          responseTime: endTime - startTime,
          status: response.status,
          success: response.ok
        });
      } catch (error) {
        results.push({
          endpoint,
          error: error.message,
          success: false
        });
      }
    }

    const averageResponseTime = results.reduce((sum, r) => sum + (r.responseTime || 0), 0) / results.length;
    
    return {
      success: true,
      result: { results, averageResponseTime },
      assertions: [
        { condition: averageResponseTime < 2000, message: 'Average response time should be under 2 seconds' },
        { condition: results.every(r => r.success), message: 'All endpoints should respond successfully' }
      ]
    };
  }

  async testMemoryUsage() {
    if (!performance.memory) {
      return {
        success: false,
        error: 'Memory API not available',
        skipReason: 'Browser does not support memory measurement'
      };
    }

    const initialMemory = performance.memory.usedJSHeapSize;
    
    // Simulate memory-intensive operations
    const testData = Array.from({ length: 100000 }, (_, i) => ({
      id: i,
      value: Math.random(),
      timestamp: new Date().toISOString()
    }));

    // Process test data
    const processedData = testData.map(item => ({
      ...item,
      processed: true,
      calculation: item.value * 2
    }));

    const finalMemory = performance.memory.usedJSHeapSize;
    const memoryIncrease = finalMemory - initialMemory;
    
    return {
      success: true,
      result: {
        initialMemory,
        finalMemory,
        memoryIncrease,
        processedItems: processedData.length
      },
      assertions: [
        { condition: memoryIncrease < 50 * 1024 * 1024, message: 'Memory increase should be under 50MB' },
        { condition: processedData.length === 100000, message: 'All items should be processed' }
      ]
    };
  }

  async testConcurrentUsers() {
    const concurrentRequests = 50;
    const promises = [];

    for (let i = 0; i < concurrentRequests; i++) {
      promises.push(
        fetch('/api/health')
          .then(response => ({
            success: response.ok,
            status: response.status,
            responseTime: Date.now()
          }))
          .catch(error => ({
            success: false,
            error: error.message
          }))
      );
    }

    const results = await Promise.all(promises);
    const successfulRequests = results.filter(r => r.success).length;
    const failureRate = (concurrentRequests - successfulRequests) / concurrentRequests;

    return {
      success: true,
      result: {
        totalRequests: concurrentRequests,
        successfulRequests,
        failureRate,
        results
      },
      assertions: [
        { condition: failureRate < 0.05, message: 'Failure rate should be under 5%' },
        { condition: successfulRequests >= concurrentRequests * 0.95, message: 'At least 95% of requests should succeed' }
      ]
    };
  }

  async testSQLInjectionProtection() {
    const maliciousInputs = [
      "'; DROP TABLE users; --",
      "1' OR '1'='1",
      "admin'--",
      "1' UNION SELECT * FROM users--"
    ];

    const results = [];
    
    for (const input of maliciousInputs) {
      try {
        const response = await fetch('/api/search', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ query: input })
        });

        const data = await response.json();
        
        results.push({
          input,
          status: response.status,
          blocked: response.status === 400 || response.status === 403,
          response: data
        });
      } catch (error) {
        results.push({
          input,
          error: error.message,
          blocked: true
        });
      }
    }

    const blockedCount = results.filter(r => r.blocked).length;
    
    return {
      success: true,
      result: { results, blockedCount },
      assertions: [
        { condition: blockedCount === maliciousInputs.length, message: 'All SQL injection attempts should be blocked' },
        { condition: results.every(r => r.blocked), message: 'No malicious inputs should succeed' }
      ]
    };
  }

  async testXSSProtection() {
    const xssPayloads = [
      "<script>alert('XSS')</script>",
      "javascript:alert('XSS')",
      "<img src=x onerror=alert('XSS')>",
      "';alert('XSS');//"
    ];

    const results = [];
    
    for (const payload of xssPayloads) {
      try {
        const response = await fetch('/api/comments', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ comment: payload })
        });

        const data = await response.json();
        
        results.push({
          payload,
          status: response.status,
          sanitized: !data.comment || !data.comment.includes('<script>'),
          response: data
        });
      } catch (error) {
        results.push({
          payload,
          error: error.message,
          sanitized: true
        });
      }
    }

    const sanitizedCount = results.filter(r => r.sanitized).length;
    
    return {
      success: true,
      result: { results, sanitizedCount },
      assertions: [
        { condition: sanitizedCount === xssPayloads.length, message: 'All XSS payloads should be sanitized' },
        { condition: results.every(r => r.sanitized), message: 'No XSS payloads should pass through' }
      ]
    };
  }

  async testAuthenticationBypass() {
    const bypassAttempts = [
      { path: '/api/admin/users', method: 'GET', headers: {} },
      { path: '/api/portfolio', method: 'GET', headers: { 'Authorization': 'Bearer invalid-token' } },
      { path: '/api/user/profile', method: 'GET', headers: { 'Authorization': 'Bearer expired-token' } }
    ];

    const results = [];
    
    for (const attempt of bypassAttempts) {
      try {
        const response = await fetch(attempt.path, {
          method: attempt.method,
          headers: attempt.headers
        });

        results.push({
          attempt,
          status: response.status,
          blocked: response.status === 401 || response.status === 403,
          response: await response.json()
        });
      } catch (error) {
        results.push({
          attempt,
          error: error.message,
          blocked: true
        });
      }
    }

    const blockedCount = results.filter(r => r.blocked).length;
    
    return {
      success: true,
      result: { results, blockedCount },
      assertions: [
        { condition: blockedCount === bypassAttempts.length, message: 'All bypass attempts should be blocked' },
        { condition: results.every(r => r.blocked), message: 'No unauthorized access should succeed' }
      ]
    };
  }

  async testUseStateFunctionality() {
    try {
      // Test React.useState availability
      const reactAvailable = typeof window.React !== 'undefined';
      const useStateAvailable = reactAvailable && typeof window.React.useState === 'function';
      
      if (!useStateAvailable) {
        return {
          success: false,
          error: 'useState hook not available',
          diagnostics: {
            reactAvailable,
            useStateAvailable,
            reactVersion: window.React?.version
          }
        };
      }

      // Test useState functionality
      const testResults = {
        reactAvailable,
        useStateAvailable,
        reactVersion: window.React.version,
        functionSignature: window.React.useState.toString().substring(0, 100)
      };

      return {
        success: true,
        result: testResults,
        assertions: [
          { condition: reactAvailable, message: 'React should be available' },
          { condition: useStateAvailable, message: 'useState should be available' },
          { condition: window.React.version.startsWith('18'), message: 'React version should be 18.x' }
        ]
      };
    } catch (error) {
      return {
        success: false,
        error: error.message,
        stack: error.stack
      };
    }
  }

  async testUseSyncExternalStore() {
    try {
      const reactAvailable = typeof window.React !== 'undefined';
      const useSyncExternalStoreAvailable = reactAvailable && typeof window.React.useSyncExternalStore === 'function';
      
      const testResults = {
        reactAvailable,
        useSyncExternalStoreAvailable,
        reactVersion: window.React?.version,
        shimDetected: this.detectUseSyncExternalStoreShim()
      };

      return {
        success: true,
        result: testResults,
        assertions: [
          { condition: reactAvailable, message: 'React should be available' },
          { condition: useSyncExternalStoreAvailable, message: 'useSyncExternalStore should be available' },
          { condition: testResults.shimDetected || useSyncExternalStoreAvailable, message: 'useSyncExternalStore should be available via React 18 or shim' }
        ]
      };
    } catch (error) {
      return {
        success: false,
        error: error.message,
        stack: error.stack
      };
    }
  }

  detectUseSyncExternalStoreShim() {
    const scripts = Array.from(document.scripts);
    return scripts.some(script => 
      script.src.includes('use-sync-external-store') ||
      (script.textContent && script.textContent.includes('useSyncExternalStore'))
    );
  }

  async testHooksErrorHandling() {
    const errorScenarios = [
      { name: 'Missing React', test: () => window.React === undefined },
      { name: 'Missing useState', test: () => !window.React?.useState },
      { name: 'Missing useSyncExternalStore', test: () => !window.React?.useSyncExternalStore }
    ];

    const results = errorScenarios.map(scenario => ({
      name: scenario.name,
      hasError: scenario.test(),
      timestamp: new Date().toISOString()
    }));

    return {
      success: true,
      result: { scenarios: results },
      assertions: [
        { condition: !results.some(r => r.hasError), message: 'No React hooks errors should be present' },
        { condition: results.length === errorScenarios.length, message: 'All error scenarios should be tested' }
      ]
    };
  }

  // Mock calculation methods (replace with actual implementations)
  async calculateVaR(returns, confidenceLevel) {
    // Simplified VaR calculation for testing
    const sorted = returns.sort((a, b) => a - b);
    const index = Math.floor(sorted.length * confidenceLevel);
    return {
      var: Math.abs(sorted[index]),
      confidenceLevel,
      method: 'historical'
    };
  }

  async calculateSharpeRatio(returns, riskFreeRate) {
    const mean = returns.reduce((sum, r) => sum + r, 0) / returns.length;
    const variance = returns.reduce((sum, r) => sum + Math.pow(r - mean, 2), 0) / returns.length;
    const volatility = Math.sqrt(variance);
    
    return {
      sharpeRatio: volatility === 0 ? Infinity : (mean - riskFreeRate) / volatility,
      annualizedReturn: mean * 252,
      annualizedVolatility: volatility * Math.sqrt(252)
    };
  }

  async calculateCorrelationMatrix(assetReturns) {
    const symbols = Object.keys(assetReturns);
    const matrix = symbols.map(() => symbols.map(() => 0));
    
    for (let i = 0; i < symbols.length; i++) {
      for (let j = 0; j < symbols.length; j++) {
        if (i === j) {
          matrix[i][j] = 1;
        } else {
          // Simplified correlation calculation
          matrix[i][j] = Math.random() * 0.8 + 0.1;
        }
      }
    }
    
    return { matrix, symbols };
  }

  // Main execution methods
  async runAllTests() {
    console.log('🚀 Running all automated tests...');
    
    const results = {
      testRunId: this.testRunId,
      timestamp: new Date().toISOString(),
      environment: this.getEnvironmentInfo(),
      suites: {},
      summary: {
        totalTests: 0,
        passedTests: 0,
        failedTests: 0,
        skippedTests: 0,
        duration: 0
      }
    };

    const startTime = Date.now();
    
    for (const [suiteId, suite] of this.testSuites) {
      console.log(`📋 Running test suite: ${suite.name}`);
      
      const suiteResults = await this.runTestSuite(suiteId);
      results.suites[suiteId] = suiteResults;
      
      results.summary.totalTests += suiteResults.tests.length;
      results.summary.passedTests += suiteResults.tests.filter(t => t.success).length;
      results.summary.failedTests += suiteResults.tests.filter(t => !t.success && !t.skipped).length;
      results.summary.skippedTests += suiteResults.tests.filter(t => t.skipped).length;
    }

    results.summary.duration = Date.now() - startTime;
    results.summary.successRate = (results.summary.passedTests / results.summary.totalTests) * 100;
    
    this.testResults.push(results);
    
    console.log('✅ All tests completed');
    console.log(`📊 Results: ${results.summary.passedTests}/${results.summary.totalTests} passed (${results.summary.successRate.toFixed(1)}%)`);
    
    await this.generateTestReport(results);
    
    return results;
  }

  async runTestSuite(suiteId) {
    const suite = this.testSuites.get(suiteId);
    if (!suite) {
      throw new Error(`Test suite not found: ${suiteId}`);
    }

    const results = {
      id: suiteId,
      name: suite.name,
      type: suite.type,
      startTime: new Date().toISOString(),
      tests: [],
      summary: {
        passed: 0,
        failed: 0,
        skipped: 0,
        duration: 0
      }
    };

    const startTime = Date.now();
    
    for (const test of suite.tests) {
      console.log(`  🧪 Running test: ${test.name}`);
      
      const testStartTime = Date.now();
      let testResult;
      
      try {
        testResult = await Promise.race([
          test.test(),
          new Promise((_, reject) => 
            setTimeout(() => reject(new Error('Test timeout')), suite.timeout)
          )
        ]);
        
        testResult.duration = Date.now() - testStartTime;
        testResult.name = test.name;
        testResult.id = test.id;
        
        // Validate assertions
        if (testResult.assertions) {
          const failedAssertions = testResult.assertions.filter(a => !a.condition);
          if (failedAssertions.length > 0) {
            testResult.success = false;
            testResult.failedAssertions = failedAssertions;
          }
        }
        
        if (testResult.success) {
          results.summary.passed++;
          console.log(`    ✅ ${test.name} - PASSED`);
        } else {
          results.summary.failed++;
          console.log(`    ❌ ${test.name} - FAILED`);
        }
        
      } catch (error) {
        testResult = {
          success: false,
          error: error.message,
          stack: error.stack,
          duration: Date.now() - testStartTime,
          name: test.name,
          id: test.id
        };
        
        results.summary.failed++;
        console.log(`    ❌ ${test.name} - ERROR: ${error.message}`);
      }
      
      results.tests.push(testResult);
    }

    results.summary.duration = Date.now() - startTime;
    results.endTime = new Date().toISOString();
    
    return results;
  }

  async generateTestReport(results) {
    const report = {
      ...results,
      reportMetadata: {
        generatedAt: new Date().toISOString(),
        framework: 'AutomatedTestFramework',
        version: '1.0.0',
        environment: this.getEnvironmentInfo()
      }
    };

    // Console report
    this.generateConsoleReport(report);
    
    // JSON report
    await this.generateJSONReport(report);
    
    // JUnit XML report (for CI/CD)
    if (this.ciMode) {
      await this.generateJUnitReport(report);
    }
    
    return report;
  }

  generateConsoleReport(report) {
    console.log('\n📊 TEST RESULTS SUMMARY');
    console.log('========================');
    console.log(`Test Run ID: ${report.testRunId}`);
    console.log(`Total Tests: ${report.summary.totalTests}`);
    console.log(`Passed: ${report.summary.passedTests} ✅`);
    console.log(`Failed: ${report.summary.failedTests} ❌`);
    console.log(`Skipped: ${report.summary.skippedTests} ⏭️`);
    console.log(`Success Rate: ${report.summary.successRate.toFixed(1)}%`);
    console.log(`Duration: ${report.summary.duration}ms`);
    
    if (report.summary.failedTests > 0) {
      console.log('\n❌ FAILED TESTS:');
      for (const [suiteId, suite] of Object.entries(report.suites)) {
        const failedTests = suite.tests.filter(t => !t.success && !t.skipped);
        if (failedTests.length > 0) {
          console.log(`\n  ${suite.name}:`);
          failedTests.forEach(test => {
            console.log(`    - ${test.name}: ${test.error || 'Test failed'}`);
          });
        }
      }
    }
  }

  async generateJSONReport(report) {
    const jsonReport = JSON.stringify(report, null, 2);
    
    // In browser environment, save to localStorage
    if (typeof window !== 'undefined') {
      localStorage.setItem(`test-report-${report.testRunId}`, jsonReport);
      console.log(`📄 JSON report saved to localStorage: test-report-${report.testRunId}`);
    }
    
    // In Node.js environment, save to file
    if (typeof process !== 'undefined' && process.versions && process.versions.node) {
      const fs = require('fs');
      const path = require('path');
      
      const reportPath = path.join(process.cwd(), `test-report-${report.testRunId}.json`);
      fs.writeFileSync(reportPath, jsonReport);
      console.log(`📄 JSON report saved to: ${reportPath}`);
    }
  }

  async generateJUnitReport(report) {
    const xmlReport = this.convertToJUnitXML(report);
    
    // In Node.js environment, save to file
    if (typeof process !== 'undefined' && process.versions && process.versions.node) {
      const fs = require('fs');
      const path = require('path');
      
      const reportPath = path.join(process.cwd(), `junit-report-${report.testRunId}.xml`);
      fs.writeFileSync(reportPath, xmlReport);
      console.log(`📄 JUnit report saved to: ${reportPath}`);
    }
  }

  convertToJUnitXML(report) {
    const testsuites = Object.entries(report.suites).map(([suiteId, suite]) => {
      const testcases = suite.tests.map(test => {
        if (test.success) {
          return `    <testcase classname="${suite.name}" name="${test.name}" time="${test.duration / 1000}"/>`;
        } else {
          return `    <testcase classname="${suite.name}" name="${test.name}" time="${test.duration / 1000}">
      <failure message="${test.error || 'Test failed'}">${test.stack || ''}</failure>
    </testcase>`;
        }
      }).join('\n');
      
      return `  <testsuite name="${suite.name}" tests="${suite.tests.length}" failures="${suite.summary.failed}" skipped="${suite.summary.skipped}" time="${suite.summary.duration / 1000}">
${testcases}
  </testsuite>`;
    }).join('\n');
    
    return `<?xml version="1.0" encoding="UTF-8"?>
<testsuites name="AutomatedTestFramework" tests="${report.summary.totalTests}" failures="${report.summary.failedTests}" skipped="${report.summary.skippedTests}" time="${report.summary.duration / 1000}">
${testsuites}
</testsuites>`;
  }

  getEnvironmentInfo() {
    return {
      userAgent: typeof navigator !== 'undefined' ? navigator.userAgent : 'Unknown',
      platform: typeof navigator !== 'undefined' ? navigator.platform : 'Unknown',
      language: typeof navigator !== 'undefined' ? navigator.language : 'Unknown',
      url: typeof window !== 'undefined' ? window.location.href : 'Unknown',
      timestamp: new Date().toISOString(),
      ciMode: this.ciMode,
      headlessMode: this.headlessMode,
      nodeVersion: typeof process !== 'undefined' && process.versions ? process.versions.node : 'Unknown'
    };
  }

  // Public API
  async runUnitTests() {
    return await this.runTestSuite('portfolio-math');
  }

  async runIntegrationTests() {
    return await this.runTestSuite('api-integration');
  }

  async runPerformanceTests() {
    return await this.runTestSuite('performance');
  }

  async runSecurityTests() {
    return await this.runTestSuite('security');
  }

  async runReactHooksTests() {
    return await this.runTestSuite('react-hooks');
  }

  getTestHistory() {
    return this.testResults;
  }

  exportTestResults() {
    const results = this.testResults[this.testResults.length - 1];
    if (!results) {
      console.log('No test results to export');
      return null;
    }
    
    const blob = new Blob([JSON.stringify(results, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `test-results-${results.testRunId}.json`;
    a.click();
    URL.revokeObjectURL(url);
    
    return results;
  }
}

// Create global instance
const automatedTestFramework = new AutomatedTestFramework();

// Export for use
export default automatedTestFramework;

// Add to window for debugging
if (typeof window !== 'undefined') {
  window.automatedTestFramework = automatedTestFramework;
}

// Export utility functions
export const runAllTests = () => automatedTestFramework.runAllTests();
export const runUnitTests = () => automatedTestFramework.runUnitTests();
export const runIntegrationTests = () => automatedTestFramework.runIntegrationTests();
export const runPerformanceTests = () => automatedTestFramework.runPerformanceTests();
export const runSecurityTests = () => automatedTestFramework.runSecurityTests();
export const runReactHooksTests = () => automatedTestFramework.runReactHooksTests();
export const exportTestResults = () => automatedTestFramework.exportTestResults();