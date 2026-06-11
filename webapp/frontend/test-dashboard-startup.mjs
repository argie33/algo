#!/usr/bin/env node

import { chromium } from 'playwright';

async function testDashboard() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  console.log('🚀 Testing dashboard startup...\n');

  try {
    // Navigate to dashboard
    console.log('📍 Navigating to http://localhost:5178');
    await page.goto('http://localhost:5178', { waitUntil: 'domcontentloaded', timeout: 10000 });

    // Check for errors in console
    const errors = [];
    page.on('console', msg => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
        console.log(`❌ Console Error: ${msg.text()}`);
      }
    });

    // Wait for the page to load
    await page.waitForTimeout(2000);

    // Take screenshot
    const screenshotPath = './dashboard-startup-test.png';
    await page.screenshot({ path: screenshotPath, fullPage: true });
    console.log(`📸 Screenshot saved to ${screenshotPath}`);

    // Check for main elements
    const pageHead = await page.locator('.page-head').first();
    const mainContent = await page.locator('.main-content').first();

    if (await pageHead.isVisible({ timeout: 5000 }).catch(() => false)) {
      console.log('✅ Page header visible');
    } else {
      console.log('❌ Page header NOT visible');
    }

    if (await mainContent.isVisible({ timeout: 5000 }).catch(() => false)) {
      console.log('✅ Main content visible');
    } else {
      console.log('❌ Main content NOT visible');
    }

    // Check for API errors
    const apiErrors = await page.locator('[class*="warning"]').count();
    console.log(`⚠️ API/Warning elements found: ${apiErrors}`);

    // Check for loading skeletons still visible
    const skeletons = await page.locator('[class*="skeleton"]').count();
    console.log(`⏳ Loading skeleton elements: ${skeletons}`);

    if (errors.length > 0) {
      console.log(`\n❌ ${errors.length} console errors detected`);
      process.exit(1);
    } else {
      console.log('\n✅ No console errors detected');
    }

  } catch (error) {
    console.error('❌ Test failed:', error.message);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

testDashboard();
