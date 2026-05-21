import { chromium } from 'playwright';

const pages = [
  { path: '/', name: 'Home (Marketing)' },
  { path: '/app/markets', name: 'Markets Dashboard' },
  { path: '/app/economic', name: 'Economic Dashboard' },
  { path: '/app/deep-value', name: 'Deep Value Stocks' },
  { path: '/app/trading-signals', name: 'Trading Signals' },
  { path: '/app/sectors', name: 'Sectors' },
  { path: '/app/sentiment', name: 'Sentiment' },
  { path: '/app/scores', name: 'Scores' },
  { path: '/app/backtests', name: 'Backtests' },
];

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  const results = [];

  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      results[results.length - 1].errors.push(msg.text());
    }
  });

  page.on('pageerror', (err) => {
    if (results.length > 0) {
      results[results.length - 1].errors.push(`PageError: ${err.message}`);
    }
  });

  console.log('Testing all public pages...\n');

  for (const route of pages) {
    const url = `http://localhost:5174${route.path}`;
    try {
      results.push({ page: route.name, url, status: null, errors: [] });
      
      const response = await page.goto(url, { waitUntil: 'networkidle', timeout: 15000 }).catch(e => null);
      results[results.length - 1].status = response?.status() || 'timeout';
      
      await page.waitForTimeout(1000);
      
      const title = await page.title();
      const content = await page.textContent('body');
      const hasContent = content && content.trim().length > 100;
      
      results[results.length - 1].title = title;
      results[results.length - 1].hasContent = hasContent;
    } catch (e) {
      results[results.length - 1].error = e.message;
    }
  }

  console.log('═══════════════════════════════════════════════════\n');
  for (const r of results) {
    const icon = r.status === 200 && r.hasContent && r.errors.length === 0 ? '✅' : '❌';
    console.log(`${icon} ${r.page}`);
    console.log(`   URL: ${r.url}`);
    console.log(`   Status: ${r.status}`);
    console.log(`   Content: ${r.hasContent ? 'Yes' : 'No'}`);
    if (r.errors.length > 0) {
      console.log(`   Errors: ${r.errors.join(' | ')}`);
    }
    console.log('');
  }

  const working = results.filter(r => r.status === 200 && r.hasContent && r.errors.length === 0).length;
  console.log(`═══════════════════════════════════════════════════\n`);
  console.log(`Summary: ${working}/${results.length} pages working\n`);

  await browser.close();
})();
