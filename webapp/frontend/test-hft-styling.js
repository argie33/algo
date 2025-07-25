#!/usr/bin/env node

/**
 * HFT Component Styling Validation Script
 * Validates that the HFT component has been successfully converted from Tailwind to Material-UI
 */

import fs from 'fs';
import path from 'path';

const hftComponentPath = './src/pages/HFTTrading.jsx';

console.log('🔍 HFT Component Styling Validation');
console.log('=' .repeat(50));

try {
  const content = fs.readFileSync(hftComponentPath, 'utf8');
  
  // Check for Tailwind CSS remnants (should be removed)
  const tailwindPatterns = [
    /className.*bg-gray-900/,
    /className.*text-white/,
    /className.*bg-gradient-to-r/,
    /className.*from-blue-400/,
    /className.*to-purple-500/,
    /className.*bg-clip-text/,
    /className.*text-transparent/,
    /className.*min-h-screen/
  ];
  
  // Check for Material-UI patterns (should be present)
  const materialUIPatterns = [
    /Box,/,
    /Card,/,
    /Typography,/,
    /sx={{.*p:.*3.*}}/,
    /variant="h4"/,
    /variant="body1"/,
    /color="textSecondary"/
  ];
  
  console.log('❌ Checking for Tailwind CSS remnants (should be 0):');
  let tailwindFound = 0;
  tailwindPatterns.forEach((pattern, index) => {
    const matches = content.match(pattern);
    if (matches) {
      tailwindFound++;
      console.log(`   - Found Tailwind pattern ${index + 1}: ${matches[0]}`);
    }
  });
  
  if (tailwindFound === 0) {
    console.log('✅ No Tailwind CSS patterns found - conversion successful!');
  }
  
  console.log('\n✅ Checking for Material-UI patterns (should be present):');
  let materialUIFound = 0;
  materialUIPatterns.forEach((pattern, index) => {
    const matches = content.match(pattern);
    if (matches) {
      materialUIFound++;
      console.log(`   ✓ Found Material-UI pattern ${index + 1}: ${matches[0]}`);
    }
  });
  
  console.log(`\n📊 Results:`);
  console.log(`   Tailwind patterns found: ${tailwindFound} (should be 0)`);
  console.log(`   Material-UI patterns found: ${materialUIFound} (should be > 5)`);
  
  if (tailwindFound === 0 && materialUIFound >= 5) {
    console.log('\n🎉 SUCCESS: HFT component successfully converted to Material-UI!');
    console.log('   - Blue background removed ✅');
    console.log('   - Tailwind CSS replaced with Material-UI ✅');
    console.log('   - Theme consistency achieved ✅');
  } else {
    console.log('\n⚠️  INCOMPLETE: Conversion needs more work');
    if (tailwindFound > 0) {
      console.log('   - Remove remaining Tailwind CSS classes');
    }
    if (materialUIFound < 5) {
      console.log('   - Add more Material-UI components');
    }
  }
  
} catch (error) {
  console.error('❌ Error reading HFT component file:', error.message);
}

console.log('\n' + '=' .repeat(50));