/**
 * Color Contrast Debug Script - Find elements with insufficient contrast
 */

import { chromium } from 'playwright';
import AxeBuilder from '@axe-core/playwright';

async function debugColorContrast() {
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();
  
  await page.addInitScript(() => {
    localStorage.setItem('financial_auth_token', 'a11y-test-token');
    localStorage.setItem('api_keys_status', JSON.stringify({
      alpaca: { configured: true, valid: true },
      polygon: { configured: true, valid: true },
      finnhub: { configured: true, valid: true }
    }));
  });
  
  await page.route('**/api/**', route => {
    route.fulfill({ json: { success: true, data: {} } });
  });

  const pagesWithContrastIssues = [
    { name: 'Real-Time Data', url: 'realtime' },
    { name: 'Watchlist', url: 'watchlist' },
    { name: 'Backtest', url: 'backtest' },
    { name: 'Service Health', url: 'service-health' }
  ];

  for (const pageInfo of pagesWithContrastIssues) {
    console.log(`\n🎨 ${pageInfo.name.toUpperCase()} COLOR CONTRAST ANALYSIS:`);
    console.log('='.repeat(60));
    
    try {
      await page.goto(`http://localhost:3001/${pageInfo.url}`);
      await page.waitForTimeout(4000);
      
      const accessibilityScanResults = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
        .analyze();
      
      const contrastViolations = accessibilityScanResults.violations.filter(
        violation => violation.id === 'color-contrast'
      );
      
      if (contrastViolations.length > 0) {
        contrastViolations.forEach(violation => {
          console.log(`\n❌ ${violation.description}`);
          console.log(`   Impact: ${violation.impact} | Elements: ${violation.nodes.length}`);
          
          violation.nodes.slice(0, 5).forEach((node, index) => {
            console.log(`\n   ${index + 1}. Element:`);
            console.log(`      HTML: ${node.html.slice(0, 150)}${node.html.length > 150 ? '...' : ''}`);
            console.log(`      Selector: ${node.target[0]}`);
            console.log(`      Issue: ${node.failureSummary}`);
            
            // Additional info if available
            if (node.any && node.any[0] && node.any[0].data) {
              const data = node.any[0].data;
              console.log(`      Contrast ratio: ${data.contrastRatio || 'N/A'}`);
              console.log(`      Expected: ${data.expectedContrastRatio || 'N/A'}`);
              console.log(`      Foreground: ${data.fgColor || 'N/A'}`);
              console.log(`      Background: ${data.bgColor || 'N/A'}`);
            }
          });
        });
      } else {
        console.log('✅ No color contrast violations found!');
      }
      
    } catch (error) {
      console.log(`❌ Error testing ${pageInfo.name}: ${error.message}`);
    }
  }
  
  await browser.close();
  console.log('\n✅ Color contrast analysis complete!');
}

debugColorContrast().catch(console.error);