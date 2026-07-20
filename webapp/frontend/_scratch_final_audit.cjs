const { chromium } = require('playwright');

const BASE = 'http://localhost:5173';
const pages = [
  '/home', '/firm', '/about', '/our-team', '/mission-values', '/contact',
  '/research-insights', '/investment-tools', '/wealth-management',
  '/app/markets', '/app/economic', '/app/sectors', '/app/sentiment',
  '/app/deep-value', '/app/trading-signals', '/app/swing', '/app/scores',
  '/app/portfolio', '/app/trades', '/app/health', '/app/settings',
  '/app/earnings', '/app/pre-trade-impact', '/app/risk-analytics',
  '/app/algo-dashboard', '/app/backtests', '/app/configuration',
  '/app/notifications', '/app/audit', '/app/blueprint',
];

(async () => {
  const browser = await chromium.launch();
  const results = {};

  for (const path of pages) {
    const context = await browser.newContext();
    const page = await context.newPage();
    const consoleMsgs = [];
    const pageErrors = [];
    const networkFails = [];

    page.on('console', (msg) => {
      const t = msg.text();
      if (['error', 'warning'].includes(msg.type()) && !t.includes('Cognito not configured')) {
        consoleMsgs.push(`[${msg.type()}] ${t.slice(0, 350)}`);
      }
    });
    page.on('pageerror', (err) => pageErrors.push(err.message));
    page.on('response', (res) => {
      if (res.status() >= 400) {
        networkFails.push(`${res.status()} ${res.request().method()} ${res.url()}`);
      }
    });

    try {
      await page.goto(BASE + path, { waitUntil: 'networkidle', timeout: 20000 });
      await page.waitForTimeout(8000);
      results[path] = { consoleMsgs, pageErrors, networkFails: [...new Set(networkFails)] };
    } catch (e) {
      results[path] = { error: e.message };
    }

    await context.close();
  }

  await browser.close();
  console.log(JSON.stringify(results, null, 2));
})();
