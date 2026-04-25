#!/usr/bin/env node
/**
 * Batch fix script: Replace all res.json() and res.status().json() calls
 * with proper sendSuccess/sendError/sendPaginated helpers
 */
const fs = require('fs');
const path = require('path');

const routesDir = './webapp/lambda/routes';
const files = fs.readdirSync(routesDir).filter(f => f.endsWith('.js'));

console.log(`Processing ${files.length} route files...`);

let totalFixed = 0;

for (const file of files) {
  const filePath = path.join(routesDir, file);
  let content = fs.readFileSync(filePath, 'utf8');
  const original = content;

  // 1. Ensure file imports response helpers
  if (!content.includes('sendSuccess') && !content.includes('sendError')) {
    if (content.includes("const router = express.Router()")) {
      const importLine = "const { sendSuccess, sendError, sendPaginated } = require('../utils/apiResponse');\n";
      content = content.replace(
        "const router = express.Router();",
        `const { sendSuccess, sendError, sendPaginated } = require('../utils/apiResponse');\nconst router = express.Router();`
      );
    }
  }

  // 2. Fix res.status(XXX).json() -> sendError
  const statusJsonPattern = /return\s+res\.status\((\d+)\)\.json\(\s*\{([^}]*error[^}]*)\}\s*\)/g;
  let match;
  while ((match = statusJsonPattern.exec(original)) !== null) {
    const code = match[1];
    // Extract error message if possible
    const errorPart = match[2];
    const errorMatch = errorPart.match(/error\s*:\s*["']([^"']+)["']/);
    const errorMsg = errorMatch ? errorMatch[1] : 'Error';

    content = content.replace(match[0], `return sendError(res, "${errorMsg}", ${code})`);
    totalFixed++;
  }

  // 3. Fix simple res.json() -> sendSuccess (but be careful)
  // Only fix ones that look like data responses (not redirects or simple documentation)
  const jsonPattern = /return\s+res\.json\(\{([^}]*success[^}]*)\}\);/g;
  content = content.replace(jsonPattern, (match) => {
    // Check if this looks like a success response with data
    if (match.includes('success: true')) {
      totalFixed++;
      // Extract the data part
      const dataMatch = match.match(/data\s*:\s*(\{[^}]+\})/);
      if (dataMatch) {
        return `return sendSuccess(res, ${dataMatch[1]});`;
      } else {
        // No data wrapper, just pass the object minus success flag
        return match.replace('success: true,', '').replace(', success: true', '');
      }
    }
    return match;
  });

  if (content !== original) {
    fs.writeFileSync(filePath, content, 'utf8');
    const count = (original.match(/res\.json\(|res\.status.*\.json\(/g) || []).length -
                    (content.match(/res\.json\(|res\.status.*\.json\(/g) || []).length;
    if (count > 0) {
      console.log(`✓ ${file}: ${count} fixes applied`);
    }
  }
}

console.log(`\n✓ Batch processing complete. Total issues fixed: ${totalFixed}`);
