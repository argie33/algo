/**
 * Systematic Test Mock Fixer
 * Fixes ISSUE #2 (Database Mock Returns Undefined) and ISSUE #3 (Auth Middleware Bypass)
 * across all test files
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// Smart query mock implementation that handles different SQL types
const SMART_QUERY_MOCK = `    query.mockImplementation((sql, params) => {
      // Handle COUNT queries
      if (sql.includes("SELECT COUNT") || sql.includes("COUNT(*)")) {
        return Promise.resolve({ rows: [{ count: "0", total: "0" }], rowCount: 1 });
      }
      // Handle INSERT/UPDATE/DELETE queries
      if (sql.includes("INSERT") || sql.includes("UPDATE") || sql.includes("DELETE")) {
        return Promise.resolve({ rowCount: 0, rows: [] });
      }
      // Handle information_schema queries
      if (sql.includes("information_schema.tables")) {
        return Promise.resolve({ rows: [{ exists: true }] });
      }
      // Default: return empty result set
      return Promise.resolve({ rows: [], rowCount: 0 });
    });`;

// Auth mock that requires authorization header
const SECURE_AUTH_MOCK = `jest.mock("../../../middleware/auth", () => ({
  authenticateToken: jest.fn((req, res, next) => {
    if (!req.headers.authorization) {
      return res.status(401).json({ error: "No authorization header" });
    }
    req.user = { sub: "test-user-123", role: "user" };
    next();
  }),
  authorizeAdmin: jest.fn((req, res, next) => {
    if (!req.user || req.user.role !== "admin") {
      return res.status(403).json({ error: "Admin access required" });
    }
    next();
  }),
  checkApiKey: jest.fn((req, res, next) => next()),
}));`;

let fixedFiles = 0;
let skippedFiles = 0;
let errors = [];

/**
 * Fix database mock in a test file
 */
function fixDatabaseMock(filePath, content) {
  let modified = false;

  // Pattern 1: Simple mockResolvedValue without conditional logic
  const simplePattern = /query\.mockResolvedValue\(\s*\{\s*rows:\s*\[\],?\s*(?:rowCount:\s*0)?\s*\}\s*\)/g;

  if (simplePattern.test(content) && !content.includes('query.mockImplementation')) {
    // Replace in beforeEach blocks
    content = content.replace(
      /(beforeEach\(\s*(?:async\s*)?\(\)\s*=>\s*\{[\s\S]*?)query\.mockResolvedValue\([^)]*\);?/,
      `$1${SMART_QUERY_MOCK}`
    );
    modified = true;
  }

  return { content, modified };
}

/**
 * Fix auth middleware mock in a test file
 */
function fixAuthMock(filePath, content) {
  let modified = false;

  // Pattern: Auth mock without authorization check
  const insecureAuthPattern = /jest\.mock\(["']\.\.\/\.\.\/\.\.\/middleware\/auth["'],\s*\(\)\s*=>\s*\(\{[\s\S]*?authenticateToken:\s*jest\.fn\(\(req,\s*res,\s*next\)\s*=>\s*\{[^}]*req\.user\s*=\s*\{[^}]*\};?[^}]*next\(\);?\s*\}\)/;

  if (insecureAuthPattern.test(content) && !content.includes('if (!req.headers.authorization)')) {
    content = content.replace(
      /jest\.mock\(["']\.\.\/\.\.\/\.\.\/middleware\/auth["'],\s*\(\)\s*=>\s*\(\{[\s\S]*?\}\)\);/,
      SECURE_AUTH_MOCK
    );
    modified = true;
  }

  return { content, modified };
}

/**
 * Process a single test file
 */
function processFile(filePath) {
  try {
    let content = fs.readFileSync(filePath, 'utf8');
    let fileModified = false;

    // Fix database mock
    const dbResult = fixDatabaseMock(filePath, content);
    if (dbResult.modified) {
      content = dbResult.content;
      fileModified = true;
    }

    // Fix auth mock
    const authResult = fixAuthMock(filePath, content);
    if (authResult.modified) {
      content = authResult.content;
      fileModified = true;
    }

    // Write back if modified
    if (fileModified) {
      fs.writeFileSync(filePath, content, 'utf8');
      fixedFiles++;
      console.log(`✅ Fixed: ${path.relative(process.cwd(), filePath)}`);
      return true;
    } else {
      skippedFiles++;
      return false;
    }
  } catch (error) {
    errors.push({ file: filePath, error: error.message });
    console.error(`❌ Error processing ${filePath}: ${error.message}`);
    return false;
  }
}

/**
 * Find all test files recursively
 */
function findTestFiles(dir, fileList = []) {
  const files = fs.readdirSync(dir);

  files.forEach(file => {
    const filePath = path.join(dir, file);
    const stat = fs.statSync(filePath);

    if (stat.isDirectory()) {
      findTestFiles(filePath, fileList);
    } else if (file.endsWith('.test.js') || file.endsWith('.integration.test.js')) {
      fileList.push(filePath);
    }
  });

  return fileList;
}

// Main execution
console.log('🔍 Scanning for test files...\n');

const testsDir = path.join(__dirname, 'tests');
const testFiles = findTestFiles(testsDir);

console.log(`Found ${testFiles.length} test files\n`);
console.log('🔧 Applying fixes...\n');

testFiles.forEach(processFile);

console.log('\n📊 Summary:');
console.log(`✅ Fixed: ${fixedFiles} files`);
console.log(`⏭️  Skipped: ${skippedFiles} files (no changes needed)`);
console.log(`❌ Errors: ${errors.length} files`);

if (errors.length > 0) {
  console.log('\n❌ Error details:');
  errors.forEach(({ file, error }) => {
    console.log(`  ${path.relative(process.cwd(), file)}: ${error}`);
  });
}

console.log('\n✅ Mock fixing complete!');
process.exit(errors.length > 0 ? 1 : 0);
