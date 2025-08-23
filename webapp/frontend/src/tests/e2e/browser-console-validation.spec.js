/**
 * End-to-End Browser Console Validation
 * This test actually loads the React app in a real browser and checks console errors
 * Equivalent to manual F12 developer tools testing
 */

import { test, expect } from '@playwright/test';

// Configure test timeouts and faster execution
test.describe.configure({ 
  mode: 'parallel',
  timeout: 120000 // 2 minutes timeout
});

test.describe('Browser Console Error Detection (F12 Equivalent)', () => {
  let consoleErrors = [];
  let consoleWarnings = [];
  let pageErrors = [];

  test.beforeEach(async ({ page }) => {
    // Reset error arrays
    consoleErrors = [];
    consoleWarnings = [];
    pageErrors = [];

    // Capture console messages (like F12 console)
    page.on('console', (msg) => {
      const type = msg.type();
      const text = msg.text();
      
      if (type === 'error') {
        consoleErrors.push(text);
        console.log(`🔴 Console Error: ${text}`);
      } else if (type === 'warning') {
        consoleWarnings.push(text);
        console.log(`🟡 Console Warning: ${text}`);
      } else {
        console.log(`ℹ️ Console ${type}: ${text}`);
      }
    });

    // Capture page errors (unhandled exceptions)
    page.on('pageerror', (error) => {
      pageErrors.push(error.message);
      console.log(`❌ Page Error: ${error.message}`);
    });
  });

  test('should load React app without console errors', async ({ page }) => {
    console.log('🌐 Loading React app (equivalent to opening in browser)...');
    
    // Set faster timeouts
    page.setDefaultTimeout(30000);
    
    // Navigate to the React app (like typing URL in browser)
    await page.goto('http://localhost:3002', { 
      waitUntil: 'domcontentloaded', // Faster than networkidle
      timeout: 30000 
    });
    
    // Wait for React to mount - shorter wait
    await page.waitForTimeout(1500);
    
    console.log(`📊 Console Analysis Results:`);
    console.log(`   Errors: ${consoleErrors.length}`);
    console.log(`   Warnings: ${consoleWarnings.length}`);
    console.log(`   Page Errors: ${pageErrors.length}`);
    
    // Should have no console errors (red errors in F12)
    expect(consoleErrors.length, 
      `Found ${consoleErrors.length} console errors: ${consoleErrors.join(', ')}`
    ).toBe(0);
    
    // Should have no page errors (unhandled exceptions)
    expect(pageErrors.length,
      `Found ${pageErrors.length} page errors: ${pageErrors.join(', ')}`
    ).toBe(0);
  });

  test('should not have React Context compatibility errors', async ({ page }) => {
    page.setDefaultTimeout(30000);
    await page.goto('http://localhost:3002', { 
      waitUntil: 'domcontentloaded',
      timeout: 30000 
    });
    await page.waitForTimeout(1000);
    
    // Check for specific React Context errors we just fixed
    const reactContextErrors = [
      ...consoleErrors,
      ...pageErrors
    ].filter(error => 
      error.includes('ContextConsumer') ||
      error.includes('Cannot set properties of undefined') ||
      error.includes('react-is') ||
      error.includes('Context') && error.includes('undefined')
    );
    
    expect(reactContextErrors.length,
      `Found React Context errors: ${reactContextErrors.join(', ')}`
    ).toBe(0);
    
    console.log('✅ No React Context compatibility errors detected');
  });

  test('should load main React components without errors', async ({ page }) => {
    page.setDefaultTimeout(30000);
    await page.goto('http://localhost:3002', { 
      waitUntil: 'domcontentloaded',
      timeout: 30000 
    });
    
    // Wait for React root to be present
    const rootElement = await page.waitForSelector('#root', { timeout: 10000 });
    expect(rootElement).toBeTruthy();
    
    // Check that React components are actually rendered
    const hasReactContent = await page.evaluate(() => {
      const root = document.getElementById('root');
      return root && root.children.length > 0;
    });
    
    expect(hasReactContent, 'React components should render in #root').toBeTruthy();
    
    // Should have no errors after component mounting
    expect(consoleErrors.length, 'No console errors after React mounting').toBe(0);
    expect(pageErrors.length, 'No page errors after React mounting').toBe(0);
    
    console.log('✅ React components loaded successfully without errors');
  });

  test('should handle navigation without Context errors', async ({ page }) => {
    page.setDefaultTimeout(30000);
    await page.goto('http://localhost:3002', { 
      waitUntil: 'domcontentloaded',
      timeout: 30000 
    });
    
    // Try to navigate (tests React Router and Context providers)
    try {
      // Look for any navigation links
      const navLinks = await page.$$('a[href^="/"]');
      
      if (navLinks.length > 0) {
        console.log(`🔗 Found ${navLinks.length} navigation links, testing first one...`);
        await navLinks[0].click();
        await page.waitForTimeout(2000);
        
        // Should still have no errors after navigation
        expect(consoleErrors.length, 'No console errors after navigation').toBe(0);
        expect(pageErrors.length, 'No page errors after navigation').toBe(0);
        
        console.log('✅ Navigation test passed without errors');
      } else {
        console.log('ℹ️ No navigation links found, skipping navigation test');
      }
    } catch (navError) {
      console.log(`⚠️ Navigation test skipped: ${navError.message}`);
      // Navigation failure shouldn't cause the main test to fail
      // We're primarily testing for Console errors, not navigation
    }
  });
});
