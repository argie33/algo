import { chromium } from 'playwright';

async function checkUI() {
  try {
    const browser = await chromium.launch();
    const page = await browser.newPage();

    await page.goto('http://localhost:5179', { waitUntil: 'networkidle' });
    
    // Wait for rendering
    await page.waitForTimeout(2000);

    // Take screenshot
    await page.screenshot({ path: 'app-screenshot.png', fullPage: true });
    console.log('Screenshot saved: app-screenshot.png');

    // Check page structure
    const title = await page.title();
    console.log(`Page title: ${title}`);

    // Get all visible text
    const content = await page.evaluate(() => {
      return {
        headings: Array.from(document.querySelectorAll('h1, h2, h3')).map(h => h.textContent),
        buttons: Array.from(document.querySelectorAll('button')).map(b => b.textContent.trim()).filter(t => t),
        links: Array.from(document.querySelectorAll('a')).map(a => a.textContent.trim()).filter(t => t),
        hasErrors: document.querySelector('[role="alert"]') ? 'YES' : 'NO'
      };
    });

    console.log('\nPage structure:');
    console.log(`  Headings: ${content.headings.join(', ')}`);
    console.log(`  Buttons: ${content.buttons.slice(0, 5).join(', ')}`);
    console.log(`  Links: ${content.links.slice(0, 5).join(', ')}`);
    console.log(`  Error alerts: ${content.hasErrors}`);

    // Check for accessibility issues
    const a11y = await page.evaluate(() => {
      const issues = [];
      
      // Check for images without alt text
      document.querySelectorAll('img').forEach(img => {
        if (!img.alt) issues.push(`Image without alt: ${img.src}`);
      });

      // Check for missing form labels
      document.querySelectorAll('input').forEach(input => {
        if (!input.id || !document.querySelector(`label[for="${input.id}"]`)) {
          if (!input.getAttribute('aria-label')) {
            issues.push(`Input without label: ${input.name || input.type}`);
          }
        }
      });

      return issues;
    });

    if (a11y.length > 0) {
      console.log('\nAccessibility issues found:');
      a11y.forEach(issue => console.log(`  ⚠️  ${issue}`));
    } else {
      console.log('\n✅ No obvious accessibility issues');
    }

    await browser.close();

  } catch (error) {
    console.error('Error:', error.message);
    process.exit(1);
  }
}

checkUI();
