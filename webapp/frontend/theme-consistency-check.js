#!/usr/bin/env node

/**
 * Theme Consistency Validation Script
 * Compares styling patterns between HFT component and Dashboard to ensure consistency
 */

import fs from 'fs';

const components = [
  { name: 'Dashboard', path: './src/pages/Dashboard.jsx' },
  { name: 'HFTTrading', path: './src/pages/HFTTrading.jsx' },
  { name: 'LiveDataAdmin', path: './src/pages/LiveDataAdmin.jsx' }
];

console.log('🎨 Theme Consistency Validation');
console.log('=' .repeat(60));

// Common Material-UI patterns that should be consistent
const consistencyPatterns = {
  'Box padding': /sx={{.*p:\s*3.*}}/,
  'Card components': /Card>/,
  'Typography variants': /variant="h4"/,
  'Color usage': /color="textSecondary"/,
  'Material-UI imports': /@mui\/material/,
  'Grid layout': /Grid.*container/,
  'Button styling': /variant="contained"/
};

const results = {};

components.forEach(component => {
  try {
    const content = fs.readFileSync(component.path, 'utf8');
    results[component.name] = {};
    
    console.log(`\n📋 Analyzing ${component.name}:`);
    
    Object.entries(consistencyPatterns).forEach(([patternName, regex]) => {
      const matches = content.match(regex);
      results[component.name][patternName] = !!matches;
      
      const status = matches ? '✅' : '❌';
      console.log(`   ${status} ${patternName}: ${matches ? 'Found' : 'Missing'}`);
    });
    
  } catch (error) {
    console.log(`   ❌ Could not read ${component.name}: ${error.message}`);
    results[component.name] = null;
  }
});

console.log('\n📊 Theme Consistency Summary:');
console.log('=' .repeat(60));

// Compare consistency across components
Object.keys(consistencyPatterns).forEach(pattern => {
  const componentResults = components.map(comp => {
    const result = results[comp.name]?.[pattern];
    return { name: comp.name, hasPattern: result };
  }).filter(r => r.hasPattern !== undefined);
  
  const allHave = componentResults.every(r => r.hasPattern);
  const someHave = componentResults.some(r => r.hasPattern);
  
  let status = '🎯';
  if (allHave) {
    status = '✅ CONSISTENT';
  } else if (someHave) {
    status = '⚠️  PARTIAL';
  } else {
    status = '❌ MISSING';
  }
  
  console.log(`${status} ${pattern}:`);
  componentResults.forEach(comp => {
    const compStatus = comp.hasPattern ? '✓' : '✗';
    console.log(`   ${compStatus} ${comp.name}`);
  });
});

// Overall assessment
const hftResults = results['HFTTrading'];
const dashboardResults = results['Dashboard'];

if (hftResults && dashboardResults) {
  const hftPatterns = Object.values(hftResults).filter(Boolean).length;
  const dashboardPatterns = Object.values(dashboardResults).filter(Boolean).length;
  const totalPatterns = Object.keys(consistencyPatterns).length;
  
  console.log('\n🏆 Final Assessment:');
  console.log(`   HFTTrading patterns: ${hftPatterns}/${totalPatterns}`);
  console.log(`   Dashboard patterns: ${dashboardPatterns}/${totalPatterns}`);
  
  const consistency = Math.min(hftPatterns, dashboardPatterns) / totalPatterns;
  
  if (consistency >= 0.8) {
    console.log('   🎉 EXCELLENT: Components are highly consistent!');
  } else if (consistency >= 0.6) {
    console.log('   ✅ GOOD: Components are mostly consistent');
  } else {
    console.log('   ⚠️  NEEDS WORK: Components need more consistency');
  }
  
  console.log(`   Consistency Score: ${Math.round(consistency * 100)}%`);
}

console.log('\n' + '=' .repeat(60));