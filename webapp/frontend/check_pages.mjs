import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ ignoreHTTPSErrors: true });
const page = await context.newPage();

// Capture ALL network requests and responses
const networkLog = [];
page.on('response', async res => {
  networkLog.push({
    url: res.url(),
    status: res.status(),
    statusText: res.statusText(),
  });
});

const routes = [
  { path: '/', name: 'Home (redirects to /app/markets)' },
  { path: '/app/markets', name: 'Markets Health' },
  { path: '/app/scores', name: 'Stock Scores' },
  { path: '/app/sectors', name: 'Sector Analysis' },
];

for (const route of routes) {
  console.log(`\n=== ${route.name} ===`);
  networkLog.length = 0;
  
  try {
    await page.goto(`https://d2u93283nn45h2.cloudfront.net${route.path}`, {
      waitUntil: 'domcontentloaded',
      timeout: 15000
    }).catch(() => {});
    
    await page.waitForTimeout(1500);
    
    // Check for 5xx errors
    const errors5xx = networkLog.filter(r => r.status >= 500);
    const errors4xx = networkLog.filter(r => r.status >= 400 && r.status < 500);
    
    console.log(`  Status codes: ${[...new Set(networkLog.map(r => r.status))].sort((a,b) => a-b).join(', ')}`);
    
    if (errors5xx.length > 0) {
      console.log(`  [5XX ERRORS] ${errors5xx.length} found:`);
      errors5xx.slice(0, 5).forEach(e => console.log(`    ${e.status} ${e.url}`));
    }
    
    if (errors4xx.length > 0) {
      console.log(`  [4XX ERRORS] ${errors4xx.length} found:`);
      errors4xx.slice(0, 5).forEach(e => console.log(`    ${e.status} ${e.url}`));
    }
    
    // Check page content
    const pageInfo = await page.evaluate(() => {
      const errors = [];
      document.querySelectorAll('[class*="error"]').forEach(el => {
        const text = el.textContent?.trim();
        if (text && text.length < 200) errors.push(text);
      });
      return {
        title: document.title,
        hasContent: document.body.innerText.length > 100,
        errorCount: document.querySelectorAll('[class*="error"]').length,
        visibleErrors: [...new Set(errors)].slice(0, 3),
      };
    });
    
    console.log(`  Page title: ${pageInfo.title}`);
    console.log(`  Has content: ${pageInfo.hasContent}`);
    if (pageInfo.visibleErrors.length > 0) {
      console.log(`  Error messages: ${pageInfo.visibleErrors.join(' | ')}`);
    }
  } catch (e) {
    console.log(`  Navigation failed: ${e.message}`);
  }
}

await browser.close();
