/**
 * Automated test conversion script
 * Converts all integration route tests from broken database init pattern to proper mocks
 */

const fs = require('fs');
const path = require('path');

const testDir = path.join(__dirname, 'tests/integration/routes');
const files = fs.readdirSync(testDir)
  .filter(f => f.endsWith('.integration.test.js'))
  .filter(f => fs.readFileSync(path.join(testDir, f), 'utf8').includes('initializeDatabase'));

console.log(`🔧 Found ${files.length} broken integration tests to fix\n`);

files.forEach((file, idx) => {
  const filePath = path.join(testDir, file);
  let content = fs.readFileSync(filePath, 'utf8');

  // Skip if already fixed
  if (!content.includes('initializeDatabase')) {
    console.log(`✓ ${idx + 1}/${files.length} - ${file} (already fixed)`);
    return;
  }

  // Extract router name from filename (e.g., sectors.integration.test.js → sectorRouter)
  const routeName = file.replace('.integration.test.js', '');
  const routerVar = routeName.charAt(0).toUpperCase() + routeName.slice(1) + 'Router';
  const routerVarCamel = routeName.replace(/([A-Z])/g, '-$1').toLowerCase().replace(/-/g, '') + 'Router';

  // Generate mock setup
  const mockSetup = `jest.mock("../../../utils/database", () => ({ query: jest.fn() }));
jest.mock("../../../middleware/auth", () => ({
  authenticateToken: jest.fn((req, res, next) => {
    req.user = { sub: "test-user-123" };
    next();
  }),
}));

const { query } = require("../../../utils/database");
const express = require("express");
let app;
`;

  // Fix pattern 1: Remove initializeDatabase calls
  content = content.replace(
    /const\s+{\s*initializeDatabase.*?}\s*=\s*require\([^)]+\);\n/gs,
    ''
  );
  content = content.replace(
    /const\s+{\s*initializeDatabase.*?\}\s*=\s*require\([^)]+\);\n/gs,
    ''
  );

  // Fix pattern 2: Replace beforeAll with proper setup
  content = content.replace(
    /beforeAll\s*\(\s*async\s*\(\s*\)\s*=>\s*{\s*await\s+initializeDatabase\s*\(\s*\)\s*;[\s\S]*?}\s*\)\s*;/,
    `beforeAll(() => {
  app = express();
  app.use(express.json());
  app.use("/api/${routeName}", require("../../../routes/${routeName}"));
});`
  );

  // Fix pattern 3: Add jest.clearAllMocks() in beforeEach if not present
  if (!content.includes('jest.clearAllMocks()')) {
    content = content.replace(
      /beforeEach\s*\(\s*\(\s*\)\s*=>\s*{\n/,
      `beforeEach(() => {
  jest.clearAllMocks();
`
    );

    // If no beforeEach exists, create one
    if (!content.includes('beforeEach')) {
      content = content.replace(
        /beforeAll\s*\(\s*\(\s*\)\s*=>\s*{[\s\S]*?}\s*\)\s*;/,
        (match) => match + `

beforeEach(() => {
  jest.clearAllMocks();
  query.mockImplementation((sql) => {
    return Promise.resolve({ rows: [] });
  });
});`
      );
    }
  }

  // Add mocks at top if not present
  if (!content.includes('jest.mock("../../../utils/database"')) {
    const requiresIndex = content.indexOf('const request = require');
    if (requiresIndex !== -1) {
      content = mockSetup + content;
    }
  }

  fs.writeFileSync(filePath, content, 'utf8');
  console.log(`✓ ${idx + 1}/${files.length} - Fixed ${file}`);
});

console.log(`\n✅ Conversion complete! Run: npm test -- tests/integration/routes/ --no-coverage`);
