import playwright from './node_modules/playwright/index.js';
const { chromium } = playwright;

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  const errors = [];
  const logs = [];

  page.on('console', msg => {
    const type = msg.type();
    const text = msg.text();
    logs.push({ type, text });
    if (type === 'error') {
      errors.push(text);
    }
  });

  page.on('pageerror', err => {
    errors.push(`PageError: ${err.message}`);
  });

  try {
    console.log('\n=== Testing MarketsHealth Page ===');
    await page.goto('http://localhost:5175/app/markets-health', { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(1500);

    // Check page content
    const bodyText = await page.textContent('body');
    const hasContent = bodyText && bodyText.length > 500;

    console.log(`Page loaded: ${hasContent ? '✅' : '❌'}`);
    console.log(`Errors: ${errors.length}`);

    if (errors.length > 0) {
      console.log('\nCONSOLE ERRORS:');
      errors.slice(0, 10).forEach((e, i) => {
        console.log(`  ${i + 1}. ${e.substring(0, 120)}`);
      });
    }

    const undefinedErrors = errors.filter(e => e.includes('Cannot read') || e.includes('undefined') || e.includes('of undefined'));
    if (undefinedErrors.length > 0) {
      console.log('\n❌ CRITICAL - Undefined property errors found:');
      undefinedErrors.forEach(e => console.log(`  - ${e.substring(0, 150)}`));
    } else {
      console.log('✅ No undefined property errors');
    }

    errors.length = 0;
    logs.length = 0;

    console.log('\n=== Testing PortfolioDashboard Page ===');
    await page.goto('http://localhost:5175/app/portfolio', { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(1500);

    const bodyText2 = await page.textContent('body');
    const hasContent2 = bodyText2 && bodyText2.length > 500;

    console.log(`Page loaded: ${hasContent2 ? '✅' : '❌'}`);
    console.log(`Errors: ${errors.length}`);

    if (errors.length > 0) {
      console.log('\nCONSOLE ERRORS:');
      errors.slice(0, 10).forEach((e, i) => {
        console.log(`  ${i + 1}. ${e.substring(0, 120)}`);
      });
    }

    const undefinedErrors2 = errors.filter(e => e.includes('Cannot read') || e.includes('undefined') || e.includes('of undefined'));
    if (undefinedErrors2.length > 0) {
      console.log('\n❌ CRITICAL - Undefined property errors found:');
      undefinedErrors2.forEach(e => console.log(`  - ${e.substring(0, 150)}`));
    } else {
      console.log('✅ No undefined property errors');
    }

  } catch (e) {
    console.error('FATAL ERROR:', e.message);
    console.error(e.stack);
  } finally {
    await browser.close();
  }
})();
