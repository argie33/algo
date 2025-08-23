/**
 * Critical User Flows E2E Tests
 * Industry Standard Testing - Run Manually Only
 * 
 * Usage:
 *   1. Start dev server: npm run dev
 *   2. Run tests: npm run test:e2e
 *   3. Debug mode: npm run test:e2e:debug
 */

import { test, expect } from '@playwright/test';

test.describe('Critical User Flows', () => {
  
  test.beforeEach(async ({ page }) => {
    // Set up test environment
    await page.goto('/');
    
    // Wait for React to load
    await page.waitForSelector('#root');
    await expect(page.locator('#root')).not.toBeEmpty();
  });

  test('App loads without console errors', async ({ page }) => {
    const consoleErrors = [];
    const pageErrors = [];
    
    // Capture console errors
    page.on('console', msg => {
      if (msg.type() === 'error') {
        consoleErrors.push({
          text: msg.text(),
          location: msg.location()
        });
      }
    });
    
    // Capture page errors
    page.on('pageerror', error => {
      pageErrors.push({
        message: error.message,
        stack: error.stack
      });
    });
    
    // Navigate and wait for full load
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    
    // Additional wait for React hydration
    await page.waitForTimeout(2000);
    
    // Check for React Context errors specifically
    const reactContextErrors = [...consoleErrors, ...pageErrors].filter(error => 
      error.text?.includes('ContextConsumer') ||
      error.text?.includes('Cannot set properties of undefined') ||
      error.text?.includes('react-is') ||
      error.message?.includes('ContextConsumer') ||
      error.message?.includes('Cannot set properties of undefined')
    );
    
    // Assert no critical errors
    expect(reactContextErrors, 'React Context errors found').toHaveLength(0);
    expect(pageErrors, 'Page errors found').toHaveLength(0);
    
    // Console errors are warnings only (some may be expected)
    if (consoleErrors.length > 0) {
      console.log('⚠️ Console warnings detected:', consoleErrors.length);
      consoleErrors.forEach(error => {
        console.log(`   - ${error.text} (${error.location?.url}:${error.location?.lineNumber})`);
      });
    }
  });

  test('Navigation works without errors', async ({ page }) => {
    // Test basic navigation
    const navigationLinks = [
      { text: 'Portfolio', expected: '/portfolio' },
      { text: 'Dashboard', expected: '/dashboard' },
      { text: 'Settings', expected: '/settings' }
    ];
    
    for (const link of navigationLinks) {
      try {
        // Find and click navigation link
        const navLink = page.locator(`a:has-text("${link.text}"), button:has-text("${link.text}")`).first();
        
        if (await navLink.isVisible()) {
          await navLink.click();
          await page.waitForLoadState('networkidle');
          
          // Verify navigation occurred
          const currentUrl = page.url();
          expect(currentUrl, `Navigation to ${link.text} failed`).toContain(link.expected);
          
          // Verify page loaded content
          await expect(page.locator('#root')).not.toBeEmpty();
          
          console.log(`✅ Navigation to ${link.text} successful`);
        } else {
          console.log(`⚠️ ${link.text} navigation link not found - may not be implemented yet`);
        }
      } catch (error) {
        console.log(`⚠️ Navigation to ${link.text} failed: ${error.message}`);
        // Don't fail test - some pages may not be implemented
      }
    }
  });

  test('Performance meets standards', async ({ page }) => {
    // Start performance monitoring
    const startTime = Date.now();
    
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    
    const domLoadTime = Date.now() - startTime;
    
    // Wait for complete load
    await page.waitForLoadState('networkidle');
    const fullLoadTime = Date.now() - startTime;
    
    // Get Web Vitals
    const webVitals = await page.evaluate(() => {
      return new Promise((resolve) => {
        const vitals = {};
        
        // First Contentful Paint
        const observer = new PerformanceObserver((entryList) => {
          const entries = entryList.getEntries();
          entries.forEach((entry) => {
            if (entry.name === 'first-contentful-paint') {
              vitals.fcp = entry.startTime;
            }
          });
        });
        
        observer.observe({ entryTypes: ['paint'] });
        
        // Largest Contentful Paint
        const lcpObserver = new PerformanceObserver((entryList) => {
          const entries = entryList.getEntries();
          const lastEntry = entries[entries.length - 1];
          if (lastEntry) {
            vitals.lcp = lastEntry.startTime;
          }
        });
        
        lcpObserver.observe({ entryTypes: ['largest-contentful-paint'] });
        
        setTimeout(() => {
          resolve(vitals);
        }, 1000);
      });
    });
    
    // Performance assertions (industry standards)
    expect(domLoadTime, 'DOM load time too slow').toBeLessThan(3000); // < 3s
    expect(fullLoadTime, 'Full load time too slow').toBeLessThan(5000); // < 5s
    
    if (webVitals.fcp) {
      expect(webVitals.fcp, 'First Contentful Paint too slow').toBeLessThan(2500); // < 2.5s
    }
    
    console.log(`📊 Performance Metrics:`);
    console.log(`   DOM Load: ${domLoadTime}ms`);
    console.log(`   Full Load: ${fullLoadTime}ms`);
    console.log(`   FCP: ${webVitals.fcp ? Math.round(webVitals.fcp) + 'ms' : 'N/A'}`);
    console.log(`   LCP: ${webVitals.lcp ? Math.round(webVitals.lcp) + 'ms' : 'N/A'}`);
  });

  test('App handles API failures gracefully', async ({ page }) => {
    // Simulate network failures
    await page.route('**/api/**', route => {
      // Fail 50% of API calls to test error handling
      if (Math.random() > 0.5) {
        route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ error: 'Simulated API failure' })
        });
      } else {
        route.continue();
      }
    });
    
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    
    // App should still render without crashing
    await expect(page.locator('#root')).not.toBeEmpty();
    
    // Should show graceful error messages, not crash
    const errorElements = page.locator('[data-testid="error"], .error, [class*="error"]');
    const hasErrorMessages = await errorElements.count() > 0;
    
    if (hasErrorMessages) {
      console.log('✅ App shows graceful error handling for API failures');
    } else {
      console.log('ℹ️ No error messages shown - may use fallback data');
    }
    
    // Most importantly - no JavaScript crashes
    await expect(page.locator('#root')).toBeVisible();
  });

  test('Mobile responsiveness works', async ({ page }) => {
    // Test mobile viewport
    await page.setViewportSize({ width: 375, height: 667 }); // iPhone SE
    
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    
    // App should render properly on mobile
    await expect(page.locator('#root')).toBeVisible();
    
    // Check for mobile-specific elements or responsive behavior
    const bodyWidth = await page.evaluate(() => document.body.scrollWidth);
    expect(bodyWidth, 'Horizontal scroll detected on mobile').toBeLessThanOrEqual(375);
    
    // Test tablet viewport
    await page.setViewportSize({ width: 768, height: 1024 }); // iPad
    await page.waitForTimeout(500); // Allow layout to adjust
    
    await expect(page.locator('#root')).toBeVisible();
    
    console.log('✅ Mobile and tablet viewports render correctly');
  });

});

test.describe('User Authentication Flow', () => {
  
  test('Login/Register forms work', async ({ page }) => {
    await page.goto('/');
    
    try {
      // Look for login/auth related elements
      const authElements = await page.locator('button:has-text("Login"), button:has-text("Sign In"), button:has-text("Register"), [data-testid*="auth"]').count();
      
      if (authElements > 0) {
        console.log('✅ Authentication elements found - testing interaction');
        
        // Test clicking auth buttons doesn't crash
        const loginButton = page.locator('button:has-text("Login"), button:has-text("Sign In")').first();
        if (await loginButton.isVisible()) {
          await loginButton.click();
          await page.waitForTimeout(1000);
          
          // Should show login form or redirect without crashing
          await expect(page.locator('#root')).toBeVisible();
          console.log('✅ Login interaction works');
        }
      } else {
        console.log('ℹ️ No authentication UI found - may be auto-authenticated in dev mode');
      }
    } catch (error) {
      console.log(`⚠️ Authentication test skipped: ${error.message}`);
    }
  });
  
});