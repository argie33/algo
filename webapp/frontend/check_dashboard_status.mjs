import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';

async function checkDashboard() {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();

    // Set viewport to see full dashboard
    await page.setViewportSize({ width: 1920, height: 1080 });

    // Navigate to dashboard
    console.log('Loading dashboard at http://localhost:5173...');
    try {
      await page.goto('http://localhost:5173', { waitUntil: 'networkidle', timeout: 30000 });
    } catch (e) {
      console.log('Initial navigation timeout, trying again...');
      await page.reload({ waitUntil: 'networkidle' });
    }

    // Wait a bit for data to load
    await page.waitForTimeout(3000);

    // Check for error messages or unavailable panels
    const errors = await page.locator('[class*="error"], [class*="unavailable"], [class*="Error"]').all();
    console.log(`\nFound ${errors.length} error/unavailable elements`);

    for (let i = 0; i < Math.min(errors.length, 10); i++) {
      const text = await errors[i].textContent();
      const html = await errors[i].innerHTML();
      console.log(`Error ${i + 1}: ${text?.trim() || html?.substring(0, 100)}`);
    }

    // Look for specific unavailable indicators
    const questionMarks = await page.locator('[class*="unavailable"], :has-text("unavailable")').all();
    console.log(`\nLooking for unavailable panels...`);

    if (questionMarks.length > 0) {
      for (const elem of questionMarks) {
        const text = await elem.textContent();
        console.log(`  - ${text?.trim()}`);
      }
    }

    // Take a full page screenshot
    const screenshotPath = path.join(process.cwd(), 'dashboard_check.png');
    await page.screenshot({ path: screenshotPath, fullPage: true });
    console.log(`\nScreenshot saved to: ${screenshotPath}`);

    // Check console logs for errors
    page.on('console', msg => {
      if (msg.type() === 'error') {
        console.log(`Console Error: ${msg.text()}`);
      }
    });

    page.on('pageerror', error => {
      console.log(`Page Error: ${error.message}`);
    });

    // Check network responses for errors
    let errorResponses = [];
    page.on('response', response => {
      if (response.status() >= 400) {
        errorResponses.push(`${response.status()} ${response.url()}`);
      }
    });

    // Wait a bit more to capture any errors
    await page.waitForTimeout(2000);

    if (errorResponses.length > 0) {
      console.log(`\nAPI Errors found:`);
      errorResponses.forEach(err => console.log(`  - ${err}`));
    }

  } finally {
    await browser.close();
  }
}

checkDashboard().catch(console.error);
