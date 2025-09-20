/**
 * Data Validation Test Suite
 * Comprehensive validation for data integrity and format validation
 */

import { test, expect } from '@playwright/test';

test.describe('Data Validation', () => {
  test.beforeEach(async ({ page }) => {
    // Set up data validation monitoring
    await page.addInitScript(() => {
      window.__VALIDATION_ERRORS__ = [];
      window.__DATA_INTEGRITY_CHECKS__ = [];

      // Monitor console errors related to data validation
      const originalConsoleError = console.error;
      console.error = function(...args) {
        if (args.some(arg => typeof arg === 'string' &&
            (arg.includes('validation') || arg.includes('invalid') || arg.includes('data')))) {
          window.__VALIDATION_ERRORS__.push({
            message: args.join(' '),
            timestamp: Date.now()
          });
        }
        return originalConsoleError.apply(console, args);
      };

      // Capture fetch responses for data validation
      const originalFetch = window.fetch;
      window.fetch = function(...args) {
        return originalFetch.apply(this, args).then(response => {
          if (response.ok) {
            response.clone().json().then(data => {
              window.__DATA_INTEGRITY_CHECKS__.push({
                url: args[0],
                data: data,
                timestamp: Date.now()
              });
            }).catch(() => {
              // Not JSON data
            });
          }
          return response;
        });
      };
    });
  });

  test('should validate financial data formats', async ({ page }) => {
    await page.goto('/portfolio');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);

    // Check displayed financial data formats
    const priceElements = await page.locator('[data-testid*="price"], .price, .amount').all();

    for (const element of priceElements.slice(0, 10)) {
      if (await element.isVisible()) {
        const text = await element.textContent();
        if (text && text.includes('$')) {
          // Price should be properly formatted: $X,XXX.XX
          expect(text).toMatch(/\$[\d,]+\.?\d{0,2}/);

          // Should not have invalid price formats
          expect(text).not.toMatch(/\$\.\d+/); // No leading decimal
          expect(text).not.toMatch(/\$\d+\.\d{3,}/); // No more than 2 decimal places
          expect(text).not.toMatch(/\$.*\d.*\./); // No multiple decimals
        }
      }
    }

    // Check percentage formats
    const percentageElements = await page.locator('[data-testid*="percentage"], .percentage, .change').all();

    for (const element of percentageElements.slice(0, 10)) {
      if (await element.isVisible()) {
        const text = await element.textContent();
        if (text && text.includes('%')) {
          // Percentage should be properly formatted: ±XX.XX%
          expect(text).toMatch(/[+-]?\d+\.?\d{0,2}%/);

          // Should not exceed 100% for most cases (some exceptions allowed)
          const numValue = parseFloat(text.replace(/[^-\d.]/g, ''));
          if (!isNaN(numValue)) {
            expect(Math.abs(numValue)).toBeLessThan(1000); // Reasonable bounds
          }
        }
      }
    }
  });

  test('should validate date and time formats', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    // Check date displays
    const dateElements = await page.locator(
      '[data-testid*="date"], .date, .timestamp, .last-updated, time'
    ).all();

    for (const element of dateElements.slice(0, 5)) {
      if (await element.isVisible()) {
        const text = await element.textContent();
        const datetime = await element.getAttribute('datetime');

        if (text) {
          // Check for common date formats
          const hasValidDateFormat =
            /\d{1,2}\/\d{1,2}\/\d{4}/.test(text) || // MM/DD/YYYY
            /\d{4}-\d{2}-\d{2}/.test(text) || // YYYY-MM-DD
            /\w+ \d{1,2}, \d{4}/.test(text) || // Month DD, YYYY
            /\d{1,2} \w+ \d{4}/.test(text) || // DD Month YYYY
            /\d{1,2}:\d{2}/.test(text); // Time format

          expect(hasValidDateFormat).toBe(true);
        }

        if (datetime) {
          // ISO datetime should be valid
          const date = new Date(datetime);
          expect(date.getTime()).not.toBeNaN();

          // Date should be reasonable (not too far in past/future)
          const now = new Date();
          const yearsDiff = Math.abs(now.getFullYear() - date.getFullYear());
          expect(yearsDiff).toBeLessThan(50);
        }
      }
    }
  });

  test('should validate form input restrictions', async ({ page }) => {
    await page.goto('/settings');
    await page.waitForLoadState('networkidle');

    const inputs = await page.locator('input, textarea, select').all();

    for (const input of inputs.slice(0, 10)) {
      if (await input.isVisible() && await input.isEnabled()) {
        const inputType = await input.getAttribute('type');
        const inputName = await input.getAttribute('name');
        const pattern = await input.getAttribute('pattern');
        const maxLength = await input.getAttribute('maxlength');
        const min = await input.getAttribute('min');
        const max = await input.getAttribute('max');

        // Test email validation
        if (inputType === 'email' || inputName?.includes('email')) {
          await input.fill('invalid-email');
          await input.blur();

          const validity = await input.evaluate(el => el.validity.valid);
          expect(validity).toBe(false);

          await input.fill('valid@example.com');
          await input.blur();

          const validityAfter = await input.evaluate(el => el.validity.valid);
          expect(validityAfter).toBe(true);
        }

        // Test number validation
        if (inputType === 'number') {
          if (min) {
            const minValue = parseFloat(min);
            await input.fill((minValue - 1).toString());
            const belowMinValid = await input.evaluate(el => el.validity.valid);
            expect(belowMinValid).toBe(false);
          }

          if (max) {
            const maxValue = parseFloat(max);
            await input.fill((maxValue + 1).toString());
            const aboveMaxValid = await input.evaluate(el => el.validity.valid);
            expect(aboveMaxValid).toBe(false);
          }

          // Test non-numeric input
          await input.fill('not-a-number');
          const nonNumericValid = await input.evaluate(el => el.validity.valid);
          expect(nonNumericValid).toBe(false);
        }

        // Test pattern validation
        if (pattern) {
          await input.fill('invalid-pattern-test');
          const patternInvalid = await input.evaluate(el => el.validity.valid);
          expect(patternInvalid).toBe(false);
        }

        // Test maxlength validation
        if (maxLength) {
          const maxLen = parseInt(maxLength);
          const longText = 'a'.repeat(maxLen + 10);
          await input.fill(longText);

          const actualValue = await input.inputValue();
          expect(actualValue.length).toBeLessThanOrEqual(maxLen);
        }

        await input.clear();
      }
    }
  });

  test('should validate API response data structures', async ({ page }) => {
    await page.goto('/portfolio');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);

    const dataChecks = await page.evaluate(() => window.__DATA_INTEGRITY_CHECKS__);

    for (const check of dataChecks) {
      const { url, data } = check;

      if (url.includes('/api/portfolio')) {
        // Portfolio data should have required fields
        expect(data).toBeTruthy();

        if (Array.isArray(data)) {
          for (const item of data.slice(0, 5)) {
            // Each portfolio item should have essential fields
            expect(item).toHaveProperty('symbol');
            expect(typeof item.symbol).toBe('string');
            expect(item.symbol.length).toBeGreaterThan(0);

            if (item.quantity !== undefined) {
              expect(typeof item.quantity).toBe('number');
              expect(item.quantity).toBeGreaterThanOrEqual(0);
            }

            if (item.price !== undefined) {
              expect(typeof item.price).toBe('number');
              expect(item.price).toBeGreaterThan(0);
              expect(item.price).toBeLessThan(1000000); // Reasonable upper bound
            }
          }
        }
      }

      if (url.includes('/api/market')) {
        // Market data validation
        if (Array.isArray(data)) {
          for (const item of data.slice(0, 5)) {
            if (item.price !== undefined) {
              expect(typeof item.price).toBe('number');
              expect(item.price).toBeGreaterThan(0);
            }

            if (item.volume !== undefined) {
              expect(typeof item.volume).toBe('number');
              expect(item.volume).toBeGreaterThanOrEqual(0);
            }

            if (item.timestamp !== undefined) {
              const timestamp = new Date(item.timestamp);
              expect(timestamp.getTime()).not.toBeNaN();
            }
          }
        }
      }
    }
  });

  test('should validate number formatting and calculations', async ({ page }) => {
    await page.goto('/portfolio');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    // Test number formatting consistency
    const numberElements = await page.locator(
      '.amount, .price, .value, [data-testid*="amount"], [data-testid*="value"]'
    ).all();

    for (const element of numberElements.slice(0, 10)) {
      if (await element.isVisible()) {
        const text = await element.textContent();
        if (text && /[\d,.]/.test(text)) {
          // Extract numeric value
          const numericText = text.replace(/[^-\d.,]/g, '');

          if (numericText) {
            // Should not have invalid number formats
            expect(numericText).not.toMatch(/,,/); // No double commas
            expect(numericText).not.toMatch(/\.\./); // No double decimals
            expect(numericText).not.toMatch(/,\./); // No comma before decimal
            expect(numericText).not.toMatch(/\.,/); // No decimal before comma

            // Thousands separators should be properly placed
            if (numericText.includes(',')) {
              expect(numericText).toMatch(/\d{1,3}(,\d{3})*(\.\d+)?/);
            }
          }
        }
      }
    }

    // Test calculations if portfolio totals are displayed
    const portfolioTotal = page.locator('[data-testid="total"], .total-value, .portfolio-total').first();
    if (await portfolioTotal.isVisible()) {
      const totalText = await portfolioTotal.textContent();
      if (totalText && totalText.includes('$')) {
        const totalValue = parseFloat(totalText.replace(/[^-\d.]/g, ''));

        // Total should be reasonable
        expect(totalValue).toBeGreaterThanOrEqual(0);
        expect(totalValue).toBeLessThan(100000000); // Reasonable upper bound

        // Total should not be NaN or Infinity
        expect(isFinite(totalValue)).toBe(true);
      }
    }
  });

  test('should validate symbol and ticker formats', async ({ page }) => {
    await page.goto('/portfolio');
    await page.waitForLoadState('networkidle');

    const symbolElements = await page.locator(
      '.symbol, .ticker, [data-testid*="symbol"], [data-testid*="ticker"]'
    ).all();

    for (const element of symbolElements.slice(0, 10)) {
      if (await element.isVisible()) {
        const text = await element.textContent();
        if (text) {
          const symbol = text.trim();

          // Stock symbols should be valid format
          expect(symbol.length).toBeGreaterThan(0);
          expect(symbol.length).toBeLessThan(10); // Most symbols are 1-5 characters
          expect(symbol).toMatch(/^[A-Z0-9.-]+$/); // Only uppercase letters, numbers, dots, hyphens
          expect(symbol).not.toMatch(/^[.-]/); // Shouldn't start with punctuation
          expect(symbol).not.toMatch(/[.-]$/); // Shouldn't end with punctuation
        }
      }
    }
  });

  test('should validate search input and suggestions', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const searchInput = page.locator('input[type="search"], input[placeholder*="search"]').first();

    if (await searchInput.isVisible()) {
      // Test valid symbol search
      await searchInput.fill('AAPL');
      await page.waitForTimeout(1000);

      // Check for search suggestions
      const suggestions = page.locator('.suggestion, .autocomplete, .dropdown-item');
      const suggestionCount = await suggestions.count();

      if (suggestionCount > 0) {
        for (let i = 0; i < Math.min(suggestionCount, 5); i++) {
          const suggestion = suggestions.nth(i);
          const suggestionText = await suggestion.textContent();

          if (suggestionText) {
            // Suggestions should contain the search term or be valid symbols
            const containsSearch = suggestionText.toLowerCase().includes('aapl');
            const isValidSymbol = /^[A-Z]{1,5}$/.test(suggestionText.trim());

            expect(containsSearch || isValidSymbol).toBe(true);
          }
        }
      }

      // Test invalid search input
      await searchInput.fill('!!!invalid###');
      await page.waitForTimeout(1000);

      // Should handle invalid input gracefully
      const errorMessage = page.locator('.error, .invalid, [role="alert"]');
      const hasError = await errorMessage.count() > 0;

      if (hasError) {
        const errorText = await errorMessage.first().textContent();
        expect(errorText?.toLowerCase()).toContain('invalid');
      }

      // Test empty search
      await searchInput.clear();
      await page.waitForTimeout(500);

      const emptySuggestions = await suggestions.count();
      expect(emptySuggestions).toBeLessThanOrEqual(suggestionCount);
    }
  });

  test('should validate chart and graph data', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);

    // Check for chart elements
    const charts = await page.locator('canvas, svg[class*="chart"], .chart').all();

    for (const chart of charts.slice(0, 3)) {
      if (await chart.isVisible()) {
        // Test chart data attributes
        const dataPoints = await chart.locator('[data-value], [data-x], [data-y]').count();

        if (dataPoints > 0) {
          // Validate data point values
          const dataElements = await chart.locator('[data-value]').all();

          for (const dataElement of dataElements.slice(0, 10)) {
            const dataValue = await dataElement.getAttribute('data-value');
            if (dataValue) {
              const numValue = parseFloat(dataValue);

              // Data values should be valid numbers
              expect(isFinite(numValue)).toBe(true);
              expect(numValue).not.toBeNaN();

              // Should be within reasonable bounds
              expect(Math.abs(numValue)).toBeLessThan(1e10);
            }
          }
        }

        // Check for chart labels and axes
        const labels = await chart.locator('text, .label, .axis-label').all();
        for (const label of labels.slice(0, 5)) {
          if (await label.isVisible()) {
            const labelText = await label.textContent();
            if (labelText) {
              // Labels should not be empty or just whitespace
              expect(labelText.trim().length).toBeGreaterThan(0);

              // If label contains numbers, they should be valid
              const numbers = labelText.match(/\d+\.?\d*/g);
              if (numbers) {
                for (const num of numbers) {
                  expect(isFinite(parseFloat(num))).toBe(true);
                }
              }
            }
          }
        }
      }
    }
  });

  test('should validate table data integrity', async ({ page }) => {
    await page.goto('/portfolio');
    await page.waitForLoadState('networkidle');

    const tables = await page.locator('table').all();

    for (const table of tables) {
      if (await table.isVisible()) {
        const rows = await table.locator('tbody tr').all();

        for (const row of rows.slice(0, 10)) {
          const cells = await row.locator('td').all();

          for (const cell of cells) {
            const cellText = await cell.textContent();
            if (cellText) {
              const trimmedText = cellText.trim();

              // Cells should not be empty unless explicitly allowed
              if (trimmedText.length > 0) {
                // Check for data consistency

                // If cell contains price data
                if (trimmedText.includes('$')) {
                  expect(trimmedText).toMatch(/\$[\d,]+\.?\d{0,2}/);
                }

                // If cell contains percentage
                if (trimmedText.includes('%')) {
                  expect(trimmedText).toMatch(/[+-]?\d+\.?\d{0,2}%/);
                }

                // If cell contains only numbers
                if (/^\d+\.?\d*$/.test(trimmedText)) {
                  const numValue = parseFloat(trimmedText);
                  expect(isFinite(numValue)).toBe(true);
                }

                // Check for common data issues
                expect(trimmedText).not.toBe('undefined');
                expect(trimmedText).not.toBe('null');
                expect(trimmedText).not.toBe('NaN');
                expect(trimmedText).not.toBe('[object Object]');
              }
            }
          }
        }

        // Check for table header consistency
        const headers = await table.locator('thead th, thead td').all();
        for (const header of headers) {
          const headerText = await header.textContent();
          if (headerText) {
            expect(headerText.trim().length).toBeGreaterThan(0);
            expect(headerText).not.toMatch(/^\s*$/); // Not just whitespace
          }
        }
      }
    }
  });

  test('should validate data persistence and consistency', async ({ page }) => {
    await page.goto('/portfolio');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    // Capture initial data state
    const initialData = await page.evaluate(() => {
      const portfolioItems = Array.from(document.querySelectorAll('[data-symbol], .portfolio-item'));
      return portfolioItems.map(item => ({
        symbol: item.textContent?.match(/[A-Z]{1,5}/)?.[0] || '',
        content: item.textContent?.trim() || ''
      })).filter(item => item.symbol);
    });

    // Navigate away and back
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    await page.goto('/portfolio');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    // Capture data after navigation
    const afterNavigationData = await page.evaluate(() => {
      const portfolioItems = Array.from(document.querySelectorAll('[data-symbol], .portfolio-item'));
      return portfolioItems.map(item => ({
        symbol: item.textContent?.match(/[A-Z]{1,5}/)?.[0] || '',
        content: item.textContent?.trim() || ''
      })).filter(item => item.symbol);
    });

    // Data consistency check (symbols should remain the same)
    if (initialData.length > 0 && afterNavigationData.length > 0) {
      const initialSymbols = initialData.map(item => item.symbol).sort();
      const afterSymbols = afterNavigationData.map(item => item.symbol).sort();

      // Symbol lists should be consistent
      expect(afterSymbols).toEqual(initialSymbols);
    }

    // Refresh page and check data persistence
    await page.reload();
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    const afterReloadData = await page.evaluate(() => {
      const portfolioItems = Array.from(document.querySelectorAll('[data-symbol], .portfolio-item'));
      return portfolioItems.map(item => ({
        symbol: item.textContent?.match(/[A-Z]{1,5}/)?.[0] || '',
        content: item.textContent?.trim() || ''
      })).filter(item => item.symbol);
    });

    // Data should persist after reload
    if (initialData.length > 0 && afterReloadData.length > 0) {
      const initialSymbols = initialData.map(item => item.symbol).sort();
      const reloadSymbols = afterReloadData.map(item => item.symbol).sort();

      expect(reloadSymbols).toEqual(initialSymbols);
    }
  });
});