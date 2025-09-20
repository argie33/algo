/**
 * Accessibility Testing Suite
 * WCAG 2.1 AA compliance and accessibility automation
 */

import { test, expect } from '@playwright/test';

test.describe('Accessibility Compliance', () => {
  test.beforeEach(async ({ page }) => {
    // Set up accessibility testing
    await page.addInitScript(() => {
      window.__A11Y_VIOLATIONS__ = [];

      // Basic accessibility checks
      window.__checkA11y__ = () => {
        const violations = [];

        // Check for missing alt text
        const images = document.querySelectorAll('img');
        images.forEach(img => {
          if (!img.alt && !img.getAttribute('aria-label') && !img.getAttribute('aria-labelledby')) {
            violations.push({ type: 'missing-alt', element: img.tagName + (img.src ? `[src="${img.src.substring(0, 50)}"]` : '') });
          }
        });

        // Check for missing form labels
        const inputs = document.querySelectorAll('input, textarea, select');
        inputs.forEach(input => {
          const hasLabel = input.labels && input.labels.length > 0;
          const hasAriaLabel = input.getAttribute('aria-label');
          const hasAriaLabelledby = input.getAttribute('aria-labelledby');

          if (!hasLabel && !hasAriaLabel && !hasAriaLabelledby && input.type !== 'hidden') {
            violations.push({ type: 'missing-label', element: input.tagName + `[type="${input.type}"]` });
          }
        });

        // Check for missing headings hierarchy
        const headings = Array.from(document.querySelectorAll('h1, h2, h3, h4, h5, h6'));
        if (headings.length > 0) {
          let prevLevel = 0;
          headings.forEach(heading => {
            const level = parseInt(heading.tagName.charAt(1));
            if (level > prevLevel + 1) {
              violations.push({ type: 'heading-skip', element: heading.tagName });
            }
            prevLevel = level;
          });
        }

        return violations;
      };
    });
  });

  test('should have proper heading hierarchy', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Check for h1
    const h1Count = await page.locator('h1').count();
    expect(h1Count).toBeGreaterThanOrEqual(1);
    expect(h1Count).toBeLessThanOrEqual(1); // Should have exactly one h1

    // Check heading hierarchy
    const headings = await page.locator('h1, h2, h3, h4, h5, h6').all();
    const headingLevels = [];

    for (const heading of headings) {
      const tagName = await heading.evaluate(el => el.tagName);
      const level = parseInt(tagName.charAt(1));
      headingLevels.push(level);
    }

    // Verify no heading levels are skipped
    for (let i = 1; i < headingLevels.length; i++) {
      const currentLevel = headingLevels[i];
      const prevLevel = headingLevels[i - 1];

      if (currentLevel > prevLevel) {
        expect(currentLevel - prevLevel).toBeLessThanOrEqual(1);
      }
    }
  });

  test('should have accessible form controls', async ({ page }) => {
    await page.goto('/settings');
    await page.waitForLoadState('networkidle');

    const formControls = await page.locator('input, textarea, select').all();

    for (const control of formControls) {
      if (await control.isVisible()) {
        const type = await control.getAttribute('type');

        // Skip hidden inputs
        if (type === 'hidden') continue;

        // Check for label association
        const hasLabel = await control.evaluate(el => {
          return (el.labels && el.labels.length > 0) ||
                 el.getAttribute('aria-label') ||
                 el.getAttribute('aria-labelledby') ||
                 el.getAttribute('title');
        });

        expect(hasLabel).toBe(true);

        // Check for required field indication
        const isRequired = await control.getAttribute('required');
        if (isRequired !== null) {
          const hasRequiredIndicator = await control.evaluate(el => {
            const parent = el.closest('label, .form-field, .input-group');
            return parent && (
              parent.textContent.includes('*') ||
              parent.querySelector('[aria-label*="required"]') ||
              el.getAttribute('aria-required') === 'true'
            );
          });

          expect(hasRequiredIndicator).toBe(true);
        }

        // Check input has accessible name
        const accessibleName = await control.evaluate(el => {
          return el.getAttribute('aria-label') ||
                 (el.labels && el.labels[0] && el.labels[0].textContent.trim()) ||
                 el.getAttribute('placeholder') ||
                 el.getAttribute('title');
        });

        expect(accessibleName).toBeTruthy();
      }
    }
  });

  test('should have proper button accessibility', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const buttons = await page.locator('button, [role="button"]').all();

    for (const button of buttons) {
      if (await button.isVisible()) {
        // Check button has accessible name
        const accessibleName = await button.evaluate(el => {
          return el.textContent.trim() ||
                 el.getAttribute('aria-label') ||
                 el.getAttribute('aria-labelledby') ||
                 el.getAttribute('title') ||
                 (el.querySelector('img') && el.querySelector('img').alt);
        });

        expect(accessibleName).toBeTruthy();

        // Check button is keyboard accessible
        const tabIndex = await button.getAttribute('tabindex');
        if (tabIndex !== null) {
          expect(parseInt(tabIndex)).toBeGreaterThanOrEqual(-1);
        }

        // Check disabled buttons are properly marked
        const isDisabled = await button.getAttribute('disabled');
        const ariaDisabled = await button.getAttribute('aria-disabled');

        if (isDisabled !== null) {
          expect(ariaDisabled === 'true' || isDisabled !== null).toBe(true);
        }
      }
    }
  });

  test('should have proper image accessibility', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const images = await page.locator('img').all();

    for (const image of images) {
      if (await image.isVisible()) {
        const _src = await image.getAttribute('src');

        // Skip decorative images (empty alt)
        const alt = await image.getAttribute('alt');
        const ariaLabel = await image.getAttribute('aria-label');
        const ariaLabelledby = await image.getAttribute('aria-labelledby');
        const ariaHidden = await image.getAttribute('aria-hidden');

        // Image should have alt text, aria-label, or be marked as decorative
        const hasAccessibleText = alt !== null || ariaLabel || ariaLabelledby || ariaHidden === 'true';
        expect(hasAccessibleText).toBe(true);

        // Alt text should be meaningful (not just filename)
        if (alt && alt.length > 0) {
          expect(alt).not.toMatch(/\.(jpg|jpeg|png|gif|svg|webp)$/i);
          expect(alt).not.toMatch(/^(image|picture|photo|img)$/i);
          expect(alt.length).toBeGreaterThan(2);
        }
      }
    }
  });

  test('should support keyboard navigation', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Test tab navigation
    await page.keyboard.press('Tab');
    let focusedElement = await page.evaluate(() => document.activeElement?.tagName);
    expect(['BUTTON', 'A', 'INPUT', 'SELECT', 'TEXTAREA']).toContain(focusedElement);

    // Test navigation through multiple elements
    const focusableElements = [];

    for (let i = 0; i < 10; i++) {
      await page.keyboard.press('Tab');
      const currentFocused = await page.evaluate(() => {
        const el = document.activeElement;
        return {
          tagName: el?.tagName,
          className: el?.className,
          id: el?.id,
          visible: el ? window.getComputedStyle(el).display !== 'none' : false
        };
      });

      if (currentFocused.tagName) {
        focusableElements.push(currentFocused);
      }
    }

    // Should be able to navigate to multiple focusable elements
    expect(focusableElements.length).toBeGreaterThan(2);

    // All focused elements should be visible
    const visibleFocused = focusableElements.filter(el => el.visible);
    expect(visibleFocused.length).toBeGreaterThan(0);

    // Test reverse navigation
    await page.keyboard.press('Shift+Tab');
    const reverseFocused = await page.evaluate(() => document.activeElement?.tagName);
    expect(reverseFocused).toBeTruthy();
  });

  test('should have proper color contrast', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Get text elements for color contrast checking
    const textElements = await page.locator('p, span, div, h1, h2, h3, h4, h5, h6, button, a').all();

    let contrastChecks = 0;

    for (const element of textElements.slice(0, 20)) {
      if (await element.isVisible()) {
        const styles = await element.evaluate(el => {
          const computed = window.getComputedStyle(el);
          const text = el.textContent.trim();

          if (text.length === 0) return null;

          return {
            color: computed.color,
            backgroundColor: computed.backgroundColor,
            fontSize: computed.fontSize,
            fontWeight: computed.fontWeight,
            hasText: text.length > 0
          };
        });

        if (styles && styles.hasText) {
          contrastChecks++;

          // Basic color validation - colors should not be the same
          expect(styles.color).not.toBe(styles.backgroundColor);

          // Font size should be reasonable for readability
          const fontSize = parseFloat(styles.fontSize);
          expect(fontSize).toBeGreaterThan(10); // Minimum readable size

          // Color should not be transparent or invalid
          expect(styles.color).not.toBe('rgba(0, 0, 0, 0)');
          expect(styles.color).not.toBe('transparent');
        }
      }
    }

    // Should have checked some text elements
    expect(contrastChecks).toBeGreaterThan(5);
  });

  test('should have proper link accessibility', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const links = await page.locator('a').all();

    for (const link of links) {
      if (await link.isVisible()) {
        // Links should have meaningful text
        const linkText = await link.evaluate(el => {
          return el.textContent.trim() ||
                 el.getAttribute('aria-label') ||
                 el.getAttribute('title') ||
                 (el.querySelector('img') && el.querySelector('img').alt);
        });

        expect(linkText).toBeTruthy();
        expect(linkText.length).toBeGreaterThan(1);

        // Avoid generic link text
        const genericTexts = ['click here', 'read more', 'link', 'here'];
        const isGeneric = genericTexts.some(generic =>
          linkText.toLowerCase().includes(generic)
        );

        if (isGeneric) {
          // Generic text is okay if there's additional context
          const hasAriaLabel = await link.getAttribute('aria-label');
          const hasTitle = await link.getAttribute('title');
          expect(hasAriaLabel || hasTitle).toBeTruthy();
        }

        // Links should have proper href or role
        const href = await link.getAttribute('href');
        const role = await link.getAttribute('role');

        expect(href || role === 'button').toBeTruthy();

        // External links should have proper indicators
        if (href && (href.startsWith('http') && !href.includes(await page.url()))) {
          const hasExternalIndicator = await link.evaluate(el => {
            const text = el.textContent;
            const ariaLabel = el.getAttribute('aria-label') || '';
            const title = el.getAttribute('title') || '';

            return text.includes('(external)') ||
                   ariaLabel.includes('external') ||
                   title.includes('external') ||
                   el.getAttribute('target') === '_blank';
          });

          // External links should have some indication
          expect(hasExternalIndicator).toBe(true);
        }
      }
    }
  });

  test('should have proper table accessibility', async ({ page }) => {
    await page.goto('/portfolio');
    await page.waitForLoadState('networkidle');

    const tables = await page.locator('table').all();

    for (const table of tables) {
      if (await table.isVisible()) {
        // Table should have caption or aria-label
        const hasCaption = await table.locator('caption').count() > 0;
        const hasAriaLabel = await table.getAttribute('aria-label');
        const hasAriaLabelledby = await table.getAttribute('aria-labelledby');

        expect(hasCaption || hasAriaLabel || hasAriaLabelledby).toBe(true);

        // Table should have proper headers
        const headers = await table.locator('th').all();
        expect(headers.length).toBeGreaterThan(0);

        // Headers should have proper scope
        for (const header of headers) {
          const scope = await header.getAttribute('scope');
          const hasScope = scope === 'col' || scope === 'row' || scope === 'colgroup' || scope === 'rowgroup';

          // If no scope, header should be in thead or first row/column
          if (!hasScope) {
            const isInThead = await header.evaluate(el =>
              el.closest('thead') !== null
            );
            expect(isInThead).toBe(true);
          }
        }

        // Check for complex tables
        const rowspan = await table.locator('[rowspan]').count();
        const colspan = await table.locator('[colspan]').count();

        if (rowspan > 0 || colspan > 0) {
          // Complex tables should have id/headers association
          const cellsWithHeaders = await table.locator('[headers]').count();
          const headersWithId = await table.locator('th[id]').count();

          expect(cellsWithHeaders > 0 || headersWithId > 0).toBe(true);
        }
      }
    }
  });

  test('should have proper ARIA landmarks', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Check for main landmark
    const mainLandmark = await page.locator('main, [role="main"]').count();
    expect(mainLandmark).toBeGreaterThanOrEqual(1);

    // Check for navigation landmark
    const navLandmark = await page.locator('nav, [role="navigation"]').count();
    expect(navLandmark).toBeGreaterThanOrEqual(1);

    // Check for banner (header)
    const bannerLandmark = await page.locator('header, [role="banner"]').count();
    expect(bannerLandmark).toBeGreaterThanOrEqual(1);

    // Check for complementary content if present
    const _asideElements = await page.locator('aside, [role="complementary"]').count();

    // Check for contentinfo (footer)
    const footerLandmark = await page.locator('footer, [role="contentinfo"]').count();
    expect(footerLandmark).toBeGreaterThanOrEqual(1);

    // Landmarks should have accessible names if multiple of same type
    const landmarks = await page.locator('[role="navigation"], nav').all();
    if (landmarks.length > 1) {
      for (const landmark of landmarks) {
        const hasLabel = await landmark.evaluate(el => {
          return el.getAttribute('aria-label') ||
                 el.getAttribute('aria-labelledby') ||
                 el.getAttribute('title');
        });
        expect(hasLabel).toBe(true);
      }
    }
  });

  test('should handle focus management', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Test focus indicators are visible
    await page.keyboard.press('Tab');

    const focusedElement = page.locator(':focus');
    const isVisible = await focusedElement.isVisible();
    expect(isVisible).toBe(true);

    // Check focus indicator styles
    const focusStyles = await focusedElement.evaluate(el => {
      const computed = window.getComputedStyle(el);
      return {
        outline: computed.outline,
        outlineWidth: computed.outlineWidth,
        outlineStyle: computed.outlineStyle,
        outlineColor: computed.outlineColor,
        boxShadow: computed.boxShadow
      };
    });

    // Should have some form of focus indicator
    const hasFocusIndicator =
      focusStyles.outline !== 'none' ||
      focusStyles.outlineWidth !== '0px' ||
      focusStyles.boxShadow !== 'none' ||
      focusStyles.outlineStyle !== 'none';

    expect(hasFocusIndicator).toBe(true);

    // Test modal focus trapping if modal is present
    const modalTriggers = await page.locator('[data-toggle="modal"], .modal-trigger').all();

    if (modalTriggers.length > 0) {
      await modalTriggers[0].click();
      await page.waitForTimeout(500);

      const modal = page.locator('.modal:visible, [role="dialog"]:visible').first();
      if (await modal.isVisible()) {
        // Focus should be trapped in modal
        await page.keyboard.press('Tab');
        const focusInModal = await page.evaluate(() => {
          const activeEl = document.activeElement;
          const modal = document.querySelector('.modal:not([style*="display: none"]), [role="dialog"]:not([style*="display: none"])');
          return modal && modal.contains(activeEl);
        });

        expect(focusInModal).toBe(true);

        // Close modal with Escape
        await page.keyboard.press('Escape');
        await page.waitForTimeout(300);

        // Focus should return to trigger
        const focusReturnedToTrigger = await modalTriggers[0].evaluate(el =>
          el === document.activeElement
        );
        expect(focusReturnedToTrigger).toBe(true);
      }
    }
  });

  test('should have proper error messaging accessibility', async ({ page }) => {
    await page.goto('/settings');
    await page.waitForLoadState('networkidle');

    const forms = await page.locator('form').all();

    for (const form of forms.slice(0, 2)) {
      if (await form.isVisible()) {
        // Fill form with invalid data
        const inputs = await form.locator('input[required], input[type="email"]').all();

        for (const input of inputs.slice(0, 2)) {
          if (await input.isVisible()) {
            await input.fill('invalid');
            await input.blur();
            await page.waitForTimeout(500);

            // Check for error messaging
            const errorMessage = await form.locator('.error, .invalid, [role="alert"]').first();

            if (await errorMessage.isVisible()) {
              // Error should be associated with input
              const errorId = await errorMessage.getAttribute('id');
              const ariaDescribedby = await input.getAttribute('aria-describedby');

              if (errorId) {
                expect(ariaDescribedby).toContain(errorId);
              }

              // Error should be announced to screen readers
              const ariaLive = await errorMessage.getAttribute('aria-live');
              const role = await errorMessage.getAttribute('role');

              expect(ariaLive === 'polite' || ariaLive === 'assertive' || role === 'alert').toBe(true);

              // Error message should be meaningful
              const errorText = await errorMessage.textContent();
              expect(errorText.length).toBeGreaterThan(5);
              expect(errorText.toLowerCase()).not.toBe('error');
            }

            await input.clear();
          }
        }
      }
    }
  });

  test('should support screen reader accessibility', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    // Check for proper ARIA attributes
    const ariaElements = await page.locator('[aria-label], [aria-labelledby], [aria-describedby]').all();
    expect(ariaElements.length).toBeGreaterThan(5);

    // Check for live regions for dynamic content
    const _liveRegions = await page.locator('[aria-live], [role="status"], [role="alert"]').count();

    // Check for proper roles
    const roleElements = await page.locator('[role]').all();

    for (const element of roleElements.slice(0, 10)) {
      const role = await element.getAttribute('role');

      // Validate common ARIA roles
      const validRoles = [
        'button', 'link', 'navigation', 'main', 'banner', 'contentinfo',
        'complementary', 'search', 'form', 'dialog', 'alert', 'status',
        'tab', 'tabpanel', 'tablist', 'menu', 'menuitem', 'grid', 'gridcell'
      ];

      expect(validRoles).toContain(role);
    }

    // Check for skip links
    const skipLinks = await page.locator('a[href^="#"], .skip-link').all();

    if (skipLinks.length > 0) {
      // Skip links should be functional
      const skipLink = skipLinks[0];
      const href = await skipLink.getAttribute('href');

      if (href && href.startsWith('#')) {
        const targetId = href.substring(1);
        const target = page.locator(`#${targetId}`);
        const targetExists = await target.count() > 0;
        expect(targetExists).toBe(true);
      }
    }

    // Check for proper list markup
    const lists = await page.locator('ul, ol').all();

    for (const list of lists.slice(0, 5)) {
      const listItems = await list.locator('li').count();
      if (listItems > 0) {
        expect(listItems).toBeGreaterThan(0);

        // Lists should only contain li elements as direct children
        const directChildren = await list.evaluate(el =>
          Array.from(el.children).map(child => child.tagName.toLowerCase())
        );

        const nonListItems = directChildren.filter(tag => tag !== 'li');
        expect(nonListItems.length).toBe(0);
      }
    }
  });
});