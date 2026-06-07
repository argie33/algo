import { chromium } from 'playwright';
import fs from 'fs';

const RESULTS = {
  consoleErrors: [],
  consoleWarnings: [],
  networkErrors: [],
  networkTimeouts: [],
  pageErrors: [],
  unhandledRejections: [],
  apiErrors: [],
  cssErrors: [],
  scriptErrors: [],
};

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  // Track all console messages
  page.on('console', (msg) => {
    const logData = {
      type: msg.type(),
      text: msg.text(),
      location: msg.location(),
      args: msg.args().length,
    };

    if (msg.type() === 'error') {
      RESULTS.consoleErrors.push(logData);
      console.error(`[CONSOLE ERROR] ${msg.text()}`);
    } else if (msg.type() === 'warning') {
      RESULTS.consoleWarnings.push(logData);
      console.warn(`[CONSOLE WARNING] ${msg.text()}`);
    }
  });

  // Track page errors
  page.on('pageerror', (error) => {
    RESULTS.pageErrors.push({
      message: error.message,
      stack: error.stack,
    });
    console.error(`[PAGE ERROR] ${error.message}`);
  });

  // Track unhandled promise rejections
  page.on('response', (response) => {
    if (response.status() >= 400) {
      const errorData = {
        status: response.status(),
        url: response.url(),
        statusText: response.statusText(),
      };
      if (response.status() >= 500) {
        RESULTS.networkErrors.push(errorData);
        console.error(`[NETWORK ERROR] ${response.status()} ${response.url()}`);
      }
    }
  });

  // Track request failures
  page.on('requestfailed', (request) => {
    RESULTS.networkErrors.push({
      url: request.url(),
      failure: request.failure().errorText,
    });
    console.error(`[REQUEST FAILED] ${request.url()} - ${request.failure().errorText}`);
  });

  // Inject error tracking script
  await page.evaluateOnNewDocument(() => {
    // Track unhandled promise rejections
    window.addEventListener('unhandledrejection', (event) => {
      if (window.__errors__ === undefined) {
        window.__errors__ = { unhandledRejections: [] };
      }
      window.__errors__.unhandledRejections.push({
        reason: event.reason?.message || String(event.reason),
        promise: String(event.promise),
      });
      console.error('[UNHANDLED REJECTION]', event.reason);
    });

    // Track API errors
    const originalFetch = window.fetch;
    window.fetch = function(...args) {
      return originalFetch.apply(this, args)
        .then(response => {
          if (!response.ok && response.status >= 500) {
            if (!window.__errors__) window.__errors__ = { apiErrors: [] };
            window.__errors__.apiErrors.push({
              status: response.status,
              url: response.url,
              statusText: response.statusText,
            });
            console.error(`[API ERROR] ${response.status} ${response.url}`);
          }
          return response;
        })
        .catch(error => {
          if (!window.__errors__) window.__errors__ = { apiErrors: [] };
          window.__errors__.apiErrors.push({
            error: error.message,
            url: args[0],
          });
          console.error(`[API FETCH ERROR] ${error.message}`);
          throw error;
        });
    };

    // Track XHR errors
    const originalXHROpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(method, url) {
      this._url = url;
      this.addEventListener('load', function() {
        if (this.status >= 500) {
          if (!window.__errors__) window.__errors__ = { apiErrors: [] };
          window.__errors__.apiErrors.push({
            status: this.status,
            url: url,
            method: method,
          });
          console.error(`[XHR ERROR] ${this.status} ${method} ${url}`);
        }
      });
      return originalXHROpen.apply(this, arguments);
    };
  });

  console.log('🔍 Starting error capture...\n');

  try {
    console.log('📍 Navigating to http://localhost:5173...');
    await page.goto('http://localhost:5173', { waitUntil: 'networkidle', timeout: 10000 }).catch(err => {
      console.warn(`Navigation warning: ${err.message}`);
    });

    // Wait a bit for errors to surface
    console.log('⏳ Waiting 3 seconds for errors to surface...');
    await page.waitForTimeout(3000);

    // Get errors from page context
    const pageErrors = await page.evaluate(() => window.__errors__ || {});
    if (pageErrors.unhandledRejections) {
      RESULTS.unhandledRejections.push(...pageErrors.unhandledRejections);
    }
    if (pageErrors.apiErrors) {
      RESULTS.apiErrors.push(...pageErrors.apiErrors);
    }

    // Get DOM content for inspection
    const html = await page.content();
    const hasErrors = html.includes('error') || html.includes('Error');

    console.log('\n📊 RESULTS:\n');
    console.log(`Console Errors: ${RESULTS.consoleErrors.length}`);
    RESULTS.consoleErrors.forEach((e, i) => {
      console.log(`  ${i + 1}. ${e.text}`);
    });

    console.log(`\nConsole Warnings: ${RESULTS.consoleWarnings.length}`);
    RESULTS.consoleWarnings.slice(0, 5).forEach((e, i) => {
      console.log(`  ${i + 1}. ${e.text}`);
    });

    console.log(`\nNetwork Errors (5xx): ${RESULTS.networkErrors.length}`);
    RESULTS.networkErrors.slice(0, 10).forEach((e, i) => {
      console.log(`  ${i + 1}. ${e.status || 'FAILED'} ${e.url}`);
    });

    console.log(`\nAPI Errors: ${RESULTS.apiErrors.length}`);
    RESULTS.apiErrors.slice(0, 10).forEach((e, i) => {
      console.log(`  ${i + 1}. ${e.status || 'ERROR'} ${e.url}`);
    });

    console.log(`\nUnhandled Rejections: ${RESULTS.unhandledRejections.length}`);
    RESULTS.unhandledRejections.slice(0, 5).forEach((e, i) => {
      console.log(`  ${i + 1}. ${e.reason}`);
    });

    console.log(`\nPage Errors: ${RESULTS.pageErrors.length}`);
    RESULTS.pageErrors.slice(0, 5).forEach((e, i) => {
      console.log(`  ${i + 1}. ${e.message}`);
    });

    // Save results
    fs.writeFileSync('error-capture-results.json', JSON.stringify(RESULTS, null, 2));
    console.log('\n✅ Results saved to error-capture-results.json');

    // Take a screenshot
    await page.screenshot({ path: 'frontend-home-screenshot.png', fullPage: true });
    console.log('📷 Screenshot saved to frontend-home-screenshot.png');
  } catch (error) {
    console.error('Capture error:', error);
  } finally {
    await browser.close();
  }
})();
