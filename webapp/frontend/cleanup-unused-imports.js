#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// Get all JSX files
function getAllJSXFiles(dir) {
  const files = [];
  const items = fs.readdirSync(dir);
  
  for (const item of items) {
    const fullPath = path.join(dir, item);
    const stat = fs.statSync(fullPath);
    
    if (stat.isDirectory() && !item.includes('node_modules') && !item.includes('.git')) {
      files.push(...getAllJSXFiles(fullPath));
    } else if (item.endsWith('.jsx') || item.endsWith('.js')) {
      files.push(fullPath);
    }
  }
  
  return files;
}

// Remove unused imports from a file
function removeUnusedImports(filePath) {
  console.log(`Processing: ${filePath}`);
  let content = fs.readFileSync(filePath, 'utf8');
  let modified = false;
  
  // Common unused import patterns
  const patterns = [
    // Remove unused imports from destructured imports
    { 
      regex: /import\s*{\s*([^}]+)\s*}\s*from\s*['"][^'"]+['"];?\n/g,
      handler: (match, imports) => {
        const importList = imports.split(',').map(imp => imp.trim());
        const usedImports = [];
        
        for (const imp of importList) {
          const varName = imp.split(' as ')[0].trim();
          // Check if this import is used in the file
          const usageRegex = new RegExp(`\\b${varName}\\b`, 'g');
          const matches = content.match(usageRegex);
          if (matches && matches.length > 1) { // More than just the import
            usedImports.push(imp);
          }
        }
        
        if (usedImports.length === 0) {
          modified = true;
          return ''; // Remove entire import
        } else if (usedImports.length !== importList.length) {
          modified = true;
          return match.replace(imports, usedImports.join(', '));
        }
        return match;
      }
    },
    // Remove unused single imports
    {
      regex: /import\s+(\w+)\s+from\s+['"][^'"]+['"];?\n/g,
      handler: (match, importName) => {
        const usageRegex = new RegExp(`\\b${importName}\\b`, 'g');
        const matches = content.match(usageRegex);
        if (!matches || matches.length <= 1) { // Only the import itself
          modified = true;
          return '';
        }
        return match;
      }
    }
  ];
  
  // Apply patterns
  for (const pattern of patterns) {
    content = content.replace(pattern.regex, pattern.handler);
  }
  
  // Remove unused variable declarations
  const lines = content.split('\n');
  const cleanedLines = [];
  
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    
    // Skip lines with unused variable declarations
    if (line.includes('= ') && 
        (line.includes('const ') || line.includes('let ') || line.includes('var ')) &&
        !line.includes('return') && 
        !line.includes('export')) {
      
      // Extract variable name
      const match = line.match(/\b(?:const|let|var)\s+(\w+)/);
      if (match) {
        const varName = match[1];
        const usageRegex = new RegExp(`\\b${varName}\\b`, 'g');
        const restOfFile = lines.slice(i + 1).join('\n');
        
        if (!usageRegex.test(restOfFile)) {
          console.log(`  Removing unused variable: ${varName}`);
          modified = true;
          continue; // Skip this line
        }
      }
    }
    
    cleanedLines.push(line);
  }
  
  if (modified) {
    fs.writeFileSync(filePath, cleanedLines.join('\n'));
    console.log(`  ✅ Modified: ${filePath}`);
    return true;
  }
  
  return false;
}

// Main execution
const srcDir = './src';
const files = getAllJSXFiles(srcDir);
let totalModified = 0;

console.log(`Found ${files.length} JavaScript/JSX files to process...`);

for (const file of files) {
  if (removeUnusedImports(file)) {
    totalModified++;
  }
}

console.log(`\n✅ Cleanup complete! Modified ${totalModified} files.`);

// Run lint again to check results
try {
  console.log('\n🔍 Running lint check...');
  const result = execSync('npm run lint', { encoding: 'utf8' });
  console.log(result);
} catch (error) {
  const issueCount = error.stdout.match(/✖ (\d+) problems/);
  if (issueCount) {
    console.log(`Remaining issues: ${issueCount[1]}`);
  }
}