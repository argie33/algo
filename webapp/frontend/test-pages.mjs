import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  
  let apiErrors = [];
  let consoleErrors = [];
  let apiCalls = [];
  
  page.on('console', msg => {
    if (msg.type() === 'error' || msg.type() === 'warning') {
      consoleErrors.push(`[${msg.type()}] ${msg.text()}`);
    }
  });
  
  page.on('response', async resp => {
    if (resp.url().includes('/api/')) {
      apiCalls.push({
        status: resp.status(),
        url: resp.url().substring(resp.url().indexOf('/api'))
      });
      if (resp.status() >= 400) {
        apiErrors.push(`${resp.status()} ${resp.url()}`);
      }
    }
  });

  console.log('=== Testing Trading Signals Page ===\n');
  await page.goto('http://localhost:5174/app/trading-signals', { waitUntil: 'domcontentloaded' }).catch(() => null);
  await page.waitForTimeout(2000);
  
  console.log('API Calls Made:');
  apiCalls.forEach(c => console.log(`  ${c.status} ${c.url}`));
  
  if (apiErrors.length) {
    console.log('\nAPI Errors:');
    apiErrors.forEach(e => console.log(`  ❌ ${e}`));
  }
  
  if (consoleErrors.length) {
    console.log('\nConsole Errors:');
    consoleErrors.forEach(e => console.log(`  ${e}`));
  }
  
  const pageState = await page.evaluate(() => ({
    title: document.title,
    h1: document.querySelector('h1')?.textContent,
    tableCount: document.querySelectorAll('table').length,
    bodyText: document.body.innerText.substring(0, 200)
  }));
  
  console.log('\nPage State:');
  console.log(`  Title: ${pageState.title}`);
  console.log(`  H1: ${pageState.h1}`);
  console.log(`  Tables: ${pageState.tableCount}`);
  console.log(`  Content preview: ${pageState.bodyText.substring(0, 100)}`);

  await browser.close();
})();
