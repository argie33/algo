#!/usr/bin/env node
/**
 * Bulk patch frontend pages to add error handling to useApiQuery calls
 *
 * Pattern:
 * OLD:  const { data } = useApiQuery(...)
 * NEW:  const { data, error, isLoading } = useApiQuery(...)
 *
 * Usage: node patch-error-handling.js <page-file>
 */

const fs = require('fs');
const path = require('path');

function patchPageWithErrorHandling(filePath) {
  console.log(`Patching ${filePath}...`);
  let content = fs.readFileSync(filePath, 'utf-8');
  const originalLength = content.length;

  // Pattern 1: Extract error/isLoading from useApiQuery calls
  // OLD: const { data: X } = useApiQuery(...)
  // NEW: const { data: X, error: errX, isLoading: xLoading } = useApiQuery(...)

  content = content.replace(
    /const\s+{\s*data:\s*(\w+)\s*}\s*=\s*useApiQuery\(/g,
    'const { data: $1, error: err_$1, isLoading: ${1}_Loading } = useApiQuery('
  );

  // Handle destructuring patterns with items (paginated queries)
  content = content.replace(
    /const\s+{\s*items:\s*(\w+)\s*}\s*=\s*useApiPaginatedQuery\(/g,
    'const { items: $1, error: err_$1, isLoading: ${1}_Loading } = useApiPaginatedQuery('
  );

  if (content.length > originalLength) {
    fs.writeFileSync(filePath, content, 'utf-8');
    console.log(`✓ Patched successfully`);
    return true;
  } else {
    console.log(`⚠ No changes made`);
    return false;
  }
}

// Patch target files
const pagesToPatch = [
  'webapp/frontend/src/pages/ScoresDashboard.jsx',
  'webapp/frontend/src/pages/PortfolioDashboard.jsx',
  'webapp/frontend/src/pages/SectorAnalysis.jsx',
];

pagesToPatch.forEach(pagePath => {
  const fullPath = path.join(process.cwd(), pagePath);
  if (fs.existsSync(fullPath)) {
    patchPageWithErrorHandling(fullPath);
  } else {
    console.log(`✗ File not found: ${fullPath}`);
  }
});

console.log('\nDone!');
