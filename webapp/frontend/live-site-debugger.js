#!/usr/bin/env node

const playwright = require('playwright');
const fs = require('fs').promises;

/**
 * LIVE SITE DEBUGGER
 * Specifically designed to debug your production site remotely
 * Provides deep F12 developer tools insight
 */

class LiveSiteDebugger {
  constructor(productionUrl) {
    this.productionUrl = productionUrl;
    this.browser = null;
    this.context = null;
    this.page = null;
    this.targetErrors = [];
    this.allLogs = [];
  }

  async init() {
    console.log('🌐 LIVE SITE DEBUGGER - Starting...');
    console.log(`🎯 Production URL: ${this.productionUrl}`);
    
    // Launch browser with debugging capabilities
    this.browser = await playwright.chromium.launch({
      headless: false,
      devtools: true,
      args: [
        '--auto-open-devtools-for-tabs',
        '--disable-web-security',
        '--allow-running-insecure-content'
      ]
    });

    this.context = await this.browser.newContext({
      viewport: { width: 1920, height: 1080 },
      // Clear cache to see fresh errors
      storageState: undefined
    });

    this.page = await this.context.newPage();
    
    // Enable all console API calls
    await this.page.addInitScript(() => {
      // Capture all console methods
      const originalLog = console.log;
      const originalError = console.error;
      const originalWarn = console.warn;
      
      window.__DEBUG_LOGS__ = [];
      
      console.log = (...args) => {
        window.__DEBUG_LOGS__.push({type: 'log', args, timestamp: Date.now()});
        originalLog.apply(console, args);
      };
      
      console.error = (...args) => {
        window.__DEBUG_LOGS__.push({type: 'error', args, timestamp: Date.now()});
        originalError.apply(console, args);
      };
      
      console.warn = (...args) => {
        window.__DEBUG_LOGS__.push({type: 'warn', args, timestamp: Date.now()});
        originalWarn.apply(console, args);
      };
    });
    
    this.setupErrorCapture();
    this.setupNetworkMonitoring();
    
    console.log('✅ Live site debugger initialized');
  }

  setupErrorCapture() {
    // Capture page errors (uncaught exceptions)
    this.page.on('pageerror', error => {
      const errorData = {
        type: 'uncaught_exception',
        message: error.message,
        stack: error.stack,
        timestamp: new Date().toISOString(),
        isTarget: this.isUseSyncExternalStoreError(error.message + ' ' + error.stack)
      };
      
      this.targetErrors.push(errorData);
      console.log('🚨 UNCAUGHT EXCEPTION:');
      console.log(JSON.stringify(errorData, null, 2));
    });

    // Capture console messages
    this.page.on('console', msg => {
      const logData = {
        type: msg.type(),
        text: msg.text(),
        location: msg.location(),
        timestamp: new Date().toISOString(),
        isTarget: this.isUseSyncExternalStoreError(msg.text())
      };
      
      this.allLogs.push(logData);
      
      if (msg.type() === 'error' || logData.isTarget) {
        console.log(`📝 CONSOLE ${msg.type().toUpperCase()}: ${msg.text()}`);
        
        if (logData.isTarget) {
          this.targetErrors.push(logData);
        }
      }
    });
  }

  setupNetworkMonitoring() {
    this.page.on('response', response => {
      const url = response.url();
      
      // Look for any sync-external-store related files
      if (url.includes('sync-external-store') || url.includes('shim')) {
        console.log(`🌐 SUSPICIOUS REQUEST: ${url} - Status: ${response.status()}`);
        
        this.targetErrors.push({
          type: 'suspicious_network_request',
          url: url,
          status: response.status(),
          headers: response.headers(),
          timestamp: new Date().toISOString(),
          isTarget: true
        });
      }
      
      if (response.status() >= 400) {
        console.log(`❌ FAILED REQUEST: ${url} - ${response.status()}`);
      }
    });
  }

  isUseSyncExternalStoreError(text) {
    const patterns = [
      'use-sync-external-store-shim.production.js:17',
      'Cannot read properties of undefined (reading \'useState\')',
      'useSyncExternalStore',
      'useState',
      'sync-external-store'
    ];
    
    return patterns.some(pattern => 
      text.toLowerCase().includes(pattern.toLowerCase())
    );
  }

  async loadProductionSite() {
    console.log(`📡 Loading production site: ${this.productionUrl}`);
    
    try {
      // Clear browser cache first
      await this.context.clearCookies();
      
      // Navigate to production site
      const response = await this.page.goto(this.productionUrl, {
        waitUntil: 'networkidle',
        timeout: 30000
      });
      
      console.log(`✅ Production site loaded - Status: ${response.status()}`);
      
      // Wait for potential errors to surface
      console.log('⏳ Waiting for React initialization and potential errors...');
      await this.page.waitForTimeout(10000);
      
      // Check if the target error occurred
      await this.checkForTargetError();
      
    } catch (error) {
      console.error('❌ Failed to load production site:', error.message);
      this.targetErrors.push({
        type: 'page_load_error',
        message: error.message,
        stack: error.stack,
        timestamp: new Date().toISOString(),
        isTarget: false
      });
    }
  }

