#!/usr/bin/env node
/**
 * Fix API Mocking Issues Across All Tests
 * 
 * This script automatically fixes common API mocking issues in test files
 * by replacing incomplete mocks with our comprehensive API service mock.
 */

const fs = require('fs');
const path = require('path');
const glob = require('glob');

const TESTS_DIR = path.join(__dirname);
const API_MOCK_PATTERNS = [
  // Pattern 1: Simple vi.mock with basic methods
  /vi\.mock\(['"`]\.\.\/.*?\/services\/api['"`],\s*\(\)\s*=>\s*\(\{[^}]*get:\s*vi\.fn\(\)[^}]*\}\)\);?/gs,
  
  // Pattern 2: vi.mock with default export containing basic methods  
  /vi\.mock\(['"`]\.\.\/.*?\/services\/api['"`],\s*\(\)\s*=>\s*\(\{[\s\S]*?default:\s*\{[\s\S]*?get:\s*vi\.fn\(\)[\s\S]*?\}[\s\S]*?\}\)\);?/gs,
  
  // Pattern 3: async vi.mock with importOriginal but incomplete
  /vi\.mock\(['"`]\.\.\/.*?\/services\/api['"`],\s*async\s*\(importOriginal\)\s*=>\s*\{[\s\S]*?return\s*\{[\s\S]*?get:\s*vi\.fn\(\)[\s\S]*?\};?[\s\S]*?\}\);?/gs
];

const COMPREHENSIVE_MOCK = `// Mock the API service with comprehensive mock
vi.mock("../../../services/api", async (importOriginal) => {
  const { createApiServiceMock } = await import('../mocks/api-service-mock');
  return {
    default: createApiServiceMock(),
    ...createApiServiceMock()
  };
});`;

const COMPREHENSIVE_MOCK_2_LEVELS = `// Mock the API service with comprehensive mock
vi.mock("../../services/api", async (importOriginal) => {
  const { createApiServiceMock } = await import('../mocks/api-service-mock');
  return {
    default: createApiServiceMock(),
    ...createApiServiceMock()
  };
});`;

function fixApiMocks() {
  console.log('🔧 Fixing API mocks across all test files...\n');

  // Find all test files
  const testFiles = glob.sync('**/*.test.{js,jsx}', { 
    cwd: TESTS_DIR,
    absolute: true 
  });

  let fixedFiles = 0;
  let totalIssues = 0;

  testFiles.forEach(filePath => {
    const content = fs.readFileSync(filePath, 'utf8');
    let updatedContent = content;
    let fileIssues = 0;

    // Check if file has API mocking issues
    API_MOCK_PATTERNS.forEach(pattern => {
      const matches = content.match(pattern);
      if (matches) {
        fileIssues += matches.length;
        
        // Determine correct mock based on file path depth
        const relativePath = path.relative(TESTS_DIR, filePath);
        const depth = relativePath.split(path.sep).length - 1;
        const mockToUse = depth >= 3 ? COMPREHENSIVE_MOCK : COMPREHENSIVE_MOCK_2_LEVELS;
        
        // Replace the incomplete mock
        updatedContent = updatedContent.replace(pattern, mockToUse);
      }
    });

    // Write the fixed file
    if (fileIssues > 0) {
      fs.writeFileSync(filePath, updatedContent);
      console.log(`✅ Fixed ${fileIssues} mock issue(s) in: ${path.relative(TESTS_DIR, filePath)}`);
      fixedFiles++;
      totalIssues += fileIssues;
    }
  });

  console.log(`\n📊 Summary:`);
  console.log(`   Fixed files: ${fixedFiles}`);
  console.log(`   Total issues resolved: ${totalIssues}`);
  console.log(`   Scanned files: ${testFiles.length}`);

  if (fixedFiles > 0) {
    console.log(`\n✨ All API mocking issues have been resolved!`);
  } else {
    console.log(`\n✨ No API mocking issues found - tests are ready to run!`);
  }
}

// Run the fix
if (require.main === module) {
  fixApiMocks();
}

module.exports = { fixApiMocks };