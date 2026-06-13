import { chromium } from 'playwright';
import { writeFileSync } from 'fs';
import { join } from 'path';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  const errors = {
    consoleErrors: [],
    consoleWarnings: [],
    consoleMessages: [],
    networkErrors: [],
    unhandledRejections: [],
    resourceErrors: []
  };

  // Capture console messages
  page.on('console', msg => {
    const logEntry = {
      type: msg.type(),
      text: msg.text(),
      location: msg.location(),
      args: msg.args().length
    };

    if (msg.type() === 'error') {
      errors.consoleErrors.push(logEntry);
      console.error(`[CONSOLE ERROR] ${msg.text()}`);
    } else if (msg.type() === 'warning') {
      errors.consoleWarnings.push(logEntry);
      console.warn(`[CONSOLE WARNING] ${msg.text()}`);
    } else {
      errors.consoleMessages.push(logEntry);
      console.log(`[CONSOLE ${msg.type().toUpperCase()}] ${msg.text()}`);
    }
  });

  // Capture network errors and 5xx responses
  page.on('response', response => {
    if (response.status() >= 500) {
      const error = {
        status: response.status(),
        url: response.url(),
        statusText: response.statusText()
      };
      errors.networkErrors.push(error);
      console.error(`[NETWORK ERROR] ${response.status()} - ${response.url()}`);
    }
  });

  // Capture request failures
  page.on('requestfailed', request => {
    const error = {
      url: request.url(),
      failure: request.failure()?.errorText
    };
    errors.resourceErrors.push(error);
    console.error(`[REQUEST FAILED] ${request.url()} - ${request.failure()?.errorText}`);
  });

  // Capture unhandled rejections
  page.on('pageerror', error => {
    errors.unhandledRejections.push({
      message: error.message,
      stack: error.stack
    });
    console.error(`[UNHANDLED ERROR] ${error.message}`);
  });

  try {
    console.log('Opening http://localhost:5174...');
    await page.goto('http://localhost:5174', { waitUntil: 'networkidle', timeout: 30000 });

    // Wait for initial page load
    await page.waitForTimeout(3000);

    console.log('\n=== Checking for React/Component errors ===');
    // Look for React error boundaries
    const reactErrors = await page.evaluate(() => {
      const errors = [];
      const errorElements = document.querySelectorAll('[class*="error"], [class*="Error"], .error-boundary');
      errorElements.forEach(el => {
        if (el.textContent) {
          errors.push({
            element: el.className,
            content: el.textContent.substring(0, 500)
          });
        }
      });
      return errors;
    });

    if (reactErrors.length > 0) {
      console.log('[REACT ERRORS FOUND]');
      reactErrors.forEach(err => {
        errors.unhandledRejections.push(err);
        console.error(`  - ${err.element}: ${err.content}`);
      });
    }

    console.log('\n=== Checking page DOM and visible content ===');
    const pageInfo = await page.evaluate(() => {
      return {
        title: document.title,
        hasContent: document.body.children.length,
        visibleText: document.body.innerText.substring(0, 500)
      };
    });
    console.log(`Page Title: ${pageInfo.title}`);
    console.log(`DOM Children: ${pageInfo.hasContent}`);
    console.log(`Visible Text: ${pageInfo.visibleText}`);

    // Take a screenshot
    console.log('\n=== Taking screenshot ===');
    await page.screenshot({ path: 'devtools-screenshot.png' });
    console.log('Screenshot saved to devtools-screenshot.png');

  } catch (error) {
    errors.unhandledRejections.push({
      message: error.message,
      stack: error.stack
    });
    console.error('Navigation error:', error.message);
  }

  await browser.close();

  // Write full error report
  const reportPath = join(process.cwd(), 'devtools-errors-report.json');
  writeFileSync(reportPath, JSON.stringify(errors, null, 2));
  console.log(`\n=== Error Report saved to: ${reportPath} ===`);

  console.log('\n=== SUMMARY ===');
  console.log(`Console Errors: ${errors.consoleErrors.length}`);
  console.log(`Console Warnings: ${errors.consoleWarnings.length}`);
  console.log(`Network Errors (5xx): ${errors.networkErrors.length}`);
  console.log(`Unhandled Rejections: ${errors.unhandledRejections.length}`);
  console.log(`Resource Errors: ${errors.resourceErrors.length}`);

  process.exit(0);
})();