  async checkForTargetError() {
    console.log('🔍 Checking for target useState error...');
    
    // Get all console logs from the page
    const debugLogs = await this.page.evaluate(() => {
      return window.__DEBUG_LOGS__ || [];
    });
    
    console.log(`📊 Found ${debugLogs.length} console messages`);
    
    // Check for our specific error pattern
    const hasTargetError = debugLogs.some(log => 
      JSON.stringify(log.args).includes('use-sync-external-store-shim.production.js:17') &&
      JSON.stringify(log.args).includes('Cannot read properties of undefined')
    );
    
    if (hasTargetError) {
      console.log('🎯 TARGET ERROR DETECTED IN CONSOLE LOGS!');
      const targetLogs = debugLogs.filter(log => 
        JSON.stringify(log.args).includes('use-sync-external-store-shim') ||
        JSON.stringify(log.args).includes('Cannot read properties of undefined')
      );
      
      console.log('🚨 EXACT ERROR LOGS:');
      targetLogs.forEach(log => {
        console.log(JSON.stringify(log, null, 2));
      });
      
      return true;
    }
    
    console.log('❓ Target error not detected in this session');
    return false;
  }

  async analyzePageState() {
    console.log('🔍 Analyzing page state...');
    
    const pageAnalysis = await this.page.evaluate(() => {
      const analysis = {
        url: window.location.href,
        title: document.title,
        hasRoot: !!document.getElementById('root'),
        rootContent: document.getElementById('root')?.innerHTML?.substring(0, 200) || 'NO ROOT',
        scriptsCount: document.scripts.length,
        scripts: Array.from(document.scripts).map(s => s.src).filter(src => src),
        hasReact: typeof window.React !== 'undefined',
        hasConfig: typeof window.__CONFIG__ !== 'undefined',
        errorMessages: [],
        timestamp: new Date().toISOString()
      };
      
      // Look for any error indicators in the DOM
      const errorElements = document.querySelectorAll('[class*="error"], [id*="error"], .error-boundary');
      if (errorElements.length > 0) {
        analysis.errorMessages = Array.from(errorElements).map(el => el.textContent?.substring(0, 100));
      }
      
      return analysis;
    });
    
    console.log('📊 PAGE ANALYSIS:');
    console.log(JSON.stringify(pageAnalysis, null, 2));
    
    return pageAnalysis;
  }

  async captureNetworkTrace() {
    console.log('🌐 Starting network trace...');
    
    // Reload page to capture full network activity
    await this.page.reload({ waitUntil: 'networkidle' });
    await this.page.waitForTimeout(5000);
    
    console.log('✅ Network trace completed');
  }

  async generateLiveReport() {
    const pageAnalysis = await this.analyzePageState();
    
    const report = {
      timestamp: new Date().toISOString(),
      productionUrl: this.productionUrl,
      summary: {
        targetErrorsFound: this.targetErrors.length,
        totalLogsCount: this.allLogs.length,
        errorLogsCount: this.allLogs.filter(log => log.type === 'error').length,
        hasUseSyncExternalStoreError: this.targetErrors.some(err => err.isTarget)
      },
      targetErrors: this.targetErrors,
      pageAnalysis: pageAnalysis,
      errorLogs: this.allLogs.filter(log => log.type === 'error'),
      allLogs: this.allLogs
    };
    
    const reportFile = `live-debug-report-${Date.now()}.json`;
    await fs.writeFile(reportFile, JSON.stringify(report, null, 2));
    
    console.log('\n📋 LIVE DEBUGGING REPORT:');
    console.log(`📁 Report file: ${reportFile}`);
    console.log(`🎯 Target errors found: ${report.summary.targetErrorsFound}`);
    console.log(`❌ Total error logs: ${report.summary.errorLogsCount}`);
    console.log(`🚨 useState error detected: ${report.summary.hasUseSyncExternalStoreError}`);
    
    if (report.summary.hasUseSyncExternalStoreError) {
      console.log('\n✅ SUCCESS: useState error successfully captured from production site!');
      console.log('🔍 Check the report file for detailed error information.');
    } else {
      console.log('\n❓ Target error not detected - may need multiple attempts or different timing');
    }
    
    return report;
  }

  async interactiveMode() {
    console.log('\n🎮 INTERACTIVE MODE - Browser is open for manual inspection');
    console.log('🔍 You can now use F12 developer tools manually');
    console.log('📊 Monitor console for real-time error detection');
    console.log('🔄 Try refreshing the page multiple times to trigger the error');
    console.log('⏹️  Press Ctrl+C when done to generate final report\n');
    
    return new Promise((resolve) => {
      process.on('SIGINT', async () => {
        console.log('\n📊 Generating final live site report...');
        const report = await this.generateLiveReport();
        await this.close();
        resolve(report);
      });
    });
  }

  async close() {
    if (this.browser) {
      await this.browser.close();
    }
  }
}

// Main execution
async function main() {
  // Replace this with your actual production URL
  const productionUrl = process.argv[2] || 'https://your-production-site.com';
  
  console.log('🌐 LIVE SITE DEBUGGER');
  console.log('=====================');
  console.log(`Target: ${productionUrl}`);
  console.log('');
  
  const debugger = new LiveSiteDebugger(productionUrl);
  
  try {
    await debugger.init();
    await debugger.loadProductionSite();
    await debugger.captureNetworkTrace();
    
    // Enter interactive mode
    const report = await debugger.interactiveMode();
    
    if (report.summary.hasUseSyncExternalStoreError) {
      console.log('🎯 Mission accomplished - error captured!');
      process.exit(0);
    } else {
      console.log('❓ Error not captured this time');
      process.exit(1);
    }
    
  } catch (error) {
    console.error('💥 Live site debugger failed:', error);
    await debugger.close();
    process.exit(2);
  }
}

if (require.main === module) {
  main();
}

module.exports = LiveSiteDebugger;