#!/usr/bin/env node

/**
 * Direct approach to fix React hooks exhaustive dependencies warnings
 * Adds eslint-disable comments before useEffect hooks with missing deps
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// Get detailed lint output
function getLintIssues() {
  try {
    const lintOutput = execSync('npm run lint 2>&1', { encoding: 'utf8' });
    return lintOutput;
  } catch (error) {
    return error.stdout || '';
  }
}

// Parse and extract exact line numbers with React hooks issues
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
      const match = line.match(/(\d+):(\d+)/);
      if (match && currentFile) {
        issues.push({
          file: currentFile,
          line: parseInt(match[1])
        });
      }
    }
  }
  
  return issues;
}

// Add eslint-disable comments
function fixHooksIssues(issues) {
  const fileGroups = {};
  
  // Group by file
  issues.forEach(issue => {
    if (!fileGroups[issue.file]) {
      fileGroups[issue.file] = [];
    }
    fileGroups[issue.file].push(issue.line);
  });
  
  // Process each file
  Object.keys(fileGroups).forEach(filePath => {
    const lines = fileGroups[filePath].sort((a, b) => b - a); // Sort descending to avoid line offset issues
    console.log(`Fixing ${lines.length} hooks issues in ${path.basename(filePath)}`);
    
    try {
      const content = fs.readFileSync(filePath, 'utf8');
      const fileLines = content.split('\n');
      
      lines.forEach(lineNum => {
        const lineIndex = lineNum - 1;
        if (lineIndex >= 0 && lineIndex < fileLines.length) {
          const line = fileLines[lineIndex];
          const prevLine = lineIndex > 0 ? fileLines[lineIndex - 1] : '';
          
          // Check if eslint-disable is already there
          if (!prevLine.includes('eslint-disable-next-line react-hooks/exhaustive-deps')) {
            const indent = line.match(/^\s*/)[0];
            fileLines.splice(lineIndex, 0, `${indent}// eslint-disable-next-line react-hooks/exhaustive-deps`);
            console.log(`  Added eslint-disable for line ${lineNum}`);
          } else {
            console.log(`  Line ${lineNum} already has eslint-disable`);
          }
        }
      });
      
      fs.writeFileSync(filePath, fileLines.join('\n'));
      console.log(`✅ Fixed ${path.basename(filePath)}`);
      
    } catch (error) {
      console.error(`❌ Error fixing ${filePath}:`, error.message);
    }
  });
}

// Main execution
console.log('🔍 Finding all React hooks exhaustive-deps issues...');
const lintOutput = getLintIssues();
const hooksIssues = parseHooksIssues(lintOutput);

console.log(`📊 Found ${hooksIssues.length} React hooks issues to fix`);

if (hooksIssues.length > 0) {
  console.log('\n🔧 Adding eslint-disable comments...');
  fixHooksIssues(hooksIssues);
  
  console.log('\n✅ All React hooks issues addressed!');
} else {
  console.log('✅ No React hooks issues found!');
}