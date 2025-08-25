/**
 * Button Name Debug Script - Find buttons missing discernible text
 */

import { chromium } from 'playwright';
import AxeBuilder from '@axe-core/playwright';

async function debugButtonNames() {
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

  const pagesWithButtonIssues = [
    { name: 'Real-Time Data', url: 'realtime' },
    { name: 'Watchlist', url: 'watchlist' },
    { name: 'Scores Dashboard', url: 'scores' }
  ];

  for (const pageInfo of pagesWithButtonIssues) {
    console.log(`\n🔘 ${pageInfo.name.toUpperCase()} BUTTON ANALYSIS:`);
    console.log('='.repeat(60));
    
    try {
      await page.goto(`http://localhost:3001/${pageInfo.url}`);
      await page.waitForTimeout(4000);
      
      const accessibilityScanResults = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
        .analyze();
      
      const buttonNameViolations = accessibilityScanResults.violations.filter(
        violation => violation.id === 'button-name'
      );
      
      if (buttonNameViolations.length > 0) {
        buttonNameViolations.forEach(violation => {
          console.log(`\n❌ ${violation.description}`);
          console.log(`   Impact: ${violation.impact} | Elements: ${violation.nodes.length}`);
          
          violation.nodes.slice(0, 5).forEach((node, index) => {
            console.log(`\n   ${index + 1}. Button HTML:`);
            console.log(`      ${node.html.slice(0, 200)}${node.html.length > 200 ? '...' : ''}`);
            console.log(`      Selector: ${node.target[0]}`);
            console.log(`      Issue: ${node.failureSummary}`);
          });
        });
      } else {
        console.log('✅ No button name violations found!');
      }
      
    } catch (error) {
      console.log(`❌ Error testing ${pageInfo.name}: ${error.message}`);
    }
  }
  
  await browser.close();
  console.log('\n✅ Button name analysis complete!');
}

debugButtonNames().catch(console.error);