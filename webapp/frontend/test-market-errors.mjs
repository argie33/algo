import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  
  const errors = [];
  const warnings = [];
  const logs = [];
  
  page.on('console', msg => {
    const text = msg.text();
    if (msg.type() === 'error') errors.push(text);
    else if (msg.type() === 'warn') warnings.push(text);
    else if (text.includes('Market') || text.includes('Overview')) logs.push(text);
  });
  
  await page.goto('http://localhost:5174/app/market', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2000);
  
  console.log('=== BROWSER CONSOLE MESSAGES ===\n');
  
  if (errors.length) {
    console.log('ERRORS:');
    errors.forEach(e => console.log(`  ❌ ${e.substring(0, 100)}`));
  }
  
  if (warnings.slice(0, 5).length) {
    console.log('\nWARNINGS (first 5):');
    warnings.slice(0, 5).forEach(w => console.log(`  ⚠️  ${w.substring(0, 100)}`));
  }
  
  if (logs.length) {
    console.log('\nMarket-related logs:');
    logs.forEach(l => console.log(`  📝 ${l.substring(0, 100)}`));
  }

  await browser.close();
})();
