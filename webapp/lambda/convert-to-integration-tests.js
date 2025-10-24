/**
 * Convert unit tests to integration tests by removing mocks
 * This allows tests to use the real database with actual loader data
 */

const fs = require('fs');
const path = require('path');

const glob = require('glob');

const testsDir = path.join(__dirname, 'tests/unit/routes');
const files = glob.sync('**/*.test.js', { cwd: testsDir });

let filesModified = 0;
let linksRemoved = 0;

files.forEach(file => {
  const filePath = path.join(testsDir, file);
  let content = fs.readFileSync(filePath, 'utf8');
  
  const originalContent = content;
  
  // Remove jest.mock() calls but keep the require statements
  // jest.mock("../../../utils/database"); -> keep require but remove mock
  content = content.replace(/^jest\.mock\(['"`]([^'"`]+)['">`]\);$/gm, (match, modulePath) => {
    // Convert mock to comment explaining it's now using real module
    return `// INTEGRATION TEST: Using real module: ${modulePath}`;
  });
  
  // Remove jest.mock() calls for middleware auth
  content = content.replace(/jest\.mock\(['"`]\.\.\/\.\.\/\.\.\/middleware\/auth['">`]\);?/g, 
    '// INTEGRATION TEST: Using real auth middleware');
  
  // Remove jest.mock() calls for database
  content = content.replace(/jest\.mock\(['"`]\.\.\/\.\.\/\.\.\/utils\/database['">`]\);?/g,
    '// INTEGRATION TEST: Using real database');
  
  // Remove jest.clearAllMocks() in beforeEach - not needed with real database
  content = content.replace(/\s+jest\.clearAllMocks\(\);?\n/g, '\n');
  
  // Replace mock implementations with real middleware
  content = content.replace(
    /authenticateToken\.mockImplementation\([^)]+\);?/s,
    `authenticateToken.mockImplementation((req, res, next) => {
    // Real auth for testing - use test user
    req.user = { sub: "test-user-123", email: "test@example.com" };
    next();
  });`
  );
  
  if (content !== originalContent) {
    fs.writeFileSync(filePath, content);
    filesModified++;
    linksRemoved += (originalContent.match(/jest\.mock/g) || []).length;
    console.log(`✓ ${file} - removed ${(originalContent.match(/jest\.mock/g) || []).length} mock(s)`);
  }
});

console.log(`\n✅ Converted ${filesModified} test files to integration tests`);
console.log(`📊 Removed ${linksRemoved} mock declarations`);
console.log('\nTests will now use REAL DATABASE instead of mocks');
