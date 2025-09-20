/**
 * Visual Regression Test Suite
 * Comprehensive visual testing and screenshot comparison
 */

import { test, expect } from '@playwright/test';

test.describe('Visual Regression Testing', () => {
  test.beforeEach(async ({ page }) => {
    // Set up consistent visual testing environment
    await page.addInitScript(() => {
      // Disable animations for consistent screenshots
      const style = document.createElement('style');
      style.textContent = `
        *, *::before, *::after {
          animation-duration: 0s !important;
          animation-delay: 0s !important;
          transition-duration: 0s !important;
          transition-delay: 0s !important;
        }
      `;
      document.head.appendChild(style);

      // Set fixed date for consistency
      Date.now = () => 1640995200000; // 2022-01-01
    });

    // Set viewport for consistent screenshots
    await page.setViewportSize({ width: 1920, height: 1080 });
  });

  test('should match homepage visual baseline', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Wait for all images and animations to complete
    await page.waitForTimeout(2000);

    // Hide dynamic content that changes frequently
    await page.addStyleTag({
      content: `
        .timestamp, .live-data, .real-time, [data-testid="timestamp"] {
          visibility: hidden !important;
        }
        .spinner, .loading, .skeleton {
          display: none !important;
        }
      `
    });

    // Take full page screenshot
    await expect(page).toHaveScreenshot('homepage-full.png', {
      fullPage: true,
      mask: [
        page.locator('.timestamp'),
        page.locator('.live-data'),
        page.locator('[data-timestamp]')
      ]
    });

    // Take viewport screenshot
    await expect(page).toHaveScreenshot('homepage-viewport.png', {
      mask: [
        page.locator('.timestamp'),
        page.locator('.live-data')
      ]
    });
  });

  test('should match dashboard visual baseline', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);

    // Hide dynamic elements
    await page.addStyleTag({
      content: `
        .chart-tooltip, .live-price, .percentage-change, .last-updated {
          visibility: hidden !important;
        }
      `
    });

    // Take dashboard screenshot
    await expect(page).toHaveScreenshot('dashboard-full.png', {
      fullPage: true,
      mask: [
        page.locator('.live-price'),
        page.locator('.percentage-change'),
        page.locator('.last-updated'),
        page.locator('[data-live]')
      ]
    });

    // Test specific dashboard components
    const chartContainer = page.locator('.chart-container').first();
    if (await chartContainer.isVisible()) {
      await expect(chartContainer).toHaveScreenshot('dashboard-chart.png');
    }

    const summaryCards = page.locator('.summary-card, .metric-card').first();
    if (await summaryCards.isVisible()) {
      await expect(summaryCards).toHaveScreenshot('dashboard-summary-card.png');
    }
  });

  test('should match portfolio page visual baseline', async ({ page }) => {
    await page.goto('/portfolio');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);

    // Hide dynamic financial data
    await page.addStyleTag({
      content: `
        .price, .gain-loss, .percentage, .market-value, .last-price {
          color: transparent !important;
          background: #f5f5f5 !important;
        }
        .real-time-indicator, .status-indicator {
          display: none !important;
        }
      `
    });

    await expect(page).toHaveScreenshot('portfolio-full.png', {
      fullPage: true,
      mask: [
        page.locator('.price'),
        page.locator('.gain-loss'),
        page.locator('.percentage'),
        page.locator('.last-updated')
      ]
    });

    // Test portfolio table
    const portfolioTable = page.locator('table, .portfolio-table').first();
    if (await portfolioTable.isVisible()) {
      await expect(portfolioTable).toHaveScreenshot('portfolio-table.png', {
        mask: [
          page.locator('td:has-text("$")')
        ]
      });
    }
  });

  test('should match market overview visual baseline', async ({ page }) => {
    await page.goto('/market-overview');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);

    // Hide dynamic market data
    await page.addStyleTag({
      content: `
        .market-price, .price-change, .volume, .market-cap {
          color: transparent !important;
          background: #f5f5f5 !important;
        }
      `
    });

    await expect(page).toHaveScreenshot('market-overview-full.png', {
      fullPage: true,
      mask: [
        page.locator('.market-price'),
        page.locator('.price-change'),
        page.locator('.last-updated')
      ]
    });

    // Test market charts
    const marketChart = page.locator('.market-chart, .chart').first();
    if (await marketChart.isVisible()) {
      await expect(marketChart).toHaveScreenshot('market-chart.png');
    }
  });

  test('should match settings page visual baseline', async ({ page }) => {
    await page.goto('/settings');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    await expect(page).toHaveScreenshot('settings-full.png', {
      fullPage: true
    });

    // Test form components
    const formSections = await page.locator('form, .form-section').all();
    for (let i = 0; i < Math.min(formSections.length, 3); i++) {
      if (await formSections[i].isVisible()) {
        await expect(formSections[i]).toHaveScreenshot(`settings-form-${i}.png`);
      }
    }
  });

  test('should match component states visual baseline', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Test button states
    const buttons = await page.locator('button').all();
    for (let i = 0; i < Math.min(buttons.length, 5); i++) {
      const button = buttons[i];
      if (await button.isVisible()) {
        // Normal state
        await expect(button).toHaveScreenshot(`button-${i}-normal.png`);

        // Hover state
        await button.hover();
        await expect(button).toHaveScreenshot(`button-${i}-hover.png`);

        // Focus state
        await button.focus();
        await expect(button).toHaveScreenshot(`button-${i}-focus.png`);
      }
    }

    // Test form input states
    const inputs = await page.locator('input[type="text"], input[type="email"]').all();
    for (let i = 0; i < Math.min(inputs.length, 3); i++) {
      const input = inputs[i];
      if (await input.isVisible()) {
        // Empty state
        await expect(input).toHaveScreenshot(`input-${i}-empty.png`);

        // Filled state
        await input.fill('Test Value');
        await expect(input).toHaveScreenshot(`input-${i}-filled.png`);

        // Focus state
        await input.focus();
        await expect(input).toHaveScreenshot(`input-${i}-focus.png`);

        await input.clear();
      }
    }
  });

  test('should match responsive design visual baseline', async ({ page }) => {
    // Test desktop view
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    await expect(page).toHaveScreenshot('responsive-desktop.png');

    // Test tablet view
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.waitForTimeout(1000);
    await expect(page).toHaveScreenshot('responsive-tablet.png');

    // Test mobile view
    await page.setViewportSize({ width: 375, height: 667 });
    await page.waitForTimeout(1000);
    await expect(page).toHaveScreenshot('responsive-mobile.png');

    // Test navigation on mobile
    const mobileMenu = page.locator('.mobile-menu, .hamburger, [aria-label*="menu"]').first();
    if (await mobileMenu.isVisible()) {
      await mobileMenu.click();
      await page.waitForTimeout(500);
      await expect(page).toHaveScreenshot('responsive-mobile-menu.png');
    }
  });

  test('should match dark mode visual baseline', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Try to enable dark mode
    const darkModeToggle = page.locator('[data-testid="dark-mode"], .dark-mode-toggle, [aria-label*="dark"]').first();
    if (await darkModeToggle.isVisible()) {
      await darkModeToggle.click();
      await page.waitForTimeout(1000);

      await expect(page).toHaveScreenshot('dark-mode-homepage.png', {
        mask: [
          page.locator('.timestamp'),
          page.locator('.live-data')
        ]
      });

      // Test dashboard in dark mode
      await page.goto('/dashboard');
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(2000);

      await expect(page).toHaveScreenshot('dark-mode-dashboard.png', {
        mask: [
          page.locator('.live-price'),
          page.locator('.percentage-change')
        ]
      });
    } else {
      // If no dark mode toggle, test with CSS dark mode
      await page.addStyleTag({
        content: `
          :root { color-scheme: dark; }
          body { background: #1a1a1a; color: #ffffff; }
        `
      });
      await page.waitForTimeout(1000);
      await expect(page).toHaveScreenshot('css-dark-mode.png');
    }
  });

  test('should match error states visual baseline', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Simulate network error
    await page.route('**/api/**', route => route.abort());

    await page.reload();
    await page.waitForTimeout(3000);

    // Look for error states
    const errorElements = await page.locator('.error, .alert-error, [role="alert"]').all();
    for (let i = 0; i < errorElements.length; i++) {
      if (await errorElements[i].isVisible()) {
        await expect(errorElements[i]).toHaveScreenshot(`error-state-${i}.png`);
      }
    }

    // Test 404 page if available
    try {
      await page.goto('/nonexistent-page');
      await page.waitForTimeout(2000);
      await expect(page).toHaveScreenshot('404-page.png');
    } catch (e) {
      // 404 page might not be available
    }
  });

  test('should match loading states visual baseline', async ({ page }) => {
    // Slow down network to capture loading states
    await page.route('**/api/**', async route => {
      await new Promise(resolve => setTimeout(resolve, 2000));
      await route.continue();
    });

    await page.goto('/dashboard');

    // Capture loading states
    await page.waitForTimeout(500);
    const loadingElements = await page.locator('.loading, .spinner, .skeleton, [aria-label*="loading"]').all();

    for (let i = 0; i < loadingElements.length; i++) {
      if (await loadingElements[i].isVisible()) {
        await expect(loadingElements[i]).toHaveScreenshot(`loading-state-${i}.png`);
      }
    }

    // Wait for loading to complete
    await page.waitForLoadState('networkidle');
  });

  test('should match chart and graph visual baseline', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);

    // Hide dynamic chart data
    await page.addStyleTag({
      content: `
        .chart-tooltip, .chart-crosshair, .chart-cursor {
          display: none !important;
        }
        .live-data-point, .real-time-update {
          opacity: 0 !important;
        }
      `
    });

    // Find and capture charts
    const charts = await page.locator('.chart, .graph, canvas, svg[class*="chart"]').all();

    for (let i = 0; i < charts.length; i++) {
      const chart = charts[i];
      if (await chart.isVisible()) {
        const boundingBox = await chart.boundingBox();
        if (boundingBox && boundingBox.width > 50 && boundingBox.height > 50) {
          await expect(chart).toHaveScreenshot(`chart-${i}.png`);
        }
      }
    }

    // Test chart interactions
    const interactiveChart = charts[0];
    if (interactiveChart && await interactiveChart.isVisible()) {
      await interactiveChart.hover({ position: { x: 100, y: 100 } });
      await page.waitForTimeout(500);
      await expect(interactiveChart).toHaveScreenshot('chart-hover-state.png');
    }
  });

  test('should match modal and dialog visual baseline', async ({ page }) => {
    await page.goto('/settings');
    await page.waitForLoadState('networkidle');

    // Look for modal triggers
    const modalTriggers = await page.locator(
      'button:has-text("Edit"), button:has-text("Add"), button:has-text("Delete"), .modal-trigger'
    ).all();

    for (let i = 0; i < Math.min(modalTriggers.length, 3); i++) {
      const trigger = modalTriggers[i];
      if (await trigger.isVisible()) {
        await trigger.click();
        await page.waitForTimeout(1000);

        // Capture modal
        const modal = page.locator('.modal, .dialog, [role="dialog"]').first();
        if (await modal.isVisible()) {
          await expect(modal).toHaveScreenshot(`modal-${i}.png`);

          // Close modal
          const closeButton = modal.locator('.close, [aria-label*="close"], button:has-text("Cancel")').first();
          if (await closeButton.isVisible()) {
            await closeButton.click();
          } else {
            await page.keyboard.press('Escape');
          }
          await page.waitForTimeout(500);
        }
      }
    }
  });

  test('should match typography and text rendering', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Create a typography showcase
    await page.addStyleTag({
      content: `
        .typography-test {
          position: fixed;
          top: 0;
          left: 0;
          width: 800px;
          background: white;
          padding: 20px;
          z-index: 9999;
          font-family: inherit;
        }
      `
    });

    await page.evaluate(() => {
      const typographyTest = document.createElement('div');
      typographyTest.className = 'typography-test';
      typographyTest.innerHTML = `
        <h1>Heading 1 - Financial Dashboard</h1>
        <h2>Heading 2 - Portfolio Overview</h2>
        <h3>Heading 3 - Market Analysis</h3>
        <p>Regular paragraph text with financial data: $1,234.56</p>
        <p><strong>Bold text:</strong> Important financial information</p>
        <p><em>Italic text:</em> Additional context and notes</p>
        <small>Small text: Last updated timestamp</small>
        <code>Code text: API endpoint /api/portfolio</code>
      `;
      document.body.appendChild(typographyTest);
    });

    await page.waitForTimeout(500);
    const typographyElement = page.locator('.typography-test');
    await expect(typographyElement).toHaveScreenshot('typography-baseline.png');
  });
});