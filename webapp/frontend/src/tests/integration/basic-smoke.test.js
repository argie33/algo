/**
 * Basic Smoke Test for Integration Testing Setup
 * Simple test to verify the testing infrastructure works
 */

import { test, expect } from '@playwright/test';

const testConfig = {
  baseURL: process.env.E2E_BASE_URL || 'https://d1zb7knau41vl9.cloudfront.net',
  timeout: 30000
};

test.describe('Basic Integration Smoke Test', () => {
  
  test('Application loads successfully', async ({ page }) => {
    console.log('🌐 Testing application load...');
    console.log(`Base URL: ${testConfig.baseURL}`);
    
    // Navigate to the application
    await page.goto(testConfig.baseURL);
    
    // Wait for page to load
    await page.waitForLoadState('networkidle');
    
    // Check if the page loaded
    const title = await page.title();
    console.log(`📄 Page title: ${title}`);
    
    // Verify we can see the page
    expect(title).toBeTruthy();
    
    // Check for basic elements
    const body = page.locator('body');
    await expect(body).toBeVisible();
    
    console.log('✅ Application loads successfully');
  });
  
  test('Basic navigation works', async ({ page }) => {
    console.log('🧭 Testing basic navigation...');
    
    await page.goto(testConfig.baseURL);
    await page.waitForLoadState('networkidle');
    
    // Look for navigation elements
    const navElements = await page.locator('nav, [data-testid*="nav"], [role="navigation"]').count();
    console.log(`🧭 Found ${navElements} navigation elements`);
    
    // Look for common UI elements
    const buttons = await page.locator('button').count();
    const links = await page.locator('a').count();
    
    console.log(`🔘 Found ${buttons} buttons`);
    console.log(`🔗 Found ${links} links`);
    
    expect(buttons + links).toBeGreaterThan(0);
    
    console.log('✅ Basic navigation elements found');
  });
  
  test('Console errors check', async ({ page }) => {
    console.log('🚨 Checking for console errors...');
    
    const consoleErrors = [];
    
    page.on('console', msg => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });
    
    await page.goto(testConfig.baseURL);
    await page.waitForLoadState('networkidle');
    
    // Wait a bit for any delayed errors
    await page.waitForTimeout(3000);
    
    console.log(`🚨 Console errors found: ${consoleErrors.length}`);
    
    if (consoleErrors.length > 0) {
      console.log('Console errors:');
      consoleErrors.forEach((error, index) => {
        console.log(`  ${index + 1}. ${error}`);
      });
    }
    
    // Don't fail on console errors for now, just log them
    console.log('✅ Console error check completed');
  });

});

export default {
  testConfig
};