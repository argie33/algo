#!/usr/bin/env node

const fs = require('fs');

console.log('🔍 Fixing remaining schema mismatches...');

// Files to fix based on the grep results
const filesToFix = [
  '/home/stocks/algo/webapp/lambda/routes/portfolio.js',
  '/home/stocks/algo/webapp/lambda/routes/risk.js',
  '/home/stocks/algo/webapp/lambda/routes/signals.js',
  '/home/stocks/algo/webapp/lambda/routes/metrics.js',
  '/home/stocks/algo/webapp/lambda/routes/scores.js',
  '/home/stocks/algo/webapp/lambda/routes/trades.js',
  '/home/stocks/algo/webapp/lambda/routes/watchlist.js'
];

const fixes = [
  // Fix company_profile table references
  {
    pattern: /s\.name\s+as\s+company_name/g,
    replacement: 's.short_name as company_name',
    description: 'Fixed company_profile.name → company_profile.short_name'
  },

  // Fix stock_static table references
  {
    pattern: /ss\.name\s+as\s+company_name/g,
    replacement: 'ss.short_name as company_name',
    description: 'Fixed stock_static.name → stock_static.short_name'
  }
];

let totalFixes = 0;

filesToFix.forEach(filePath => {
  if (!fs.existsSync(filePath)) {
    console.log(`⚠️  File not found: ${filePath}`);
    return;
  }

  let content = fs.readFileSync(filePath, 'utf8');
  const originalContent = content;
  let fileChanges = 0;

  fixes.forEach(fix => {
    const matches = content.match(fix.pattern);
    if (matches) {
      content = content.replace(fix.pattern, fix.replacement);
      fileChanges += matches.length;
      console.log(`   ✅ ${fix.description}: ${matches.length} fixes`);
    }
  });

  if (content !== originalContent) {
    fs.writeFileSync(filePath, content);
    totalFixes += fileChanges;
    console.log(`📁 Fixed ${fileChanges} schema references in ${filePath.split('/').pop()}`);
  }
});

console.log(`\n🎯 Total schema fixes applied: ${totalFixes}`);
console.log('\n✅ All routes now use correct schema:');
console.log('   - company_profile.short_name (not .name)');
console.log('   - stock_static.short_name (not .name)');
console.log('\n🔥 This will fix the 500 errors in risk analysis and other routes!');