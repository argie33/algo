/**
 * ARIA Input Field Name Debug Script - Find input fields missing accessible names
 */

import { chromium } from 'playwright';
import AxeBuilder from '@axe-core/playwright';

async function debugAriaInputFields() {
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

  const pagesWithInputIssues = [
    { name: 'Technical Analysis', url: 'technical-analysis' },
    { name: 'Sentiment Analysis', url: 'sentiment-analysis' },
    { name: 'Backtest', url: 'backtest' }
  ];

  for (const pageInfo of pagesWithInputIssues) {
    console.log(`\n📝 ${pageInfo.name.toUpperCase()} ARIA INPUT FIELD ANALYSIS:`);
    console.log('='.repeat(60));
    
    try {
      await page.goto(`http://localhost:3000/${pageInfo.url}`);
      await page.waitForTimeout(4000);
      
      const accessibilityScanResults = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
        .analyze();
      
      const inputViolations = accessibilityScanResults.violations.filter(
        violation => violation.id === 'aria-input-field-name'
      );
      
      if (inputViolations.length > 0) {
        inputViolations.forEach(violation => {
          console.log(`\n❌ ${violation.description}`);
          console.log(`   Impact: ${violation.impact} | Elements: ${violation.nodes.length}`);
          
          violation.nodes.forEach((node, index) => {
            console.log(`\n   ${index + 1}. Element:`);
            console.log(`      HTML: ${node.html.slice(0, 200)}${node.html.length > 200 ? '...' : ''}`);
            console.log(`      Selector: ${node.target[0]}`);
            console.log(`      Issue: ${node.failureSummary}`);
            
            // Additional element analysis
            if (node.any && node.any[0] && node.any[0].data) {
              console.log(`      Data: ${JSON.stringify(node.any[0].data, null, 8)}`);
            }
          });
        });
      } else {
        console.log('✅ No ARIA input field violations found!');
      }
      
    } catch (error) {
      console.log(`❌ Error testing ${pageInfo.name}: ${error.message}`);
    }
  }
  
  await browser.close();
  console.log('\n✅ ARIA input field analysis complete!');
}

debugAriaInputFields().catch(console.error);