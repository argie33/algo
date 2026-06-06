import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ ignoreHTTPSErrors: true });
const page = await context.newPage();

const pageErrors = [];
page.on('pageerror', err => pageErrors.push(err.toString()));

console.log('Loading site...');
await page.goto('https://d2u93283nn45h2.cloudfront.net', { 
  waitUntil: 'domcontentloaded',
  timeout: 30000 
}).catch(() => {});

await page.waitForTimeout(2000);

// Find where "5xx" or "500" text appears
const errorMessages = await page.evaluate(() => {
  const text = document.body.innerText;
  const lines = text.split('\n');
  const errorLines = lines.filter(l => 
    l.toLowerCase().includes('5xx') || 
    l.includes('500') || 
    l.includes('503') || 
    l.includes('504') ||
    l.toLowerCase().includes('error') ||
    l.toLowerCase().includes('failed')
  );
  return errorLines.slice(0, 20); // First 20 error lines
});

console.log('=== ERROR TEXT FOUND IN PAGE ===');
console.log(errorMessages);

// Check for API response errors
const responseErrors = await page.evaluate(() => {
  // Try to find any error messages in the page
  const allText = document.body.innerText;
  // Look for common error patterns
  const patterns = [
    /API.*(?:error|failed|5\d{2})/gi,
    /Connection.*(?:refused|failed|timeout)/gi,
    /Cannot.*(?:read|access|find)/gi,
    /Status.*(?:5\d{2})/gi
  ];
  
  const matches = [];
  patterns.forEach(p => {
    const found = allText.match(p);
    if (found) matches.push(...found);
  });
  return [...new Set(matches)];
});

console.log('\n=== API/CONNECTION ERRORS ===');
console.log(responseErrors);

// Get all console logs
const consoleLogs = [];
page.on('console', msg => consoleLogs.push(`[${msg.type()}] ${msg.text()}`));

await page.waitForTimeout(2000); // Wait for more logs

console.log('\n=== CONSOLE LOGS (filtered) ===');
consoleLogs
  .filter(l => !l.includes('width(-1) and height(-1)'))
  .slice(0, 30)
  .forEach(l => console.log(l));

console.log('\n=== PAGE ERRORS ===');
pageErrors.forEach(e => console.log(e));

console.log('\n=== CHECKING SPECIFIC DATA LOAD STATUS ===');
const dataStatus = await page.evaluate(() => {
  // Check if there are loading spinners or error states
  const loadingElements = document.querySelectorAll('[class*="loading"], [class*="spinner"], [class*="skeleton"]');
  const errorElements = document.querySelectorAll('[class*="error"], [class*="alert"]');
  
  return {
    loadingElementCount: loadingElements.length,
    errorElementCount: errorElements.length,
    loadingVisible: Array.from(loadingElements).some(el => {
      const style = window.getComputedStyle(el);
      return style.display !== 'none';
    }),
    errorMessages: Array.from(errorElements)
      .map(el => el.textContent)
      .filter(t => t.trim())
      .slice(0, 5)
  };
});

console.log('\n=== DATA LOAD STATUS ===');
console.log(JSON.stringify(dataStatus, null, 2));

await browser.close();
