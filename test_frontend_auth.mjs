#!/usr/bin/env node
import { chromium } from '@playwright/test';

const testUrl = 'http://localhost:5175';

async function testFrontend() {
  const browser = await chromium.launch();
  const context = await browser.newContext();

  // Capture all console messages
  const consoleLogs = [];
  context.on('page', page => {
    page.on('console', msg => {
      consoleLogs.push({
        type: msg.type(),
        text: msg.text(),
        location: msg.location(),
      });
    });
  });

  const page = await context.newPage();

  try {
    console.log(`Opening ${testUrl}...`);
    await page.goto(testUrl, { waitUntil: 'networkidle', timeout: 15000 });

    // Wait a bit for React to render
    await page.waitForTimeout(2000);

    // Get console logs
    console.log('\n=== CONSOLE LOGS ===');
    consoleLogs.forEach(log => {
      const level = log.type === 'error' ? '❌' : log.type === 'warning' ? '⚠️' : 'ℹ️';
      console.log(`${level} [${log.type}] ${log.text}`);
    });

    // Check for specific auth errors
    const authErrors = consoleLogs.filter(log =>
      log.text.includes('Auth') ||
      log.text.includes('Cognito') ||
      log.text.includes('Amplify')
    );

    if (authErrors.length > 0) {
      console.log('\n=== AUTH-RELATED MESSAGES ===');
      authErrors.forEach(log => {
        const level = log.type === 'error' ? '❌' : log.type === 'warning' ? '⚠️' : 'ℹ️';
        console.log(`${level} [${log.type}] ${log.text}`);
      });
    }

    // Check page title
    const title = await page.title();
    console.log(`\nPage Title: ${title}`);

    // Check if page has content
    const bodyText = await page.evaluate(() => document.body.innerText.slice(0, 200));
    console.log(`Page Content (first 200 chars): ${bodyText}`);

    console.log('\n✅ Page loaded successfully');

  } catch (error) {
    console.error('❌ Error loading page:', error.message);
  } finally {
    await context.close();
    await browser.close();
  }
}

testFrontend();
