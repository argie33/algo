#!/usr/bin/env node
const fs = require('fs');
const path = require('path');

const routesDir = path.join(__dirname, 'webapp/lambda/routes');
const files = fs.readdirSync(routesDir).filter(f => f.endsWith('.js'));

console.log(`\n📝 Batch fixing response formatting in ${files.length} route files...\n`);

let stats = { filesChanged: 0, totalFixes: 0 };

for (const file of files) {
  const filePath = path.join(routesDir, file);
  let content = fs.readFileSync(filePath, 'utf8');
  const original = content;
  let fileChanged = false;

  // Step 1: Ensure file imports response helpers (skip if missing database import)
  const hasDatabaseImport = content.includes("require('../utils/database')");
  const hasHelperImport = content.includes('sendSuccess') || content.includes('sendError') || content.includes('sendPaginated');

  if (hasDatabaseImport && !hasHelperImport) {
    const routerLine = "const router = express.Router();";
    if (content.includes(routerLine)) {
      const importStmt = "\nconst { sendSuccess, sendError, sendPaginated } = require('../utils/apiResponse');";
      content = content.replace(
        routerLine,
        `${importStmt}\nconst router = express.Router();`
      );
      fileChanged = true;
    }
  }

  // Step 2: Fix res.status(XXX).json({...error...}) -> sendError
  // Pattern: return res.status(404).json({error: "..."})
  content = content.replace(
    /return\s+res\.status\((\d+)\)\.json\(\{\s*error\s*:\s*"([^"]+)"[^}]*\}\s*\)/g,
    'return sendError(res, "$2", $1)'
  );

  // Step 3: Fix res.status(XXX).json({...error...}) with single quotes
  content = content.replace(
    /return\s+res\.status\((\d+)\)\.json\(\{\s*error\s*:\s*'([^']+)'[^}]*\}\s*\)/g,
    "return sendError(res, '$2', $1)"
  );

  // Step 4: Fix remaining res.status().json() calls
  content = content.replace(
    /return\s+res\.status\((\d+)\)\.json\(([^)]+)\)/g,
    (match, code) => {
      // Return the original but log it as needing manual review
      return match;
    }
  );

  // Step 5: Fix simple res.json() calls returning {success: true, ...}
  // This is a safer replacement that maintains structure
  content = content.replace(
    /return\s+res\.json\(\{\s*([^}]*success\s*:\s*true[^}]*)\}\s*\);/g,
    (match, content_inner) => {
      // Check if this has a 'data' property or 'items' property
      if (content_inner.includes('data:') || content_inner.includes('items:')) {
        // Don't change - let sendSuccess handle it properly
        return match.replace('res.json({', 'sendSuccess(res, {')
                           .replace(/,\s*success\s*:\s*true[^}]*}/, '})');
      }
      return match;
    }
  );

  // Step 6: Fix checkDatabaseAvailable helper calls
  content = content.replace(
    /return\s+res\.status\(503\)\.json\(\{\s*error\s*:\s*"[^"]+"\s*,\s*success\s*:\s*false\s*\}\s*\)/g,
    'return sendError(res, "Database service unavailable", 503)'
  );

  // Step 7: Remove orphaned success fields in res.json() that will become sendSuccess
  if (content !== original) {
    fileChanged = true;
  }

  if (fileChanged) {
    fs.writeFileSync(filePath, content, 'utf8');
    const fixes = (original.match(/res\.json\(|res\.status.*\.json\(/g) || []).length -
                    (content.match(/res\.json\(|res\.status.*\.json\(/g) || []).length;
    stats.filesChanged++;
    stats.totalFixes += fixes;
    if (fixes > 0) {
      console.log(`  ✓ ${file.padEnd(30)} ${fixes} fixes`);
    }
  }
}

console.log(`\n✅ Batch complete: ${stats.filesChanged} files changed, ${stats.totalFixes} issues fixed\n`);
