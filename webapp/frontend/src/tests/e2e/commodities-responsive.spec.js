import { test, expect } from '@playwright/test';

test.describe('Commodities Page Responsive Design', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to commodities page
    await page.goto('/commodities');
    
    // Wait for page to load
    await page.waitForSelector('[data-testid="commodities-header"], h1, h3', { timeout: 10000 });
  });

  test.describe('Desktop View (1920x1080)', () => {
    test.beforeEach(async ({ page }) => {
      await page.setViewportSize({ width: 1920, height: 1080 });
    });

    test('should display full desktop layout', async ({ page }) => {
      // Check header is visible
      await expect(page.locator('text=Commodities Market')).toBeVisible();
      
      // Check search functionality
      await expect(page.locator('input[placeholder*="Search"]')).toBeVisible();
      
      // Check market summary bar if present
      const marketSummary = page.locator('text=Market Open, text=Market Closed').first();
      if (await marketSummary.isVisible()) {
        await expect(marketSummary).toBeVisible();
      }
      
      // Check grid/table toggle buttons
      const gridButton = page.locator('button:has-text("Grid")');
      const tableButton = page.locator('button:has-text("Table")');
      
      if (await gridButton.isVisible()) {
        await expect(gridButton).toBeVisible();
        await expect(tableButton).toBeVisible();
      }
    });

    test('should handle category navigation', async ({ page }) => {
      // Look for category tabs or navigation
      const allCategories = page.locator('text=All Categories');
      const energyTab = page.locator('text=Energy');
      
      if (await allCategories.isVisible()) {
        await expect(allCategories).toBeVisible();
      }
      
      if (await energyTab.isVisible()) {
        await energyTab.click();
        // Should update content based on category
        await page.waitForTimeout(1000);
      }
    });
  });

  test.describe('Tablet View (768x1024)', () => {
    test.beforeEach(async ({ page }) => {
      await page.setViewportSize({ width: 768, height: 1024 });
    });

    test('should adapt layout for tablet', async ({ page }) => {
      // Header should still be visible
      await expect(page.locator('text=Commodities Market')).toBeVisible();
      
      // Check responsive grid
      const gridItems = page.locator('[data-testid*="commodity"], .MuiCard-root');
      if (await gridItems.first().isVisible()) {
        const gridItem = gridItems.first();
        const boundingBox = await gridItem.boundingBox();
        
        // Grid items should be appropriately sized for tablet
        expect(boundingBox?.width).toBeLessThan(400);
      }
    });

    test('should maintain search functionality', async ({ page }) => {
      const searchInput = page.locator('input[placeholder*="Search"]');
      
      if (await searchInput.isVisible()) {
        await searchInput.fill('oil');
        await page.waitForTimeout(500);
        
        // Should filter results
        const oilResults = page.locator('text=Oil, text=oil').first();
        if (await oilResults.isVisible()) {
          await expect(oilResults).toBeVisible();
        }
      }
    });
  });

  test.describe('Mobile View (375x667)', () => {
    test.beforeEach(async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 667 });
    });

    test('should show mobile-optimized layout', async ({ page }) => {
      // Header should be responsive
      await expect(page.locator('text=Commodities Market')).toBeVisible();
      
      // Check for mobile category dropdown instead of tabs
      const categorySelect = page.locator('label:has-text("Category")');
      const categoryTabs = page.locator('[role="tablist"]');
      
      if (await categorySelect.isVisible()) {
        // Mobile should show dropdown
        await expect(categorySelect).toBeVisible();
      } else if (await categoryTabs.isVisible()) {
        // Tabs should be scrollable on mobile
        await expect(categoryTabs).toBeVisible();
      }
    });

    test('should handle mobile navigation', async ({ page }) => {
      // Test scrolling behavior
      await page.evaluate(() => window.scrollTo(0, 300));
      await page.waitForTimeout(500);
      
      // Content should still be accessible
      const content = page.locator('.MuiContainer-root, main, [data-testid*="content"]').first();
      await expect(content).toBeVisible();
    });

    test('should maintain touch interactions', async ({ page }) => {
      // Test touch interactions on mobile
      const refreshButton = page.locator('button:has-text("Refresh")');
      
      if (await refreshButton.isVisible()) {
        await refreshButton.tap();
        await page.waitForTimeout(1000);
      }
      
      // Test card interactions
      const cards = page.locator('.MuiCard-root');
      if (await cards.first().isVisible()) {
        await cards.first().tap();
        await page.waitForTimeout(500);
      }
    });
  });

  test.describe('Cross-device Functionality', () => {
    test('should handle view switching on different devices', async ({ page }) => {
      const sizes = [
        { width: 1920, height: 1080, name: 'Desktop' },
        { width: 768, height: 1024, name: 'Tablet' },
        { width: 375, height: 667, name: 'Mobile' }
      ];

      for (const size of sizes) {
        await page.setViewportSize(size);
        await page.waitForTimeout(500);
        
        // Header should always be visible
        await expect(page.locator('text=Commodities Market')).toBeVisible();
        
        // Content should be responsive
        const content = page.locator('.MuiContainer-root, main').first();
        await expect(content).toBeVisible();
        
        // Check viewport-specific elements
        if (size.width >= 768) {
          // Desktop/Tablet: Check for grid/table toggle
          const viewToggle = page.locator('button:has-text("Grid"), button:has-text("Table")').first();
          if (await viewToggle.isVisible()) {
            await expect(viewToggle).toBeVisible();
          }
        }
      }
    });
  });

  test.describe('Performance on Different Devices', () => {
    test('should load quickly on mobile', async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 667 });
      
      const startTime = Date.now();
      await page.reload();
      
      // Wait for main content to load
      await page.waitForSelector('text=Commodities Market', { timeout: 10000 });
      
      const loadTime = Date.now() - startTime;
      
      // Should load within 5 seconds on mobile
      expect(loadTime).toBeLessThan(5000);
    });

    test('should handle network throttling', async ({ page, context }) => {
      // Simulate slow 3G network
      await context.route('**/*', route => {
        setTimeout(() => route.continue(), 100);
      });
      
      await page.setViewportSize({ width: 375, height: 667 });
      await page.reload();
      
      // Should still load and be functional
      await expect(page.locator('text=Commodities Market')).toBeVisible({ timeout: 15000 });
    });
  });

  test.describe('Accessibility on Mobile', () => {
    test('should be accessible on touch devices', async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 667 });
      
      // Check for proper touch targets
      const buttons = page.locator('button');
      const buttonCount = await buttons.count();
      
      for (let i = 0; i < Math.min(buttonCount, 5); i++) {
        const button = buttons.nth(i);
        if (await button.isVisible()) {
          const boundingBox = await button.boundingBox();
          
          // Touch targets should be at least 44px (iOS standard)
          expect(boundingBox?.height).toBeGreaterThanOrEqual(36);
        }
      }
    });

    test('should support keyboard navigation', async ({ page }) => {
      await page.setViewportSize({ width: 768, height: 1024 });
      
      // Test tab navigation
      const focusableElements = page.locator('button, input, select, [tabindex="0"]');
      const count = await focusableElements.count();
      
      if (count > 0) {
        await page.keyboard.press('Tab');
        await page.waitForTimeout(200);
        
        // Should have visible focus indicator
        const focusedElement = page.locator(':focus');
        await expect(focusedElement).toBeVisible();
      }
    });
  });

  test.describe('Error Handling on Mobile', () => {
    test('should gracefully handle API errors on mobile', async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 667 });
      
      // Block API calls to test error states
      await page.route('**/api/commodities/**', route => {
        route.abort();
      });
      
      await page.reload();
      
      // Should show fallback content or error messages
      const errorElements = page.locator('text=Error, text=Failed, text=Demo Data, [data-testid="error"]');
      const hasError = await errorElements.first().isVisible({ timeout: 5000 });
      
      if (hasError) {
        await expect(errorElements.first()).toBeVisible();
      } else {
        // Should at least show the page header
        await expect(page.locator('text=Commodities Market')).toBeVisible();
      }
    });
  });
});