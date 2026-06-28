import { chromium } from 'playwright';

(async () => {
  try {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();

    await page.goto('file:///c/Users/arger/code/algo/webapp/frontend/test_api.html');
    await page.waitForTimeout(2000);

    // Click first test button
    console.log('Testing proxy API...');
    await page.click('button:has-text("Test")');
    await page.waitForTimeout(3000);

    // Get results
    const result1 = await page.textContent('#result1');
    console.log('=== Proxy API Response ===');
    console.log(result1);

    // Click second test
    console.log('\nTesting status...');
    const buttons = await page.locator('button').all();
    await buttons[1].click();
    await page.waitForTimeout(2000);

    const result2 = await page.textContent('#result2');
    console.log('\n=== Status Test ===');
    console.log(result2);

    // Click third test
    console.log('\nTesting all endpoints...');
    await buttons[2].click();
    await page.waitForTimeout(5000);

    const result3 = await page.textContent('#result3');
    console.log('\n=== All Endpoints ===');
    console.log(result3);

    await browser.close();
  } catch (error) {
    console.error('Error:', error.message);
    process.exit(1);
  }
})();
