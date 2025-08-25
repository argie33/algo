/**
 * Input Field Debug Script - Find aria-input-field-name violations
 */

import { chromium } from 'playwright';
import AxeBuilder from '@axe-core/playwright';

async function debugInputFields() {
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

  console.log(`\n📝 PORTFOLIO PAGE INPUT FIELD ANALYSIS:`);
  console.log('='.repeat(60));
  
  try {
    await page.goto(`http://localhost:3001/portfolio`);
    await page.waitForTimeout(4000);
    
    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
      .analyze();
    
    const ariaInputFieldViolations = accessibilityScanResults.violations.filter(
      violation => violation.id === 'aria-input-field-name'
    );
    
    if (ariaInputFieldViolations.length > 0) {
      console.log(`❌ Found ${ariaInputFieldViolations.length} aria-input-field-name violations:`);
      
      for (const violation of ariaInputFieldViolations) {
        console.log(`\n📋 Violation: ${violation.description}`);
        
        if (violation.nodes && violation.nodes.length > 0) {
          console.log(`\n🎯 FAILING ELEMENTS (${violation.nodes.length} total):`);
          
          for (let index = 0; index < Math.min(violation.nodes.length, 10); index++) {
            const node = violation.nodes[index];
            console.log(`\n${index + 1}. Element HTML:`);
            console.log(`   ${node.html.slice(0, 300)}${node.html.length > 300 ? '...' : ''}`);
            
            if (node.target && node.target.length > 0) {
              console.log(`   CSS Selector: ${node.target[0]}`);
            }
            
            if (node.failureSummary) {
              console.log(`   Issue: ${node.failureSummary}`);
            }
            
            if (node.impact) {
              console.log(`   Impact: ${node.impact}`);
            }
          }
        }
      }
    } else {
      console.log(`✅ No aria-input-field-name violations found!`);
    }
    
  } catch (error) {
    console.log(`❌ Error: ${error.message}`);
  }
  
  await browser.close();
  console.log('\n✅ Input field debug complete!');
}

debugInputFields().catch(console.error);