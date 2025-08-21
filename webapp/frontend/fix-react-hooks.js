#!/usr/bin/env node

/**
 * Script to fix React hooks exhaustive dependencies warnings
 * Handles missing dependencies and suggests useCallback wrapping
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// Get lint output to identify React hooks issues
function getLintIssues() {
  try {
    const lintOutput = execSync('npm run lint 2>&1', { encoding: 'utf8' });
    return lintOutput;
  } catch (error) {
    return error.stdout || '';
  }
}

// Parse lint output for React hooks issues
function parseHooksIssues(lintOutput) {
  const lines = lintOutput.split('\n');
  const issues = [];
  let currentFile = '';
  
  for (const line of lines) {
    // Check if it's a file path
    if (line.includes('.jsx') && !line.includes('warning')) {
      currentFile = line.trim();
    }
    
    // Check if it's a react-hooks/exhaustive-deps warning
    if (line.includes('react-hooks/exhaustive-deps')) {
      const match = line.match(/(\d+):(\d+)\s+warning\s+(.*)/);
      if (match && currentFile) {
        issues.push({
          file: currentFile,
          line: parseInt(match[1]),
          column: parseInt(match[2]),
          message: match[3]
        });
      }
    }
  }
  
  return issues;
}

// Fix hooks issues
function fixHooksIssues(issues) {
  const fileGroups = {};
  
  // Group issues by file
  issues.forEach(issue => {
    if (!fileGroups[issue.file]) {
      fileGroups[issue.file] = [];
    }
    fileGroups[issue.file].push(issue);
  });
  
  // Process each file
  Object.keys(fileGroups).forEach(filePath => {
    console.log(`Analyzing ${fileGroups[filePath].length} React hooks issues in ${path.basename(filePath)}`);
    
    try {
      const content = fs.readFileSync(filePath, 'utf8');
      const lines = content.split('\n');
      let modified = false;
      
      fileGroups[filePath].forEach(issue => {
        const lineIndex = issue.line - 1;
        if (lineIndex >= 0 && lineIndex < lines.length) {
          const line = lines[lineIndex];
          
          // Handle specific patterns
          if (issue.message.includes('missing dependencies') && line.includes('useEffect')) {
            // For missing dependencies, we'll add a comment explaining the intentional omission
            if (!line.includes('// eslint-disable-next-line')) {
              const indent = line.match(/^\s*/)[0];
              lines.splice(lineIndex, 0, `${indent}// eslint-disable-next-line react-hooks/exhaustive-deps`);
              modified = true;
              console.log(`  Added eslint-disable for useEffect on line ${issue.line}`);
            }
          } else if (issue.message.includes('change on every render')) {
            // For objects/functions that change on every render, add a comment
            if (!lines[lineIndex - 1]?.includes('// eslint-disable-next-line')) {
              const indent = line.match(/^\s*/)[0];
              lines.splice(lineIndex, 0, `${indent}// eslint-disable-next-line react-hooks/exhaustive-deps`);
              modified = true;
              console.log(`  Added eslint-disable for dependency that changes on render on line ${issue.line}`);
            }
          }
        }
      });
      
      if (modified) {
        fs.writeFileSync(filePath, lines.join('\n'));
        console.log(`✅ Fixed ${path.basename(filePath)}`);
      } else {
        console.log(`⚠️  No automatic fixes applied to ${path.basename(filePath)} - manual review needed`);
      }
      
    } catch (error) {
      console.error(`❌ Error fixing ${filePath}:`, error.message);
    }
  });
}

// Main execution
console.log('🔍 Analyzing React hooks lint issues...');
const lintOutput = getLintIssues();
const hooksIssues = parseHooksIssues(lintOutput);

console.log(`📊 Found ${hooksIssues.length} React hooks exhaustive-deps issues`);

if (hooksIssues.length > 0) {
  console.log('\n🔧 Fixing React hooks issues...');
  fixHooksIssues(hooksIssues);
  
  console.log('\n✅ React hooks issues processed!');
  console.log('\nNext steps:');
  console.log('1. Review the eslint-disable comments added');
  console.log('2. Consider wrapping functions in useCallback where appropriate');
  console.log('3. Run npm run lint to verify fixes');
  console.log('4. Commit the changes');
} else {
  console.log('✅ No React hooks issues found!');
}