import { chromium } from 'playwright';

async function checkConsoleErrors() {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  const logs = [];
  const errors = [];
  const warnings = [];

  page.on('console', msg => {
    const log = {
      type: msg.type(),
      text: msg.text(),
      location: msg.location()
    };
    console.log(`[${msg.type().toUpperCase()}] ${msg.text()}`);

    if (msg.type() === 'error') {
      errors.push(log);
    } else if (msg.type() === 'warning') {
      warnings.push(log);
    } else {
      logs.push(log);
    }
  });

  page.on('pageerror', err => {
    console.error('[PAGE ERROR]', err.message);
    errors.push({ type: 'pageerror', text: err.message, stack: err.stack });
  });

  page.on('response', response => {
    if (response.status() >= 400) {
      console.warn(`[HTTP ${response.status()}] ${response.url()}`);
      warnings.push({ type: 'http', status: response.status(), url: response.url() });
    }
  });

  console.log('Navigating to http://localhost:5173...');
  await page.goto('http://localhost:5173', { waitUntil: 'networkidle', timeout: 30000 }).catch(err => {
    console.error('Navigation error:', err.message);
  });

  // Wait a bit for any async errors to appear
  await page.waitForTimeout(3000);

  await browser.close();

  console.log('\n=== SUMMARY ===');
  console.log(`Errors: ${errors.length}`);
  console.log(`Warnings: ${warnings.length}`);
  console.log(`Info logs: ${logs.length}`);

  if (errors.length > 0) {
    console.log('\n=== ERRORS ===');
    errors.forEach(e => console.log(`- ${e.text}`));
  }

  if (warnings.length > 0) {
    console.log('\n=== WARNINGS ===');
    warnings.forEach(w => {
      if (w.type === 'http') {
        console.log(`- HTTP ${w.status}: ${w.url}`);
      } else {
        console.log(`- ${w.text}`);
      }
    });
  }

  process.exit(errors.length > 0 ? 1 : 0);
}

checkConsoleErrors().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});
