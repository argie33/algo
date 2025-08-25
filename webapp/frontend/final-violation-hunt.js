/**
 * Final Violation Hunt - Target timing-dependent violations with comprehensive loading waits
 */

import { chromium } from 'playwright';
import AxeBuilder from '@axe-core/playwright';

async function finalViolationHunt() {
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
          // Rich mock data to trigger all components
          technical_indicators: Array(20).fill(null).map((_, i) => ({ 
            symbol: `STOCK${i}`, 
            rsi: Math.random() * 100,
            sma: Math.random() * 200,
            ema: Math.random() * 200
          })),
          sentiment_analysis: {
            sources: Array(10).fill(null).map((_, i) => ({
              source: `Source ${i}`,
              sentiment: Math.random(),
              confidence: Math.random()
            })),
            loading: false,
            progress: Math.random()
          },
          earnings_calendar: Array(15).fill(null).map((_, i) => ({
            symbol: `EARN${i}`,
            date: new Date(Date.now() + i * 86400000).toISOString(),
            eps_estimate: Math.random() * 5
          }))
        }
      } 
    });
  });

  const problematicPages = [
    { name: 'Technical Analysis', url: 'technical-analysis' },
    { name: 'Sentiment Analysis', url: 'sentiment-analysis' },
    { name: 'Earnings Calendar', url: 'earnings-calendar' }
  ];

  console.log('🎯 FINAL VIOLATION HUNT - COMPREHENSIVE LOADING STRATEGY');
  console.log('='.repeat(80));

  for (const pageInfo of problematicPages) {
    console.log(`\n🔍 HUNTING: ${pageInfo.name.toUpperCase()}`);
    console.log('-'.repeat(50));
    
    try {
      await page.goto(`http://localhost:3000/${pageInfo.url}`);
      console.log('✓ Page loaded, beginning comprehensive wait strategy...');
      
      // Strategy 1: Wait for network idle
      await page.waitForLoadState('networkidle');
      console.log('✓ Network idle reached');
      
      // Strategy 2: Wait for common loading indicators to disappear
      try {
        await page.waitForSelector('.MuiCircularProgress-root', { state: 'detached', timeout: 5000 });
        console.log('✓ Loading spinners disappeared');
      } catch (e) {
        console.log('- No loading spinners found');
      }
      
      // Strategy 3: Wait for potential async components
      await page.waitForTimeout(8000);
      console.log('✓ Extended wait completed');
      
      // Strategy 4: Trigger all possible interactions
      try {
        // Focus any text inputs to trigger validation states
        const textInputs = await page.locator('input[type="text"], textarea, [contenteditable="true"], [role="textbox"]').all();
        console.log(`✓ Found ${textInputs.length} text input elements`);
        
        for (let i = 0; i < textInputs.length; i++) {
          try {
            await textInputs[i].focus({ timeout: 1000 });
            await textInputs[i].fill('test'); // Trigger any validation
            await page.waitForTimeout(500);
          } catch (e) {
            // Continue on error
          }
        }
        
        // Look for progress bars and charts that might be loading
        const progressBars = await page.locator('[role="progressbar"], .progress, .MuiLinearProgress-root').all();
        console.log(`✓ Found ${progressBars.length} progress elements`);
        
      } catch (interactionError) {
        console.log(`- Interaction phase error: ${interactionError.message}`);
      }
      
      // Strategy 5: Final wait for any last-second renders
      await page.waitForTimeout(3000);
      console.log('✓ Final stabilization wait completed');
      
      // Now run accessibility scan
      console.log('🔬 Running accessibility scan...');
      const accessibilityScanResults = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
        .analyze();
      
      const relevantViolations = accessibilityScanResults.violations.filter(
        violation => violation.id === 'aria-input-field-name' || violation.id === 'aria-progressbar-name'
      );
      
      if (relevantViolations.length > 0) {
        console.log(`\n🎯 FOUND ${relevantViolations.length} VIOLATIONS!`);
        
        relevantViolations.forEach(violation => {
          console.log(`\n❌ ${violation.id.toUpperCase()}: ${violation.description}`);
          console.log(`   Impact: ${violation.impact} | Elements: ${violation.nodes.length}`);
          
          violation.nodes.forEach((node, index) => {
            console.log(`\n   🎯 Element ${index + 1} - READY FOR FIXING:`);
            console.log(`      Selector: ${node.target[0]}`);
            console.log(`      HTML: ${node.html.slice(0, 400)}${node.html.length > 400 ? '...' : ''}`);
            console.log(`      Issue: ${node.failureSummary}`);
            
            // Specific fix recommendations based on element type
            if (violation.id === 'aria-input-field-name') {
              if (node.html.includes('contenteditable') || node.html.includes('role="textbox"')) {
                console.log(`      🔧 CODE FIX NEEDED: Add aria-label="[description]" to this element`);
                console.log(`      🔧 EXAMPLE: <div ... aria-label="Enter your analysis text">`);
              } else if (node.html.includes('<input')) {
                console.log(`      🔧 CODE FIX NEEDED: Add aria-label or associated <label>`);
                console.log(`      🔧 EXAMPLE: <input ... aria-label="Search field" />`);
              }
            } else if (violation.id === 'aria-progressbar-name') {
              console.log(`      🔧 CODE FIX NEEDED: Add aria-label="[progress description]" to progress element`);
              console.log(`      🔧 EXAMPLE: <div role="progressbar" aria-label="Loading progress" ...>`);
            }
          });
        });
      } else {
        console.log('✅ No violations found in comprehensive scan!');
      }
      
    } catch (error) {
      console.log(`❌ Error during comprehensive analysis of ${pageInfo.name}: ${error.message}`);
    }
  }
  
  await browser.close();
  console.log('\n✅ Final violation hunt complete!');
}

finalViolationHunt().catch(console.error);