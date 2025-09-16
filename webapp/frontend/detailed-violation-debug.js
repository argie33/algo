/**
 * Detailed Violation Debug - Get specific elements for each violation type
 */

import { chromium } from 'playwright';
import AxeBuilder from '@axe-core/playwright';

async function debugAllViolations() {
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

  const targetPages = [
    { name: 'Technical Analysis', url: 'technical-analysis', violations: ['aria-input-field-name'] },
    { name: 'Sentiment Analysis', url: 'sentiment-analysis', violations: ['aria-input-field-name', 'aria-progressbar-name'] },
    { name: 'Earnings Calendar', url: 'earnings-calendar', violations: ['aria-progressbar-name'] },
    { name: 'Service Health', url: 'service-health', violations: ['nested-interactive'] }
  ];

  for (const pageInfo of targetPages) {
    console.log(`\n🔍 ${pageInfo.name.toUpperCase()} DETAILED ANALYSIS:`);
    console.log('='.repeat(70));
    
    try {
      await page.goto(`http://localhost:3000/${pageInfo.url}`);
      await page.waitForTimeout(6000); // Wait for dynamic content
      
      const accessibilityScanResults = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
        .analyze();
      
      for (const violationType of pageInfo.violations) {
        const violations = accessibilityScanResults.violations.filter(
          violation => violation.id === violationType
        );
        
        if (violations.length > 0) {
          violations.forEach(violation => {
            console.log(`\n❌ ${violation.id.toUpperCase()}: ${violation.description}`);
            console.log(`   Impact: ${violation.impact} | Elements: ${violation.nodes.length}`);
            
            violation.nodes.forEach((node, index) => {
              console.log(`\n   ${index + 1}. Problem Element:`);
              console.log(`      Selector: ${node.target[0]}`);
              console.log(`      HTML: ${node.html.slice(0, 400)}${node.html.length > 400 ? '...' : ''}`);
              console.log(`      Issue: ${node.failureSummary}`);
              
              // Show context for nested-interactive
              if (violation.id === 'nested-interactive') {
                console.log(`      Context: This element contains interactive controls nested inside other interactive elements`);
              }
            });
          });
        } else {
          console.log(`✅ No ${violationType} violations found!`);
        }
      }
      
    } catch (error) {
      console.log(`❌ Error testing ${pageInfo.name}: ${error.message}`);
    }
  }
  
  await browser.close();
  console.log('\n✅ Detailed violation analysis complete!');
}

debugAllViolations().catch(console.error);