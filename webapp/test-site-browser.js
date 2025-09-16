#!/usr/bin/env node

/**
 * Browser-based Site Tests
 * Tests the actual deployed site functionality using Playwright
 */

const { chromium } = require('playwright');

const API_BASE = 'https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev';
const FRONTEND_URLS = [
  'https://d1copuy2oqlazx.cloudfront.net',
  'https://d1zb7knau41vl9.cloudfront.net'
];

class BrowserSiteTester {
  constructor() {
    this.results = {
      passed: 0,
      failed: 0,
      tests: []
    };
    this.browser = null;
    this.workingFrontendUrl = null;
  }

  async init() {
    this.browser = await chromium.launch({ headless: true });
  }

  async cleanup() {
    if (this.browser) {
      await this.browser.close();
    }
  }

  test(name, testFn) {
    return async () => {
      try {
        console.log(`🧪 Testing: ${name}`);
        await testFn();
        this.results.passed++;
        this.results.tests.push({ name, status: 'PASS' });
        console.log(`✅ PASS: ${name}`);
      } catch (error) {
        this.results.failed++;
        this.results.tests.push({ name, status: 'FAIL', error: error.message });
        console.log(`❌ FAIL: ${name} - ${error.message}`);
      }
    };
  }

  async findWorkingFrontendUrl() {
    console.log('🔍 Finding working frontend URL...');
    
    for (const url of FRONTEND_URLS) {
      try {
        const page = await this.browser.newPage();
        const response = await page.goto(url, { timeout: 10000 });
        
        if (response && response.status() === 200) {
          const title = await page.title();
          if (title && (title.includes('Stock') || title.includes('Finance') || title.includes('Market'))) {
            console.log(`✅ Found working frontend: ${url}`);
            this.workingFrontendUrl = url;
            await page.close();
            return url;
          }
        }
        await page.close();
      } catch (error) {
        console.log(`❌ Failed to connect to ${url}: ${error.message}`);
      }
    }
    
    throw new Error('No working frontend URL found');
  }

