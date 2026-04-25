#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const glob = require('glob');

// Get all route files
const routeFiles = glob.sync('webapp/lambda/routes/*.js');

console.log(`Found ${routeFiles.length} route files to process\n`);

const stats = {
  filesProcessed: 0,
  patternsFixed: 0,
  errors: []
};

routeFiles.forEach(file => {
  try {
    let content = fs.readFileSync(file, 'utf8');
    const originalContent = content;

    // Only process if file doesn't already use helpers consistently
    const hasImports = content.includes('sendSuccess') || content.includes('sendError');
    if (!hasImports) {
      console.log(`⚠️ Skipping ${file} - missing sendSuccess/sendError imports`);
      return;
    }

    // PATTERN 1: Direct res.json({ data, success: true }) → sendSuccess
    // This is the most common pattern for endpoints returning data
    // BUT: Be careful not to convert pure documentation endpoints

    // PATTERN 2: res.status(CODE).json({ error, success: false }) → sendError(res, error, CODE)
    content = content.replace(
      /return\s+res\.status\((\d+)\)\.json\(\s*{\s*([^}]*?)\s*success:\s*false\s*([^}]*?)\s*}\s*\)/g,
      (match, code, before, after) => {
        const hasError = match.includes('error:');
        if (hasError) {
          return `return sendError(res, error, ${code})`;
        }
        return match;
      }
    );

    // PATTERN 3: res.json({ items, pagination, success: true }) → sendPaginated
    content = content.replace(
      /return\s+res\.json\(\s*{\s*items:\s*([^,]+),\s*pagination:\s*([^,]+),([^}]*?)success:\s*true[^}]*}\s*\)/g,
      'return sendPaginated(res, $1, $2)'
    );

    // PATTERN 4: Simple error responses
    content = content.replace(
      /return\s+res\.status\((\d+)\)\.json\(\s*{\s*error:\s*"([^"]+)",\s*success:\s*false\s*}\s*\)/g,
      'return sendError(res, "$2", $1)'
    );

    // Log if file was modified
    if (content !== originalContent) {
      fs.writeFileSync(file, content, 'utf8');
      const lines = originalContent.split('\n').length;
      console.log(`✅ ${file} - processed (${lines} lines)`);
      stats.filesProcessed++;
      stats.patternsFixed++;
    }

  } catch (error) {
    stats.errors.push(`${file}: ${error.message}`);
    console.error(`❌ Error processing ${file}: ${error.message}`);
  }
});

console.log(`\n=== SUMMARY ===`);
console.log(`Files processed: ${stats.filesProcessed}`);
console.log(`Patterns fixed: ${stats.patternsFixed}`);
if (stats.errors.length > 0) {
  console.log(`Errors: ${stats.errors.length}`);
  stats.errors.forEach(e => console.log(`  - ${e}`));
}
