#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// Find all test files with permissive patterns
console.log('🔍 Finding permissive test patterns...');

// Get all files that contain the problematic patterns
const testFiles = [];
try {
  const grepOutput = execSync(`grep -r "\\[200.*404\\]\\|\\[200.*500\\]" webapp/lambda/tests/ --include="*.js" -l`, { encoding: 'utf8' });
  testFiles.push(...grepOutput.trim().split('\n').filter(f => f.trim()));
} catch (e) {
  // No matches found, that's okay
}

console.log(`Found ${testFiles.length} files with permissive tests`);

const fixes = {
  // Basic 200,404 patterns - should only accept 200
  'expect([200, 404]).toContain(response.status);': 'expect(response.status).toBe(200);',
  'expect([200, 404, 500]).toContain(response.status);': 'expect(response.status).toBe(200);',
  'expect([200, 500]).toContain(response.status);': 'expect(response.status).toBe(200);',

  // More complex patterns
  'expect([200, 403, 404]).toContain(response.status);': 'expect(response.status).toBe(200);',

  // Handle specific error scenarios that legitimately expect errors
  // Rate limiting tests should still expect rate limit responses
  'expect([200, 500].includes(recoveryResponse.status)).toBe(true);': 'expect([200, 429, 503].includes(recoveryResponse.status)).toBe(true);',
};

// Files that should be excluded from blanket fixes (legitimate error testing)
const excludeFromBlanketFix = [
  'rate-limiting.integration.test.js',
  'timeout-handling.integration.test.js',
  '4xx-error-scenarios.integration.test.js',
  'malformed-request.integration.test.js'
];

let totalFixes = 0;

testFiles.forEach(filePath => {
  if (!fs.existsSync(filePath)) return;

  const fileName = path.basename(filePath);
  const shouldExclude = excludeFromBlanketFix.some(exclude => fileName.includes(exclude));

  let content = fs.readFileSync(filePath, 'utf8');
  const originalContent = content;

  // Apply fixes based on file type
  for (const [pattern, replacement] of Object.entries(fixes)) {
    if (shouldExclude && pattern.includes('[200, 404]')) {
      // For error testing files, be more selective
      continue;
    }

    const regex = new RegExp(pattern.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g');
    content = content.replace(regex, replacement);
  }

  // Special handling for legitimate error tests
  if (shouldExclude) {
    console.log(`⚠️  Skipping blanket fix for error test file: ${fileName}`);
  } else if (content !== originalContent) {
    fs.writeFileSync(filePath, content);
    const lineChanges = (originalContent.match(/expect\(\[200.*\]\)\.toContain/g) || []).length;
    totalFixes += lineChanges;
    console.log(`✅ Fixed ${lineChanges} permissive assertions in ${fileName}`);
  }
});

console.log(`\n🎯 Total fixes applied: ${totalFixes}`);
console.log('\n📋 Summary of changes:');
console.log('- Changed expect([200, 404]).toContain(response.status) → expect(response.status).toBe(200)');
console.log('- Changed expect([200, 404, 500]).toContain(response.status) → expect(response.status).toBe(200)');
console.log('- Preserved legitimate error testing patterns in error-specific test files');

console.log('\n🧪 These tests will now properly catch:');
console.log('- 500 errors from schema mismatches');
console.log('- 400 errors from malformed requests');
console.log('- Any unexpected error responses');