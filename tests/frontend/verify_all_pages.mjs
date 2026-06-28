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
  const errors = [], failed = [];
  page.on('response', r => { const s=r.status(), u=r.url(); if(s>=400&&u.includes('/api/')&&!u.includes('favicon')) failed.push(`HTTP ${s}: ${u.replace(BASE_URL,'')}`); });
  page.on('console', m => { if(m.type()==='error'){const t=m.text(); if(!IGNORE.some(p=>p.test(t))) errors.push(t.substring(0,250));} });
  page.on('pageerror', e => errors.push(`[UNCAUGHT] ${e.message.substring(0,250)}`));
  await page.goto(`${BASE_URL}${path}`, {waitUntil:'networkidle',timeout:30000});
  await page.waitForTimeout(3000);
  const crashed = await page.locator('text=Something went wrong').isVisible();
  await ctx.close();
  return { path, errors, failed, crashed };
}

async function main() {
  const browser = await chromium.launch({headless:true});
  const results = [];
  for (const p of PAGES) results.push(await check(browser, p));
  await browser.close();
  let allClean = true;
  for (const r of results) {
    const ok = r.errors.length===0 && !r.crashed;
    if (!ok) allClean = false;
    console.log(`${ok?'✅':'❌'} ${r.path}: ${r.errors.length} err, ${r.failed.length} API fail`);
    r.errors.forEach(e => console.log(`  ERR: ${e}`));
    r.failed.forEach(f => console.log(`  NET: ${f}`));
  }
  console.log(`\n${allClean?'✅ ALL PAGES CLEAN':'❌ ERRORS FOUND'}`);
  process.exit(allClean?0:1);
}

main().catch(e=>{console.error(e);process.exit(1);});
