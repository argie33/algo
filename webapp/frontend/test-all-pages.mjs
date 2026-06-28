import { chromium } from 'playwright';

const BASE = 'http://localhost:5178';
const PAGES = [
  '/app/markets',
  '/app/portfolio',
  '/app/algo',
  '/app/signals',
  '/app/scores',
  '/app/sectors',
  '/app/sentiment',
  '/app/risk',
  '/app/economic',
  '/app/health',
  '/app/trades',
];

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
const page = await context.newPage();

const allErrors = [];
const allResponses = {};

page.on('response', async (response) => {
  if (response.url().includes('/api/')) {
    const status = response.status();
    const url = new URL(response.url());
    const endpoint = url.pathname;
    try {
      const body = await response.text();
      if (!allResponses[endpoint]) allResponses[endpoint] = { status, body: body.substring(0, 500) };
      if (status >= 400) {
        allErrors.push({ status, endpoint, body: body.substring(0, 500) });
        console.log(`\n❌ ERROR ${status} ${endpoint}`);
        console.log(`   ${body.substring(0, 300)}`);
      }
    } catch (e) {}
  }
});

for (const pagePath of PAGES) {
  try {
    console.log(`\n=== Visiting ${pagePath} ===`);
    await page.goto(`${BASE}${pagePath}`, { timeout: 20000, waitUntil: 'networkidle' });
    await page.waitForTimeout(2000);
    const title = await page.title();
    const visible = await page.locator('body').textContent();
    // Check for error indicators
    const hasError = visible.includes('503') || visible.includes('500') || visible.includes('Error loading');
    const hasEmpty = visible.includes('No trades') || visible.includes('No data') || visible.includes('No positions');
    console.log(`   Title: ${title}`);
    if (hasError) console.log(`   ⚠️  ERROR TEXT found in page`);
    if (hasEmpty) console.log(`   ⚠️  EMPTY STATE found: "${visible.match(/(No \w+[^.]*)/)?.[1] || ''}"`);
    await page.screenshot({ path: `screenshot-${pagePath.replace('/app/', '').replace('/', '-')}.png`, fullPage: true });
  } catch (e) {
    console.log(`   Navigation error: ${e.message}`);
  }
}

console.log('\n\n========== SUMMARY ==========');
console.log(`Total API endpoints seen: ${Object.keys(allResponses).length}`);
console.log(`\nALL ENDPOINTS:`);
for (const [ep, data] of Object.entries(allResponses)) {
  const icon = data.status >= 400 ? '❌' : '✅';
  console.log(`  ${icon} ${data.status} ${ep}`);
}

console.log(`\n\nERRORS (${allErrors.length} total):`);
for (const err of allErrors) {
  console.log(`\n❌ ${err.status} ${err.endpoint}`);
  console.log(`   ${err.body.substring(0, 400)}`);
}

await browser.close();
