/**
 * Apply systematic fixes to test mocks
 * ISSUE #2: Database Mock Returns Undefined (90 tests)
 * ISSUE #3: Auth Middleware Bypass (70 tests)
 */

const fs = require('fs');
const path = require('path');

const glob = require('glob');

let fixedFiles = 0;
let errors = [];

function fixFile(filePath) {
  try {
    let content = fs.readFileSync(filePath, 'utf8');
    let modified = false;

    // Fix #3: Auth middleware - add authorization check
    const oldAuthPattern = `jest.mock("../../../middleware/auth", () => ({
  authenticateToken: jest.fn((req, res, next) => {
    req.user = { sub: "test-user-123" };
    next();
  }),`;

    const newAuthPattern = `jest.mock("../../../middleware/auth", () => ({
  authenticateToken: jest.fn((req, res, next) => {
    if (!req.headers.authorization) {
      return res.status(401).json({ error: "No authorization header" });
    }
    req.user = { sub: "test-user-123", role: "user" };
    next();
  }),`;

    if (content.includes(oldAuthPattern)) {
      content = content.replace(oldAuthPattern, newAuthPattern);
      modified = true;
    }

    // Fix #2: Database mock - add conditional implementation
    // Look for beforeEach with query.mockImplementation that doesn't handle COUNT
    const beforeEachRegex = /beforeEach\(\s*(?:async\s*)?\(\)\s*=>\s*\{[\s\S]*?query\.mockImplementation\(([\s\S]*?)\);[\s\S]*?\}\);/g;

    let match;
    while ((match = beforeEachRegex.exec(content)) !== null) {
      const implementation = match[1];

      // Check if it's missing COUNT/INSERT/UPDATE/DELETE handling
      if (!implementation.includes('SELECT COUNT') && !implementation.includes('COUNT(*)')) {
        // This needs fixing - but only if it's a simple () => Promise.resolve
        if (implementation.includes('() =>') && !implementation.includes('(sql') && !implementation.includes('(query')) {
          const newImpl = `(sql, params) => {
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
      // Default: return empty rows
      return Promise.resolve({ rows: [], rowCount: 0 });
    }`;

          content = content.replace(implementation, newImpl);
          modified = true;
        }
      }
    }

    // Fix mockResolvedValue without conditional
    if (content.includes('query.mockResolvedValue({ rows: []') &&
        !content.includes('query.mockImplementation((sql')) {

      // Find beforeEach blocks with mockResolvedValue
      const simpleResolveRegex = /beforeEach\([\s\S]*?query\.mockResolvedValue\(\s*\{\s*rows:\s*\[\][\s\S]*?\}\s*\);/g;

      if (simpleResolveRegex.test(content)) {
        content = content.replace(
          /query\.mockResolvedValue\(\s*\{\s*rows:\s*\[\][\s\S]*?\}\s*\);/g,
          `query.mockImplementation((sql, params) => {
      // Handle COUNT queries
      if (sql.includes("SELECT COUNT") || sql.includes("COUNT(*)")) {
        return Promise.resolve({ rows: [{ count: "0", total: "0" }], rowCount: 1 });
      }
      // Handle INSERT/UPDATE/DELETE queries
      if (sql.includes("INSERT") || sql.includes("UPDATE") || sql.includes("DELETE")) {
        return Promise.resolve({ rowCount: 0, rows: [] });
      }
      // Default: return empty rows
      return Promise.resolve({ rows: [], rowCount: 0 });
    });`
        );
        modified = true;
      }
    }

    if (modified) {
      fs.writeFileSync(filePath, content, 'utf8');
      fixedFiles++;
      console.log(`✅ Fixed: ${path.relative(process.cwd(), filePath)}`);
      return true;
    }
    return false;

  } catch (error) {
    errors.push({ file: filePath, error: error.message });
    console.error(`❌ Error: ${path.relative(process.cwd(), filePath)}: ${error.message}`);
    return false;
  }
}

// Main execution
console.log('🔍 Finding test files...\n');

// Find all test files
const testFiles = glob.sync('tests/**/*.test.js', { cwd: __dirname });

console.log(`Found ${testFiles.length} test files\n`);
console.log('🔧 Applying fixes...\n');

testFiles.forEach(file => {
  const fullPath = path.join(__dirname, file);
  fixFile(fullPath);
});

console.log('\n📊 Summary:');
console.log(`✅ Fixed: ${fixedFiles} files`);
console.log(`❌ Errors: ${errors.length} files`);

if (errors.length > 0) {
  console.log('\n❌ Error details:');
  errors.forEach(({ file, error }) => {
    console.log(`  ${path.relative(process.cwd(), file)}: ${error}`);
  });
}

process.exit(0);
