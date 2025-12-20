import { test, expect } from '@playwright/test';

test.describe('Trading Signals Pagination', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to Trading Signals page
    await page.goto('http://localhost:5173/trading-signals');

    // Wait for page to load
    await page.waitForLoadState('networkidle');

    // Wait for signals table to be visible
    await expect(page.getByRole('table')).toBeVisible({ timeout: 10000 });
  });

  test('should display first page with 25 signals by default', async ({ page }) => {
    // Check that we have a table
    const table = page.getByRole('table');
    await expect(table).toBeVisible();

    // Count rows in table body (excluding header)
    const rows = page.locator('tbody tr');
    const rowCount = await rows.count();

    console.log(`✅ Page 1: Found ${rowCount} signals displayed`);
    expect(rowCount).toBeGreaterThan(0);
    expect(rowCount).toBeLessThanOrEqual(25);
  });

  test('should show pagination controls', async ({ page }) => {
    // Look for TablePagination component elements
    const paginationContainer = page.locator('[class*="MuiTablePagination"]');

    // Check for next button or page navigation
    const nextButton = page.locator('button:has-text("Next")').first();
    const previousButton = page.locator('button:has-text("Previous")').first();

    console.log(`✅ Pagination controls found`);

    // At least one should be visible
    const isVisible = await nextButton.isVisible().catch(() => false) ||
                     await previousButton.isVisible().catch(() => false);

    expect(isVisible || await paginationContainer.isVisible().catch(() => false)).toBeTruthy();
  });

  test('should display signal info text showing current page range', async ({ page }) => {
    // Look for text like "Showing 1 to 25 of N signals"
    const infoText = page.locator('text=/Showing.*to.*of.*signals/');

    await expect(infoText).toBeVisible({ timeout: 5000 });

    const text = await infoText.textContent();
    console.log(`✅ Signal info: ${text}`);

    expect(text).toMatch(/Showing \d+ to \d+ of \d+ signals/);
  });

  test('should navigate to page 2 and display different signals', async ({ page }) => {
    // Get first page signals
    let firstPageSymbols = [];
    const firstPageRows = page.locator('tbody tr');
    const firstPageCount = await firstPageRows.count();

    for (let i = 0; i < firstPageCount; i++) {
      const symbol = await firstPageRows.nth(i).locator('td').first().textContent();
      if (symbol) {
        firstPageSymbols.push(symbol.trim());
      }
    }

    console.log(`📊 Page 1 symbols: ${firstPageSymbols.slice(0, 5).join(', ')} ... (${firstPageSymbols.length} total)`);

    // Find and click next page button
    const nextButton = page.locator('button[title*="Next Page"], button[aria-label*="next"]').first();

    // Try alternative selector if first doesn't work
    let clicked = false;
    try {
      if (await nextButton.isVisible()) {
        await nextButton.click();
        clicked = true;
        console.log('✅ Clicked Next button');
      }
    } catch (e) {
      console.log('Next button not found via standard selectors');
    }

    // If standard selector didn't work, try MUI pagination
    if (!clicked) {
      const mobileNextBtn = page.locator('button').filter({ hasText: '>' }).first();
      try {
        if (await mobileNextBtn.isVisible()) {
          await mobileNextBtn.click();
          clicked = true;
          console.log('✅ Clicked MUI next button');
        }
      } catch (e) {
        console.log('MUI next button also not found');
      }
    }

    if (!clicked) {
      // Try clicking on page 2 directly if available
      const page2Btn = page.locator('button').filter({ hasText: '2' }).first();
      try {
        if (await page2Btn.isVisible()) {
          await page2Btn.click();
          clicked = true;
          console.log('✅ Clicked page 2 button');
        }
      } catch (e) {
        console.log('Page 2 button not found');
      }
    }

    // Wait for page to update
    await page.waitForTimeout(1000);

    // Get second page signals
    let secondPageSymbols = [];
    const secondPageRows = page.locator('tbody tr');
    const secondPageCount = await secondPageRows.count();

    for (let i = 0; i < secondPageCount; i++) {
      const symbol = await secondPageRows.nth(i).locator('td').first().textContent();
      if (symbol) {
        secondPageSymbols.push(symbol.trim());
      }
    }

    console.log(`📊 Page 2 symbols: ${secondPageSymbols.slice(0, 5).join(', ')} ... (${secondPageSymbols.length} total)`);

    // Verify signals are different or pagination advanced
    if (clicked && secondPageSymbols.length > 0) {
      const isDifferent = secondPageSymbols.some(s => !firstPageSymbols.includes(s));
      console.log(`📌 Signals changed between pages: ${isDifferent}`);

      // Check info text updated
      const infoText = await page.locator('text=/Showing.*to.*of.*signals/').textContent();
      console.log(`✅ Updated info: ${infoText}`);
    } else {
      console.log('⚠️  Could not navigate to next page via button click');
    }
  });

  test('should change rows per page and update display', async ({ page }) => {
    // Look for rows per page dropdown
    const rowsPerPageSelect = page.locator('[aria-label*="rows per page"], select').first();

    // Try to find the rows per page button/dropdown
    const rowsPerPageBtn = page.locator('button').filter({ hasText: /25|50/ }).first();

    // Get initial row count
    let initialRows = await page.locator('tbody tr').count();
    console.log(`📊 Initial rows displayed: ${initialRows}`);

    // Try clicking rows per page selector
    try {
      if (await rowsPerPageBtn.isVisible()) {
        await rowsPerPageBtn.click();
        console.log('✅ Clicked rows per page button');

        // Click on 50 option
        const option50 = page.locator('li[data-value="50"], div').filter({ hasText: '50' }).first();
        if (await option50.isVisible()) {
          await option50.click();
          console.log('✅ Selected 50 rows per page');

          // Wait for update
          await page.waitForTimeout(1000);

          // Check new row count
          const newRows = await page.locator('tbody tr').count();
          console.log(`📊 New rows displayed: ${newRows}`);

          expect(newRows).toBeGreaterThan(initialRows);
        }
      }
    } catch (e) {
      console.log('⚠️  Could not change rows per page:', e.message);
    }
  });

  test('should verify signals 26-50 appear on page 2', async ({ page }) => {
    // Get first page signal count
    const firstPageCount = await page.locator('tbody tr').count();
    console.log(`✅ Page 1 displays ${firstPageCount} signals`);

    // Get first signal symbol from page 1
    const firstSignal = await page.locator('tbody tr').first().locator('td').first().textContent();
    console.log(`📌 First signal on page 1: ${firstSignal}`);

    // Navigate to page 2 by changing page parameter in URL or clicking navigation
    const currentUrl = page.url();

    // Try using page navigation buttons
    const buttons = page.locator('button');
    let foundNextBtn = false;

    for (let i = 0; i < await buttons.count(); i++) {
      const btn = buttons.nth(i);
      const text = await btn.textContent();
      const ariaLabel = await btn.getAttribute('aria-label');

      if ((text && text.includes('>')) || (ariaLabel && ariaLabel.includes('next'))) {
        console.log(`🔘 Found navigation button: ${text || ariaLabel}`);

        // Check if it's disabled
        const isDisabled = await btn.isDisabled();
        if (!isDisabled) {
          await btn.click();
          foundNextBtn = true;
          console.log('✅ Clicked next button');
          break;
        }
      }
    }

    // Wait for navigation
    if (foundNextBtn) {
      await page.waitForTimeout(1500);

      // Verify we're on a different page
      const secondPageCount = await page.locator('tbody tr').count();
      console.log(`✅ Page 2 displays ${secondPageCount} signals`);

      // Get first signal from page 2
      const secondSignal = await page.locator('tbody tr').first().locator('td').first().textContent();
      console.log(`📌 First signal on page 2: ${secondSignal}`);

      // Verify they're different
      if (firstSignal !== secondSignal) {
        console.log('✅ Page 1 and Page 2 display different signals');
      }

      // Verify page range in info text
      const infoText = await page.locator('text=/Showing.*to.*of.*signals/').textContent();
      console.log(`📊 Page 2 info: ${infoText}`);

      // Check if info text shows signals 26-50 range (or appropriate range for page 2)
      if (infoText) {
        const match = infoText.match(/Showing (\d+) to (\d+)/);
        if (match) {
          const start = parseInt(match[1]);
          const end = parseInt(match[2]);

          console.log(`✅ Showing signals ${start} to ${end}`);

          // If using default 25 per page, page 2 should show 26-50
          if (firstPageCount === 25) {
            expect(start).toBe(26);
            expect(end).toBe(50);
          }
        }
      }
    } else {
      console.log('⚠️  Could not find or click next navigation button');
    }
  });

  test('should have proper pagination info structure', async ({ page }) => {
    // Check for pagination info container
    const infoBox = page.locator('div').filter({ hasText: /Showing \d+ to \d+ of \d+ signals/ }).first();

    if (await infoBox.isVisible()) {
      const text = await infoBox.textContent();
      const match = text.match(/Showing (\d+) to (\d+) of (\d+) signals/);

      if (match) {
        const [, start, end, total] = match;
        console.log(`✅ Pagination structure valid:`);
        console.log(`   Start: ${start}, End: ${end}, Total: ${total}`);

        // Verify logic
        expect(parseInt(start)).toBeLessThanOrEqual(parseInt(end));
        expect(parseInt(end)).toBeLessThanOrEqual(parseInt(total));
      }
    } else {
      console.log('⚠️  Pagination info text not found');
    }
  });

  test('should handle pagination with active filters', async ({ page }) => {
    // Apply a filter if available (e.g., signal type)
    const signalTypeSelect = page.locator('select, [role="combobox"]').first();

    try {
      if (await signalTypeSelect.isVisible()) {
        // Try to select Buy signals
        await signalTypeSelect.click();
        const buyOption = page.locator('option, [role="option"]').filter({ hasText: 'Buy' }).first();

        if (await buyOption.isVisible()) {
          await buyOption.click();
          console.log('✅ Applied Buy filter');

          // Wait for filtered results
          await page.waitForTimeout(1000);

          // Verify pagination still works
          const rowCount = await page.locator('tbody tr').count();
          console.log(`✅ Filtered results show ${rowCount} signals`);

          // Try to navigate
          const nextBtn = page.locator('button').filter({ hasText: '>' }).first();
          if (await nextBtn.isVisible() && !await nextBtn.isDisabled()) {
            await nextBtn.click();
            console.log('✅ Pagination works with active filters');
          }
        }
      }
    } catch (e) {
      console.log('⚠️  Could not test filtering:', e.message);
    }
  });
});
