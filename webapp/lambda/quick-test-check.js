#!/usr/bin/env node
const fs = require('fs');
const path = require('path');

console.log('🔍 Quick Test Analysis - Finding remaining issues...\n');

// Find all test files
const testDir = 'tests/unit/routes';
const testFiles = fs.readdirSync(testDir).filter(f => f.endsWith('.test.js'));

console.log(`Found ${testFiles.length} test files to analyze:\n`);

// Read each test file and identify potential issues
testFiles.slice(0, 10).forEach(file => {
  const filePath = path.join(testDir, file);
  const content = fs.readFileSync(filePath, 'utf8');

  console.log(`📋 ${file}:`);

  // Count test cases
  const testCases = (content.match(/test\(/g) || []).length;
  console.log(`  - ${testCases} test cases`);

  // Check for common issues
  const issues = [];

  if (content.includes('toHaveProperty') && !content.includes('expect.extend')) {
    issues.push('Missing custom matchers setup');
  }

  if (content.includes('daily_pnl_percent')) {
    issues.push('References missing database column');
  }

  if (content.includes('expect(response.body.data).toHaveProperty') && !content.includes('|| response.body')) {
    issues.push('Rigid property expectations');
  }

  if (content.includes('.toBeOneOf') && !content.includes('expect.extend')) {
    issues.push('Custom matcher toBeOneOf not defined');
  }

  if (issues.length > 0) {
    console.log(`  ⚠️  Potential issues: ${issues.join(', ')}`);
  } else {
    console.log(`  ✅ No obvious issues detected`);
  }

  console.log('');
});

console.log('\n📊 Summary:');
console.log(`- Analyzed first 10 test files`);
console.log(`- Focus on files with potential issues for targeted fixes`);
console.log(`- Main issue types: property expectations, custom matchers, database columns`);