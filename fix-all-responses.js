#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const glob = require('glob');

// Get all route files
const routeFiles = glob.sync('webapp/lambda/routes/*.js');

console.log(`\n🔧 MASS API RESPONSE FIXER\n`);
console.log(`Found ${routeFiles.length} route files to process\n`);

let totalFixed = 0;
const results = [];

routeFiles.forEach(filePath => {
  try {
    let content = fs.readFileSync(filePath, 'utf8');
    const original = content;
    const fileName = path.basename(filePath);

    // PATTERN 1: res.json({ items: x, pagination: y, success: true })
    // → Should be sendPaginated with proper format
    content = content.replace(
      /return\s+res\.json\(\s*{\s*items:\s*([^,}]+),\s*pagination:\s*([^,}]+),([^}]*?)success:\s*true([^}]*?)}\s*\)/g,
      'return sendPaginated(res, $1, $2)'
    );

    // PATTERN 2: res.json({ success: true, data: x, pagination: y })
    // → Should be sendPaginated
    content = content.replace(
      /return\s+res\.json\(\s*{\s*success:\s*true,\s*data:\s*([^,}]+),\s*pagination:\s*([^,}]+)([^}]*?)}\s*\)/g,
      'return sendPaginated(res, $1, $2)'
    );

    // PATTERN 3: res.json({ data: x, success: true, ... })
    // → Should be sendSuccess
    content = content.replace(
      /return\s+res\.json\(\s*{\s*data:\s*([^,}]+),\s*success:\s*true,([^}]*?)}\s*\)/g,
      'return sendSuccess(res, $1)'
    );

    // PATTERN 4: res.json({ success: true, data: {...}, ... })
    // → Should be sendSuccess
    content = content.replace(
      /return\s+res\.json\(\s*{\s*success:\s*true,\s*data:\s*({[^}]*}),([^}]*?)}\s*\)/g,
      'return sendSuccess(res, $1)'
    );

    // PATTERN 5: res.status(CODE).json({ error: "msg", success: false })
    // → Should be sendError
    content = content.replace(
      /return\s+res\.status\((\d+)\)\.json\(\s*{\s*error:\s*"([^"]+)",\s*success:\s*false\s*}\s*\)/g,
      'return sendError(res, "$2", $1)'
    );

    // PATTERN 6: res.json({ success: true, items: x })
    // → Should be sendSuccess
    content = content.replace(
      /return\s+res\.json\(\s*{\s*success:\s*true,\s*items:\s*([^,}]+),([^}]*?)}\s*\)/g,
      'return sendSuccess(res, $1)'
    );

    // PATTERN 7: res.json({ success: true })
    // → Should be sendSuccess with empty data
    content = content.replace(
      /return\s+res\.json\(\s*{\s*success:\s*true\s*}\s*\)/g,
      'return sendSuccess(res, {})'
    );

    if (content !== original) {
      fs.writeFileSync(filePath, content, 'utf8');
      const changesCount = original.split('res.json(').length - content.split('res.json(').length;
      console.log(`✅ ${fileName.padEnd(20)} - Fixed ${changesCount} responses`);
      totalFixed += changesCount;
      results.push({ file: fileName, fixed: changesCount });
    }

  } catch (error) {
    console.error(`❌ Error processing ${path.basename(filePath)}: ${error.message}`);
  }
});

console.log(`\n${'='.repeat(50)}`);
console.log(`✅ TOTAL RESPONSES FIXED: ${totalFixed}`);
console.log(`📁 FILES PROCESSED: ${results.length}`);
console.log(`${'='.repeat(50)}\n`);

results.forEach(r => {
  console.log(`  ${r.file.padEnd(25)} ${r.fixed} fixed`);
});

console.log(`\n⚠️  Note: Verify critical endpoints still work correctly`);
console.log(`   Run: npm test or manual testing of key pages\n`);
