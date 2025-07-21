#!/usr/bin/env node

const puppeteer = require('puppeteer');
const fs = require('fs').promises;

/**
 * REMOTE DEBUGGING SUITE
 * Comprehensive tool to analyze production site F12 developer tools remotely
 */

class RemoteDebugger {
  constructor(targetUrl) {
    this.targetUrl = targetUrl;
    this.browser = null;
    this.page = null;
    this.errors = [];
    this.networkRequests = [];
    this.consoleMessages = [];
  }

  async init() {
    console.log('🔍 REMOTE DEBUGGING SUITE STARTING...');
    console.log(`🎯 Target URL: ${this.targetUrl}`);
    
    this.browser = await puppeteer.launch({
      headless: false, // Set to false so you can see what's happening
      devtools: true,  // Open DevTools automatically
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-web-security',
        '--disable-features=VizDisplayCompositor',
        '--remote-debugging-port=9222'
      ]
    });

    this.page = await this.browser.newPage();
    
    // Enable all debugging features
    await this.page.setViewport({ width: 1920, height: 1080 });
    
    // Set up error capture
    this.setupErrorCapture();
    this.setupNetworkMonitoring();
    this.setupConsoleMonitoring();
    
    console.log('✅ Remote debugger initialized');
    console.log('🌐 Remote debugging port: 9222');
    console.log('📊 DevTools will open automatically');
  }

  setupErrorCapture() {
    // Capture JavaScript errors
    this.page.on('pageerror', error => {
      const errorData = {
        type: 'javascript_error',
        message: error.message,
        stack: error.stack,
        timestamp: new Date().toISOString(),
        isTarget: this.isTargetError(error.message + ' ' + error.stack)
      };
      
      this.errors.push(errorData);
      
      if (errorData.isTarget) {
        console.log('🚨 TARGET ERROR DETECTED:');
        console.log(JSON.stringify(errorData, null, 2));
      }
    });

    // Capture unhandled promise rejections
    this.page.on('console', async msg => {
      if (msg.type() === 'error') {
        const errorData = {
          type: 'console_error',
          text: msg.text(),
          location: msg.location(),
          timestamp: new Date().toISOString(),
          isTarget: this.isTargetError(msg.text())
        };
        
        this.errors.push(errorData);
        
        if (errorData.isTarget) {
          console.log('🎯 CONSOLE ERROR (TARGET):');
          console.log(JSON.stringify(errorData, null, 2));
        }
      }
    });
  }

  setupNetworkMonitoring() {
    // Monitor all network requests
    this.page.on('request', request => {
      const url = request.url();
      if (this.isTargetRequest(url)) {
        console.log(`📡 TARGET REQUEST: ${url}`);
      }
    });

    this.page.on('response', response => {
      const requestData = {
        url: response.url(),
        status: response.status(),
        statusText: response.statusText(),
        headers: response.headers(),
        timestamp: new Date().toISOString(),
        isTarget: this.isTargetRequest(response.url())
      };
      
      this.networkRequests.push(requestData);
      
      if (requestData.isTarget || requestData.status >= 400) {
        console.log(`🌐 NETWORK ${requestData.status}: ${requestData.url}`);
      }
    });

    this.page.on('requestfailed', request => {
      const failureData = {
        type: 'network_failure',
        url: request.url(),
        failure: request.failure()?.errorText || 'Unknown failure',
        timestamp: new Date().toISOString(),
        isTarget: this.isTargetRequest(request.url())
      };
      
      this.errors.push(failureData);
      console.log('❌ NETWORK FAILURE:', JSON.stringify(failureData, null, 2));
    });
  }

  setupConsoleMonitoring() {
    this.page.on('console', msg => {
      const consoleData = {
        type: msg.type(),
        text: msg.text(),
        location: msg.location(),
        timestamp: new Date().toISOString(),
        isTarget: this.isTargetMessage(msg.text())
      };
      
      this.consoleMessages.push(consoleData);
      
      if (consoleData.isTarget) {
        console.log(`📝 CONSOLE (${consoleData.type.toUpperCase()}): ${consoleData.text}`);
      }
    });
  }

  isTargetError(errorText) {
    const targetPatterns = [
      'use-sync-external-store',
      'useState',
      'useSyncExternalStore',
      'shim',
      'Cannot read properties of undefined'
    ];
    
    return targetPatterns.some(pattern => 
      errorText.toLowerCase().includes(pattern.toLowerCase())
    );
  }

  isTargetRequest(url) {
    const targetPatterns = [
      'sync-external-store',
      'shim',
      'use-sync',
      '.production.js'
    ];
    
    return targetPatterns.some(pattern => 
      url.toLowerCase().includes(pattern.toLowerCase())
    );
  }

  isTargetMessage(message) {
    return this.isTargetError(message) || message.includes('🚨') || message.includes('ERROR');
  }

  async loadSite() {
    console.log(`📡 Loading site: ${this.targetUrl}`);
    
    try {
      const response = await this.page.goto(this.targetUrl, { 
        waitUntil: 'networkidle2',
        timeout: 30000 
      });
      
      console.log(`✅ Page loaded with status: ${response.status()}`);
      
      // Wait for React to initialize
      console.log('⏳ Waiting for React initialization...');
      await this.page.waitForTimeout(5000);
      
      // Try to detect if React loaded successfully
      const reactLoaded = await this.page.evaluate(() => {
        return typeof window.React !== 'undefined' || 
               document.querySelector('[data-reactroot]') !== null ||
               document.getElementById('root').children.length > 0;
      });
      
      console.log(`⚛️ React loaded: ${reactLoaded}`);
      
    } catch (error) {
      console.error('❌ Failed to load site:', error.message);
      this.errors.push({
        type: 'page_load_failure',
        message: error.message,
        stack: error.stack,
        timestamp: new Date().toISOString(),
        isTarget: true
      });
    }
  }

  async runDiagnostics() {
    console.log('🔍 Running comprehensive diagnostics...');
    
    // Check for specific DOM elements
    const diagnostics = await this.page.evaluate(() => {
      const results = {
        hasRoot: !!document.getElementById('root'),
        rootContent: document.getElementById('root')?.innerHTML?.substring(0, 500) || 'NO ROOT',
        reactPresent: typeof window.React !== 'undefined',
        configPresent: typeof window.__CONFIG__ !== 'undefined',
        errorBoundaryActive: document.querySelector('.error-boundary') !== null,
        scriptsLoaded: Array.from(document.scripts).map(script => ({
          src: script.src,
          loaded: script.readyState === 'complete'
        })),
        stylesheets: Array.from(document.styleSheets).length,
        timestamp: new Date().toISOString()
      };
      
      return results;
    });
    
    console.log('📊 PAGE DIAGNOSTICS:');
    console.log(JSON.stringify(diagnostics, null, 2));
    
    return diagnostics;
  }

  async captureScreenshot(filename = 'debug-screenshot.png') {
    console.log(`📸 Capturing screenshot: ${filename}`);
    await this.page.screenshot({ 
      path: filename,
      fullPage: true 
    });
    console.log(`✅ Screenshot saved: ${filename}`);
  }

  async generateReport() {
    const report = {
      timestamp: new Date().toISOString(),
      targetUrl: this.targetUrl,
      summary: {
        totalErrors: this.errors.length,
        targetErrors: this.errors.filter(e => e.isTarget).length,
        networkRequests: this.networkRequests.length,
        failedRequests: this.networkRequests.filter(r => r.status >= 400).length,
        consoleMessages: this.consoleMessages.length
      },
      targetErrors: this.errors.filter(e => e.isTarget),
      allErrors: this.errors,
      suspiciousRequests: this.networkRequests.filter(r => r.isTarget || r.status >= 400),
      diagnostics: await this.runDiagnostics()
    };
    
    const reportFile = `debug-report-${Date.now()}.json`;
    await fs.writeFile(reportFile, JSON.stringify(report, null, 2));
    
    console.log('\n📋 DEBUGGING REPORT GENERATED:');
    console.log(`📁 Report file: ${reportFile}`);
    console.log(`🚨 Target errors: ${report.summary.targetErrors}`);
    console.log(`❌ Total errors: ${report.summary.totalErrors}`);
    console.log(`🌐 Failed requests: ${report.summary.failedRequests}`);
    
    return report;
  }

  async keepAlive() {
    console.log('\n🔄 INTERACTIVE MODE ACTIVATED');
    console.log('📊 Browser and DevTools are now open for manual inspection');
    console.log('🎯 Monitor the console for real-time error detection');
    console.log('⏹️  Press Ctrl+C to exit and generate final report\n');
    
    // Keep the process alive
    return new Promise((resolve) => {
      process.on('SIGINT', async () => {
        console.log('\n📊 Generating final report...');
        const report = await this.generateReport();
        await this.captureScreenshot('final-debug-screenshot.png');
        await this.browser.close();
        console.log('✅ Remote debugging session completed');
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
  const targetUrl = process.argv[2] || 'http://localhost:8080';
  
  const remoteDebugger = new RemoteDebugger(targetUrl);
  
  try {
    await remoteDebugger.init();
    await remoteDebugger.loadSite();
    await remoteDebugger.captureScreenshot('initial-load.png');
    const report = await remoteDebugger.keepAlive();
    
    // Final analysis
    if (report.summary.targetErrors > 0) {
      console.log('\n🎯 SUCCESS: Target errors detected and captured!');
      process.exit(0);
    } else {
      console.log('\n❓ No target errors found - may be environment specific');
      process.exit(1);
    }
    
  } catch (error) {
    console.error('💥 Remote debugger failed:', error);
    await remoteDebugger.close();
    process.exit(2);
  }
}

if (require.main === module) {
  main();
}

module.exports = RemoteDebugger;