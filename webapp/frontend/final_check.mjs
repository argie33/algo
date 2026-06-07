import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
await page.setViewportSize({ width: 1280, height: 720 });

const consoleLogs = [];
page.on('console', msg => {
  consoleLogs.push({
    type: msg.type(),
    text: msg.text()
  });
});

try {
  await page.goto('http://localhost:5184/', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(2000);
  
  const errors = consoleLogs.filter(l => l.type === 'error');
  const warnings = consoleLogs.filter(l => l.type === 'warning');
  
  console.log('✅ Console Error Fix Summary:');
  console.log(`   Total logs: ${consoleLogs.length}`);
  console.log(`   Errors: ${errors.length}`);
  console.log(`   Warnings: ${warnings.length}`);
  
  if (errors.length > 0) {
    console.log('\n   Remaining errors:');
    errors.forEach(e => console.log(`   - ${e.text.substring(0, 80)}`));
  }
  
  if (warnings.length > 0) {
    console.log('\n   Remaining warnings:');
    warnings.forEach(w => console.log(`   - ${w.text.substring(0, 80)}`));
  }
  
  const svgCount = await page.locator('svg').count();
  console.log(`\n✅ Page rendering: ${svgCount} charts rendered successfully`);
  
} catch (e) {
  console.log('Error:', e.message);
}

await browser.close();
