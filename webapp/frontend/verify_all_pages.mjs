import { chromium } from 'playwright';
const BASE_URL = 'https://d2u93283nn45h2.cloudfront.net';
const PAGES = [
  '/app/markets', '/app/economy', '/app/portfolio', '/app/algo',
  '/app/signals', '/app/swings', '/app/scores', '/app/sectors',
  '/app/sentiment', '/app/trades', '/app/audit', '/app/service-health',
];
const IGNORE = [/\[AMPLIFY\]/, /favicon/, /ERR_NAME/, /chrome-extension/, /ResizeObserver/];
async function check(browser, path) {
  const ctx = await browser.newContext({ userAgent: 'Mozilla/5.0 Chrome/120' });
  const page = await ctx.newPage();
  const errors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') {
      const t = msg.text();
      if (!IGNORE.some(p => p.test(t))) errors.push(t.substring(0, 250));
    }
  });
  page.on('pageerror', e => errors.push(`[UNCAUGHT] ${e.message.substring(0, 250)}`));
  await page.goto(`${BASE_URL}${path}`, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(3000);
  const crashed = await page.locator('text=Something went wrong').isVisible();
  await ctx.close();
  return { path, errors, crashed };
}
async function main() {
  const browser = await chromium.launch({ headless: true });
  const results = [];
  for (const p of PAGES) { results.push(await check(browser, p)); }
  await browser.close();
  let allClean = true;
  for (const r of results) {
    const ok = r.errors.length === 0 && !r.crashed;
    if (!ok) allClean = false;
    console.log(`${ok ? '✅' : '❌'} ${r.path}: ${r.errors.length} error(s)${r.crashed ? ' +ErrorBoundary' : ''}`);
    if (r.errors.length) r.errors.forEach(e => console.log(`     ${e}`));
  }
  console.log(`\n${allClean ? '✅ ALL CLEAN' : '❌ ERRORS FOUND'}`);
  process.exit(allClean ? 0 : 1);
}
main().catch(e => { console.error(e); process.exit(1); });
