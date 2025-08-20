#!/usr/bin/env node
/**
 * Fix unused variables by prefixing with underscore
 */

const fs = require('fs');
const { execSync } = require('child_process');

console.log('🔧 Fixing unused variables by prefixing with underscore...');

// Get list of files with unused variable warnings
try {
  const lintOutput = execSync('npm run lint 2>&1', { encoding: 'utf8' });
  const unusedVarMatches = lintOutput.match(/^(.+\.jsx?):\s*(\d+):(\d+)\s+(?:warning|error)\s+['`]([^'`]+)['`]\s+is.*?(?:defined but never used|assigned a value but never used)/gm);
  
  if (!unusedVarMatches) {
    console.log('   ✅ No unused variable issues found');
    return;
  }

  const fileIssues = {};
  unusedVarMatches.forEach(match => {
    const parts = match.match(/^([^:]+):.*?['`]([^'`]+)['`]/);
    if (parts) {
      const file = parts[1].trim();
      const varName = parts[2].trim();
      if (!fileIssues[file]) fileIssues[file] = [];
      fileIssues[file].push(varName);
    }
  });

  Object.keys(fileIssues).forEach(filePath => {
    try {
      if (fs.existsSync(filePath)) {
        let content = fs.readFileSync(filePath, 'utf8');
        const variables = fileIssues[filePath];
        
        variables.forEach(varName => {
          if (varName.startsWith('_')) return; // Already prefixed
          
          // Handle different variable declaration patterns
          const patterns = [
            // Function parameters
            new RegExp(`\\b(\\w+)\\s*\\(([^)]*\\b)${varName}(\\b[^)]*)\\)`, 'g'),
            // Array destructuring
            new RegExp(`\\[([^\\]]*\\b)${varName}(\\b[^\\]]*)\\]`, 'g'),
            // Object destructuring
            new RegExp(`\\{([^}]*\\b)${varName}(\\b[^}]*)\\}`, 'g'),
            // Variable declarations
            new RegExp(`\\b(const|let|var)\\s+${varName}\\b`, 'g'),
          ];
          
          patterns.forEach(pattern => {
            content = content.replace(pattern, (match) => {
              return match.replace(new RegExp(`\\b${varName}\\b`, 'g'), `_${varName}`);
            });
          });
        });
        
        fs.writeFileSync(filePath, content);
        console.log(`   ✅ Fixed ${variables.length} unused variables in ${filePath}`);
      }
    } catch (e) {
      console.log(`   ⚠️  Failed to fix ${filePath}:`, e.message);
    }
  });

} catch (e) {
  console.log('   ⚠️  Error getting lint output:', e.message);
}

console.log('🎉 Unused variable fixes completed!');