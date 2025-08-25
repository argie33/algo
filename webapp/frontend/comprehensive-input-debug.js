/**
 * Comprehensive Input Field Debug Script - Find ALL accessibility violations
 */

import { chromium } from 'playwright';
import AxeBuilder from '@axe-core/playwright';

async function debugAllInputFields() {
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

  console.log(`\n🔍 COMPREHENSIVE PORTFOLIO INPUT FIELD ANALYSIS:`);
  console.log('='.repeat(70));
  
  try {
    await page.goto(`http://localhost:3001/portfolio`);
    await page.waitForTimeout(5000);
    
    // Run full accessibility scan
    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
      .analyze();
    
    // Check ALL violations by type
    const allViolations = accessibilityScanResults.violations;
    console.log(`\n📊 TOTAL VIOLATIONS FOUND: ${allViolations.length}`);
    
    allViolations.forEach((violation, index) => {
      console.log(`\n${index + 1}. ${violation.id}: ${violation.description}`);
      console.log(`   Impact: ${violation.impact}`);
      console.log(`   Elements affected: ${violation.nodes.length}`);
      
      if (violation.nodes.length > 0) {
        violation.nodes.slice(0, 3).forEach((node, nodeIndex) => {
          console.log(`   ${nodeIndex + 1}. ${node.html.slice(0, 200)}...`);
          if (node.target && node.target.length > 0) {
            console.log(`      CSS Selector: ${node.target[0]}`);
          }
          if (node.failureSummary) {
            console.log(`      Issue: ${node.failureSummary}`);
          }
        });
      }
    });
    
  } catch (error) {
    console.log(`❌ Error: ${error.message}`);
  }
  
  await browser.close();
  console.log('\n✅ Comprehensive analysis complete!');
}

debugAllInputFields().catch(console.error);