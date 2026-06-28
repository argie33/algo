import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

try {
  console.log('Navigating to dashboard...');
  await page.goto('http://localhost:5185/app/algo-dashboard', { waitUntil: 'networkidle', timeout: 30000 });
  
  // Wait a bit for content to load
  await page.waitForTimeout(2000);
  
  // Take a screenshot
  await page.screenshot({ path: 'dashboard.png', fullPage: true });
  console.log('Screenshot saved');
  
  // Get all text content
  const fullText = await page.textContent('body');
  
  // Check for error/unavailable patterns
  if (fullText.includes('unavailable') || fullText.includes('Unavailable')) {
    console.log('\n⚠ Dashboard shows unavailable panels');
  }
  
  // Try to find specific panel issues
  const panels = await page.locator('h2, h3').allTextContents();
  console.log('\nPanel titles found:');
  panels.slice(0, 20).forEach(p => {
    if (p.trim()) console.log(`  - ${p.trim()}`);
  });
  
  // Look for error messages
  const errorMsg = await page.locator('[class*="error"], [role="alert"]').allTextContents();
  if (errorMsg.length > 0) {
    console.log('\nError messages:');
    errorMsg.forEach(e => {
      if (e.trim()) console.log(`  - ${e.trim()}`);
    });
  }
  
  console.log('\n✓ Dashboard check complete');
  
} catch (e) {
  console.error('Error:', e.message);
} finally {
  await browser.close();
}
