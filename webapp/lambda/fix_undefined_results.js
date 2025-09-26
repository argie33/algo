const fs = require('fs');
const path = require('path');

// Files that commonly have undefined result.rows issues
const criticalFiles = [
  'routes/price.js',
  'routes/stocks.js',
  'routes/watchlist.js',
  'routes/debug.js',
  'routes/market.js',
  'routes/sectors.js',
  'routes/sentiment.js',
  'routes/news.js',
  'routes/earnings.js',
  'routes/economic.js'
];

// Pattern to add safety check before accessing result.rows
function addSafetyCheck(content) {
  // Replace patterns like: return result.rows[0].exists;
  content = content.replace(
    /return\s+result\.rows\[0\]\.([a-zA-Z_][a-zA-Z0-9_]*);/g,
    `if (!result || !result.rows || result.rows.length === 0) {
      console.warn('Query returned invalid result:', result);
      return null;
    }
    return result.rows[0].$1;`
  );

  // Replace patterns like: const data = result.rows[0];
  content = content.replace(
    /const\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*result\.rows\[0\];/g,
    `if (!result || !result.rows || result.rows.length === 0) {
      console.warn('Query returned invalid result for $1:', result);
      const $1 = null;
    } else {
      const $1 = result.rows[0];
    }`
  );

  // Replace patterns like: data: result.rows[0],
  content = content.replace(
    /(\s+)([a-zA-Z_][a-zA-Z0-9_]*:\s*)result\.rows\[0\],/g,
    `$1$2(result && result.rows && result.rows[0]) || {},`
  );

  return content;
}

function applySafetyFixes() {
  console.log('🔧 Applying safety fixes for undefined result.rows issues...');

  let filesFixed = 0;

  for (const filePath of criticalFiles) {
    try {
      if (!fs.existsSync(filePath)) {
        console.log(`⚠️ File not found: ${filePath}`);
        continue;
      }

      const content = fs.readFileSync(filePath, 'utf8');
      const fixedContent = addSafetyCheck(content);

      if (content !== fixedContent) {
        fs.writeFileSync(filePath, fixedContent);
        console.log(`✅ Fixed: ${filePath}`);
        filesFixed++;
      } else {
        console.log(`✓ No changes needed: ${filePath}`);
      }
    } catch (error) {
      console.error(`❌ Error fixing ${filePath}:`, error.message);
    }
  }

  console.log(`🎯 Safety fixes completed! ${filesFixed} files were updated.`);
}

// Run the fixes
applySafetyFixes();