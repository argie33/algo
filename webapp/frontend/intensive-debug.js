/**
 * Intensive Debug - Find timing-dependent violations with extensive waiting and interaction
 */

import { chromium } from 'playwright';
import AxeBuilder from '@axe-core/playwright';

async function intensiveDebug() {
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
    route.fulfill({ 
      json: { 
        success: true, 
        data: {
          // Mock data that might trigger components
          technical_data: Array(10).fill(null).map((_, i) => ({ symbol: `STOCK${i}`, value: Math.random() * 100 })),
          sentiment_data: Array(5).fill(null).map((_, i) => ({ source: `Source${i}`, sentiment: 0.5 })),
          earnings: Array(5).fill(null).map((_, i) => ({ symbol: `EARN${i}`, date: new Date().toISOString() }))
        }
      } 
    });
  });

  const problematicPages = [
    { name: 'Technical Analysis', url: 'technical-analysis' },
    { name: 'Sentiment Analysis', url: 'sentiment-analysis' },
    { name: 'Earnings Calendar', url: 'earnings-calendar' }
  ];
  
  for (const pageInfo of problematicPages) {
    console.log(`\n🔍 INTENSIVE ANALYSIS: ${pageInfo.name.toUpperCase()}`);
    console.log('='.repeat(70));
    
    try {
      await page.goto(`http://localhost:3000/${pageInfo.url}`);
      console.log('Page loaded, waiting for content...');
      
      // Extended wait and interaction sequence
      await page.waitForTimeout(5000);
      
      // Trigger any interactive elements that might create violations
      try {
        // Click any buttons or tabs
        const buttons = await page.locator('button, [role="button"], [role="tab"]').all();
        console.log(`Found ${buttons.length} interactive elements`);
        
        for (let i = 0; i < Math.min(buttons.length, 5); i++) {
          try {
            await buttons[i].click({ timeout: 1000 });
            await page.waitForTimeout(1000);
          } catch (e) {
            // Continue if click fails
          }
        }
        
        // Trigger any inputs
        const inputs = await page.locator('input, textarea, [contenteditable], [role="textbox"]').all();
        console.log(`Found ${inputs.length} input elements`);
        
        for (let i = 0; i < Math.min(inputs.length, 3); i++) {
          try {
            await inputs[i].focus({ timeout: 1000 });
            await page.waitForTimeout(500);
          } catch (e) {
            // Continue if focus fails
          }
        }
        
      } catch (interactionError) {
        console.log(`Interaction error (expected): ${interactionError.message}`);
      }
      
      // Scroll to trigger lazy loading
      await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
      await page.waitForTimeout(2000);
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.waitForTimeout(2000);
      
      // Multiple accessibility scans
      for (let scan = 1; scan <= 3; scan++) {
        console.log(`Running accessibility scan ${scan}/3...`);
        
        const accessibilityScanResults = await new AxeBuilder({ page })
          .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
          .analyze();
        
        const relevantViolations = accessibilityScanResults.violations.filter(
          violation => violation.id === 'aria-input-field-name' || violation.id === 'aria-progressbar-name'
        );
        
        if (relevantViolations.length > 0) {
          console.log(`\n❌ VIOLATIONS FOUND IN SCAN ${scan}:`);
          
          relevantViolations.forEach(violation => {
            console.log(`\n🚨 ${violation.id.toUpperCase()}: ${violation.description}`);
            console.log(`   Impact: ${violation.impact} | Elements: ${violation.nodes.length}`);
            
            violation.nodes.forEach((node, index) => {
              console.log(`\n   Element ${index + 1}:`);
              console.log(`      Selector: ${node.target[0]}`);
              console.log(`      HTML: ${node.html.slice(0, 300)}...`);
              console.log(`      Issue: ${node.failureSummary}`);
              
              // Get more context about the element
              if (violation.id === 'aria-input-field-name') {
                console.log(`      🔍 This input element lacks accessible labeling`);
              }
              if (violation.id === 'aria-progressbar-name') {
                console.log(`      🔍 This progress indicator lacks accessible labeling`);
              }
            });
          });
          
          // Found violations, can break out of scan loop
          break;
        } else {
          console.log(`   ✅ Scan ${scan}: No violations found`);
        }
        
        if (scan < 3) {
          await page.waitForTimeout(2000); // Wait between scans
        }
      }
      
    } catch (error) {
      console.log(`❌ Error testing ${pageInfo.name}: ${error.message}`);
    }
  }
  
  await browser.close();
  console.log('\n✅ Intensive debugging complete!');
}

intensiveDebug().catch(console.error);