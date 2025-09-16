/**
 * List Structure Debug Script - Find MUI List accessibility violations
 */

import { chromium } from 'playwright';
import AxeBuilder from '@axe-core/playwright';

async function debugListStructure() {
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

  const pages = [
    { name: 'Portfolio', url: 'portfolio' },
    { name: 'Market', url: 'market-overview' },
    { name: 'Settings', url: 'settings' }
  ];

  for (const pageInfo of pages) {
    console.log(`\n📋 ${pageInfo.name.toUpperCase()} PAGE LIST ANALYSIS:`);
    console.log('='.repeat(60));
    
    try {
      await page.goto(`http://localhost:3001/${pageInfo.url}`);
      await page.waitForTimeout(4000);
      
      const accessibilityScanResults = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
        .analyze();
      
      const listViolations = accessibilityScanResults.violations.filter(
        violation => violation.id === 'list' || violation.id === 'listitem'
      );
      
      if (listViolations.length > 0) {
        listViolations.forEach(violation => {
          console.log(`\n❌ ${violation.id}: ${violation.description}`);
          console.log(`   Elements: ${violation.nodes.length}`);
          
          violation.nodes.slice(0, 3).forEach((node, index) => {
            console.log(`\n   ${index + 1}. ${node.html.slice(0, 150)}...`);
            console.log(`      Selector: ${node.target[0]}`);
            console.log(`      Issue: ${node.failureSummary}`);
          });
        });
      } else {
        console.log('✅ No list structure violations found!');
      }
      
    } catch (error) {
      console.log(`❌ Error testing ${pageInfo.name}: ${error.message}`);
    }
  }
  
  await browser.close();
  console.log('\n✅ List structure analysis complete!');
}

debugListStructure().catch(console.error);