#!/usr/bin/env node
import { chromium } from 'playwright';

const PORT = 5173;
const BASE_URL = `http://localhost:${PORT}`;

async function test() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const consoleMessages = [];
  page.on('console', msg => {
    consoleMessages.push({
      type: msg.type(),
      text: msg.text(),
    });
  });

  try {
    console.log(`\n🧪 Testing frontend at ${BASE_URL}...\n`);

    await page.goto(BASE_URL, { waitUntil: 'load', timeout: 30000 });
    await page.waitForTimeout(2000);

    // Check console for errors
    const errors = consoleMessages.filter(m => m.type === 'error');
    const warnings = consoleMessages.filter(m => m.type === 'warning');

    console.log(`📝 Console Messages:`);
    console.log(`  ❌ Errors: ${errors.length}`);
    console.log(`  ⚠️  Warnings: ${warnings.length}`);

    if (errors.length > 0) {
      console.log('\n❌ ERRORS:');
      errors.forEach((err, i) => {
        console.log(`  ${i + 1}. ${err.text.slice(0, 100)}`);
      });
    }

    // Check for specific auth errors
    const authErrors = errors.filter(e => e.text.includes('Auth') || e.text.includes('Cognito') || e.text.includes('Amplify'));
    if (authErrors.length > 0) {
      console.log('\n🔐 Authentication Issues Found:');
      authErrors.forEach(err => {
        console.log(`  - ${err.text}`);
      });
    } else {
      console.log('\n✅ No authentication errors detected!');
    }

    // Get page title and basic info
    const title = await page.title();
    console.log(`\n📄 Page Title: ${title}`);

    // Check if React app is running
    const reactRoot = await page.evaluate(() => {
      const root = document.querySelector('#root');
      return root ? 'Found' : 'Not found';
    });
    console.log(`⚛️ React Root: ${reactRoot}`);

    await browser.close();
    console.log('\n✅ Test completed successfully!\n');
    process.exit(0);

  } catch (error) {
    console.error('\n❌ Test failed:', error.message);
    await browser.close();
    process.exit(1);
  }
}

test();
