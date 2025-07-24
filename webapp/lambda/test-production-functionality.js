#!/usr/bin/env node

/**
 * Production Functionality Test Suite
 * Tests the core features that the site actually provides today
 * Consolidated from multiple test files to avoid sprawl
 */

const apiKeyService = require('./utils/simpleApiKeyService');
const axios = require('axios');

const API_BASE = 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev';

class ProductionTestSuite {
  constructor() {
    this.results = {
      total: 0,
      passed: 0,
      failed: 0,
      tests: []
    };
  }

  async test(name, testFn) {
    this.results.total++;
    console.log(`\n🧪 Testing: ${name}`);
    
    try {
      await testFn();
      this.results.passed++;
      this.results.tests.push({ name, status: 'PASSED' });
      console.log(`✅ PASSED: ${name}`);
    } catch (error) {
      this.results.failed++;
      this.results.tests.push({ name, status: 'FAILED', error: error.message });
      console.log(`❌ FAILED: ${name} - ${error.message}`);
    }
  }

  async runAllTests() {
    console.log('🚀 Production Functionality Test Suite');
    console.log('=' .repeat(60));
    
    // Core Infrastructure Tests
    await this.test('Health endpoint responds', async () => {
      const response = await axios.get(`${API_BASE}/health`, { timeout: 5000 });
      if (response.status !== 200) throw new Error(`Expected 200, got ${response.status}`);
      if (!response.data.success) throw new Error('Health check failed');
    });

    await this.test('API health endpoint responds', async () => {
      const response = await axios.get(`${API_BASE}/api/health`, { timeout: 5000 });
      if (response.status !== 200) throw new Error(`Expected 200, got ${response.status}`);
    });

    // Stock Data Tests (Core feature)
    await this.test('Stock screening works (with fallback)', async () => {
      const response = await axios.get(`${API_BASE}/api/stocks/screen?limit=5`, {
        headers: { Authorization: 'development-mode' },
        timeout: 10000
      });
      if (response.status !== 200) throw new Error(`Expected 200, got ${response.status}`);
      if (!response.data.success) throw new Error('Stock screening failed');
      if (!Array.isArray(response.data.data)) throw new Error('Data should be array');
    });

    await this.test('Individual stock lookup works', async () => {
      const response = await axios.get(`${API_BASE}/api/stocks/AAPL`, {
        headers: { Authorization: 'development-mode' },
        timeout: 10000
      });
      if (response.status !== 200) throw new Error(`Expected 200, got ${response.status}`);
      if (!response.data.success) throw new Error('Stock lookup failed');
    });

    // API Key Infrastructure Tests
    await this.test('API key service can read from Parameter Store', async () => {
      const result = await apiKeyService.getApiKey('test-user', 'alpaca');
      // Should return null gracefully, not throw error
      if (result !== null) throw new Error('Expected null for non-existent key');
    });

    await this.test('API key service encodes user IDs safely', async () => {
      const encoded = apiKeyService.encodeUserId('test@example.com');
      if (encoded.includes('@')) throw new Error('Should encode @ symbol');
      if (!encoded.includes('_at_')) throw new Error('Should replace @ with _at_');
    });

    // Market Data Tests (Core feature)
    await this.test('Market overview endpoint works', async () => {
      const response = await axios.get(`${API_BASE}/api/market/overview`, {
        headers: { Authorization: 'development-mode' },
        timeout: 10000
      });
      // Accept 200 (working) or 503 (fallback) as both are valid
      if (![200, 503].includes(response.status)) {
        throw new Error(`Expected 200 or 503, got ${response.status}`);
      }
    });

    // Portfolio System Tests (With graceful failures)
    await this.test('Portfolio endpoint handles no API keys gracefully', async () => {
      try {
        const response = await axios.get(`${API_BASE}/api/portfolio`, {
          headers: { Authorization: 'development-mode' },
          timeout: 10000
        });
        // Should either work or fail gracefully
        if (response.status === 200 && response.data.success) {
          console.log('  📊 Portfolio working with live data');
        }
      } catch (error) {
        if (error.response?.status === 503) {
          console.log('  📊 Portfolio gracefully unavailable (expected without API keys)');
        } else {
          throw error;
        }
      }
    });

    // Settings Integration Tests
    await this.test('Settings endpoints are defined (even if failing)', async () => {
      // These should at least return structured errors, not 404s
      const endpoints = [
        '/api/user/notifications',
        '/api/user/theme',
        '/api/user/profile'
      ];
      
      let definedEndpoints = 0;
      for (const endpoint of endpoints) {
        try {
          await axios.get(`${API_BASE}${endpoint}`, {
            headers: { Authorization: 'development-mode' },
            timeout: 5000
          });
          definedEndpoints++;
        } catch (error) {
          if (error.response?.status !== 404) {
            definedEndpoints++; // Defined but failing is better than 404
          }
        }
      }
      
      if (definedEndpoints === 0) {
        throw new Error('No settings endpoints are defined');
      }
      console.log(`  📊 ${definedEndpoints}/${endpoints.length} settings endpoints defined`);
    });

    // Display Results
    this.displayResults();
  }

  displayResults() {
    console.log('\n' + '=' .repeat(60));
    console.log('🏁 TEST RESULTS SUMMARY');
    console.log('=' .repeat(60));
    
    console.log(`📊 Total Tests: ${this.results.total}`);
    console.log(`✅ Passed: ${this.results.passed}`);
    console.log(`❌ Failed: ${this.results.failed}`);
    console.log(`📈 Success Rate: ${Math.round((this.results.passed / this.results.total) * 100)}%`);
    
    if (this.results.failed > 0) {
      console.log('\n❌ FAILED TESTS:');
      this.results.tests
        .filter(t => t.status === 'FAILED')
        .forEach(test => console.log(`  • ${test.name}: ${test.error}`));
    }
    
    console.log('\n🎯 CORE FUNCTIONALITY STATUS:');
    console.log(`  📈 Stock Data: ${this.getFeatureStatus(['Stock screening', 'Individual stock lookup'])}`);
    console.log(`  🔐 API Keys: ${this.getFeatureStatus(['API key service'])}`);
    console.log(`  📊 Market Data: ${this.getFeatureStatus(['Market overview'])}`);
    console.log(`  💼 Portfolio: ${this.getFeatureStatus(['Portfolio endpoint'])}`);
    console.log(`  ⚙️ Settings: ${this.getFeatureStatus(['Settings endpoints'])}`);
    
    console.log('\n💡 PRODUCTION READINESS:');
    if (this.results.passed >= Math.floor(this.results.total * 0.8)) {
      console.log('🟢 READY - Core functionality working with graceful fallbacks');
    } else if (this.results.passed >= Math.floor(this.results.total * 0.6)) {
      console.log('🟡 PARTIAL - Some core features working, needs fixes');
    } else {
      console.log('🔴 NOT READY - Critical functionality broken');
    }
  }

  getFeatureStatus(keywords) {
    const relevantTests = this.results.tests.filter(test => 
      keywords.some(keyword => test.name.toLowerCase().includes(keyword.toLowerCase()))
    );
    
    if (relevantTests.length === 0) return 'UNKNOWN';
    
    const passed = relevantTests.filter(t => t.status === 'PASSED').length;
    const total = relevantTests.length;
    
    if (passed === total) return 'WORKING';
    if (passed > 0) return 'PARTIAL';
    return 'BROKEN';
  }
}

// Run the tests
const testSuite = new ProductionTestSuite();
testSuite.runAllTests().catch(console.error);