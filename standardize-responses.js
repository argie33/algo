#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const glob = require('glob');

const routeFiles = glob.sync('webapp/lambda/routes/*.js').filter(f => !f.includes('signals.js'));

let fixed = 0;
let errors = 0;

routeFiles.forEach(file => {
  try {
    let content = fs.readFileSync(file, 'utf8');
    const original = content;

    // Fix 1: res.status(CODE).json({ error: "msg", success: false }) → sendError(res, "msg", CODE)
    content = content.replace(
      /return\s+res\.status\((\d+)\)\.json\(\s*{\s*error:\s*"([^"]+)",\s*success:\s*false\s*}\s*\)/g,
      'return sendError(res, "$2", $1)'
    );

    // Fix 2: res.status(CODE).json({ error: someVar, success: false }) → sendError(res, someVar, CODE)
    content = content.replace(
      /return\s+res\.status\((\d+)\)\.json\(\s*{\s*error:\s*([^,}]+),\s*success:\s*false\s*}\s*\)/g,
      'return sendError(res, $2, $1)'
    );

    // Fix 3: res.json({ items: x, pagination: y, success: true }) → sendPaginated(res, x, y)
    content = content.replace(
      /return\s+res\.json\(\s*{\s*items:\s*([^,}]+),\s*pagination:\s*([^,}]+),.*?success:\s*true.*?}\s*\)/gs,
      'return sendPaginated(res, $1, $2)'
    );

    // Fix 4: res.json({ data: x, pagination: y, success: true }) → sendPaginated(res, x, y)
    content = content.replace(
      /return\s+res\.json\(\s*{\s*data:\s*([^,}]+),\s*pagination:\s*([^,}]+),.*?success:\s*true.*?}\s*\)/gs,
      'return sendPaginated(res, $1, $2)'
    );

    // Fix 5: res.json({ data: x, success: true, ...}) → sendSuccess(res, x)
    content = content.replace(
      /return\s+res\.json\(\s*{\s*data:\s*([^,}]+),.*?success:\s*true.*?}\s*\)/gs,
      'return sendSuccess(res, $1)'
    );

    // Fix 6: res.json({ success: true }) → sendSuccess(res, {})
    content = content.replace(
      /return\s+res\.json\(\s*{\s*success:\s*true\s*}\s*\)/g,
      'return sendSuccess(res, {})'
    );

    if (content !== original) {
      fs.writeFileSync(file, content, 'utf8');
      console.log(`✅ Fixed: ${path.basename(file)}`);
      fixed++;
    }
  } catch (error) {
    console.error(`❌ Error in ${file}: ${error.message}`);
    errors++;
  }
});

console.log(`\n=== RESULTS ===`);
console.log(`Fixed: ${fixed} files`);
if (errors > 0) console.log(`Errors: ${errors}`);