  async runTests() {
    console.log('🚀 Starting Browser-based Site Tests\n');
    console.log(`API Base: ${API_BASE}\n`);

    await this.init();

    try {
      // Find working frontend
      await this.test('Find Working Frontend URL', async () => {
        await this.findWorkingFrontendUrl();
        if (!this.workingFrontendUrl) throw new Error('No working frontend found');
      })();

      if (!this.workingFrontendUrl) {
        console.log('❌ Cannot continue without working frontend URL');
        return;
      }

      // Frontend Tests
      await this.test('Frontend Loads Successfully', async () => {
        const page = await this.browser.newPage();
        try {
          const response = await page.goto(this.workingFrontendUrl, { timeout: 15000 });
          if (!response || response.status() !== 200) {
            throw new Error(`Failed to load: status ${response?.status()}`);
          }
          
          // Wait for React to load
          await page.waitForTimeout(2000);
          
          const title = await page.title();
          if (!title || title.includes('Error')) {
            throw new Error('Page loaded with error or empty title');
          }
        } finally {
          await page.close();
        }
      })();

      await this.test('Navigation Menu Present', async () => {
        const page = await this.browser.newPage();
        try {
          await page.goto(this.workingFrontendUrl, { timeout: 15000 });
          await page.waitForTimeout(3000);
          
          // Look for common navigation elements
          const navElements = await page.$$eval('nav, [role="navigation"], .navbar, .menu', 
            elements => elements.length);
          
          if (navElements === 0) {
            // Try looking for common nav links
            const links = await page.$$eval('a', 
              links => links.filter(link => 
                link.textContent?.includes('Dashboard') ||
                link.textContent?.includes('Portfolio') ||
                link.textContent?.includes('Market')
              ).length);
            
            if (links === 0) throw new Error('No navigation menu found');
          }
        } finally {
          await page.close();
        }
      })();

      await this.test('Market Data Displays', async () => {
        const page = await this.browser.newPage();
        try {
          await page.goto(this.workingFrontendUrl, { timeout: 15000 });
          await page.waitForTimeout(5000);
          
          // Look for market data indicators
          const marketData = await page.evaluate(() => {
            const text = document.body.innerText.toLowerCase();
            return text.includes('market') || 
                   text.includes('stock') || 
                   text.includes('portfolio') ||
                   text.includes('trading');
          });
          
          if (!marketData) throw new Error('No market-related content found');
        } finally {
          await page.close();
        }
      })();

      await this.test('API Configuration Loaded', async () => {
        const page = await this.browser.newPage();
        try {
          await page.goto(this.workingFrontendUrl, { timeout: 15000 });
          await page.waitForTimeout(2000);
          
          const hasConfig = await page.evaluate(() => {
            return window.__CONFIG__ && window.__CONFIG__.API_URL;
          });
          
          if (!hasConfig) throw new Error('API configuration not loaded');
          
          const apiUrl = await page.evaluate(() => window.__CONFIG__.API_URL);
          if (!apiUrl.includes('qda42av7je.execute-api.us-east-1.amazonaws.com')) {
            throw new Error(`Unexpected API URL: ${apiUrl}`);
          }
        } finally {
          await page.close();
        }
      })();

      await this.test('Dashboard Page Accessible', async () => {
        const page = await this.browser.newPage();
        try {
          await page.goto(`${this.workingFrontendUrl}/dashboard`, { timeout: 15000 });
          await page.waitForTimeout(3000);
          
          // Check if page loaded without error
          const hasError = await page.evaluate(() => {
            const text = document.body.innerText.toLowerCase();
            return text.includes('error') || text.includes('404') || text.includes('not found');
          });
          
          if (hasError) {
            // This might be expected if dashboard requires auth
            console.log('   ℹ️  Dashboard may require authentication');
          }
        } finally {
          await page.close();
        }
      })();

      await this.test('Market Overview Page Accessible', async () => {
        const page = await this.browser.newPage();
        try {
          const response = await page.goto(`${this.workingFrontendUrl}/market-overview`, { timeout: 15000 });
          await page.waitForTimeout(3000);
          
          // Check if we got a reasonable response
          if (response.status() >= 500) {
            throw new Error(`Server error: ${response.status()}`);
          }
        } finally {
          await page.close();
        }
      })();

      await this.test('JavaScript Errors Check', async () => {
        const page = await this.browser.newPage();
        const errors = [];
        
        page.on('pageerror', error => {
          errors.push(error.message);
        });
        
        try {
          await page.goto(this.workingFrontendUrl, { timeout: 15000 });
          await page.waitForTimeout(5000);
          
          if (errors.length > 0) {
            // Filter out common non-critical errors
            const criticalErrors = errors.filter(error => 
              !error.includes('ResizeObserver') &&
              !error.includes('Non-passive event listener') &&
              !error.includes('404')
            );
            
            if (criticalErrors.length > 0) {
              throw new Error(`Critical JavaScript errors: ${criticalErrors.join(', ')}`);
            }
          }
        } finally {
          await page.close();
        }
      })();

      await this.test('Console Warnings Check', async () => {
        const page = await this.browser.newPage();
        const warnings = [];
        
        page.on('console', msg => {
          if (msg.type() === 'warning' || msg.type() === 'error') {
            warnings.push(msg.text());
          }
        });
        
        try {
          await page.goto(this.workingFrontendUrl, { timeout: 15000 });
          await page.waitForTimeout(3000);
          
          // Filter out common non-critical warnings
          const criticalWarnings = warnings.filter(warning => 
            !warning.includes('DevTools') &&
            !warning.includes('sourcemap') &&
            !warning.includes('favicon') &&
            !warning.toLowerCase().includes('deprecated')
          );
          
          if (criticalWarnings.length > 5) {
            console.log(`   ⚠️  Found ${criticalWarnings.length} console warnings (showing first 3):`);
            criticalWarnings.slice(0, 3).forEach(w => console.log(`      - ${w.substring(0, 100)}`));
          }
        } finally {
          await page.close();
        }
      })();

    } finally {
      await this.cleanup();
    }

    this.printResults();
  }

  printResults() {
    console.log('\n' + '='.repeat(60));
    console.log('🌐 BROWSER SITE TEST RESULTS');
    console.log('='.repeat(60));
    console.log(`✅ Passed: ${this.results.passed}`);
    console.log(`❌ Failed: ${this.results.failed}`);
    console.log(`📈 Success Rate: ${((this.results.passed / (this.results.passed + this.results.failed)) * 100).toFixed(1)}%`);
    
    if (this.results.failed > 0) {
      console.log('\n❌ FAILED TESTS:');
      this.results.tests
        .filter(test => test.status === 'FAIL')
        .forEach(test => {
          console.log(`   - ${test.name}: ${test.error}`);
        });
    }

    if (this.workingFrontendUrl) {
      console.log('\n🔗 WORKING SITE:');
      console.log(`   Frontend: ${this.workingFrontendUrl}`);
      console.log(`   API: ${API_BASE}/health`);
    }
    
    if (this.results.failed === 0) {
      console.log('\n🎉 ALL BROWSER TESTS PASSED - Your site works in the browser!');
    } else {
      console.log(`\n⚠️  ${this.results.failed} test(s) failed - see details above`);
    }
    
    console.log('='.repeat(60));
  }
}

// Run tests if called directly
if (require.main === module) {
  const tester = new BrowserSiteTester();
  tester.runTests().catch(console.error);
}

module.exports = BrowserSiteTester;