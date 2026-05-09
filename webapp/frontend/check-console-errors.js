import { chromium } from 'playwright';

async function checkConsoleErrors() {
  const url = 'http://localhost:5179';
  const errors = [];
  const warnings = [];
  const logs = [];

  try {
    const browser = await chromium.launch();
    const page = await browser.newPage();

    // Capture all console messages
    page.on('console', msg => {
      const type = msg.type();
      const text = msg.text();
      const location = msg.location();

      const logEntry = { type, text, location };

      if (type === 'error') {
        errors.push(logEntry);
      } else if (type === 'warning') {
        warnings.push(logEntry);
      } else {
        logs.push(logEntry);
      }

      console.log(`[${type.toUpperCase()}] ${text}`);
    });

    // Capture page errors
    page.on('pageerror', error => {
      errors.push({
        type: 'pageerror',
        message: error.message,
        stack: error.stack.split('\n').slice(0, 3).join('\n')
      });
      console.error(`[PAGE ERROR] ${error.message}`);
    });

    // Capture request/response errors
    page.on('requestfailed', request => {
      errors.push({
        type: 'request-failed',
        url: request.url(),
        reason: request.failure()?.errorText
      });
      console.error(`[REQUEST FAILED] ${request.url()}: ${request.failure()?.errorText}`);
    });

    console.log(`Opening ${url}...`);
    await page.goto(url, { waitUntil: 'networkidle' });

    // Wait for additional logs
    await new Promise(r => setTimeout(r, 2000));

    // Print summary
    console.log(`\n${'='.repeat(60)}`);
    console.log(`ISSUE SUMMARY`);
    console.log(`${'='.repeat(60)}`);
    console.log(`\nErrors: ${errors.length}`);
    errors.forEach((e, i) => {
      console.log(`  ${i + 1}. ${e.text || e.message}`);
    });

    console.log(`\nWarnings: ${warnings.length}`);
    warnings.slice(0, 10).forEach((w, i) => {
      console.log(`  ${i + 1}. ${w.text}`);
    });

    console.log(`\nLogs: ${logs.length}`);
    console.log(`${'='.repeat(60)}\n`);

    await browser.close();

  } catch (error) {
    console.error('Script error:', error.message);
    process.exit(1);
  }
}

checkConsoleErrors();
