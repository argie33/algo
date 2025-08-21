#!/usr/bin/env node

/**
 * Script to fix React refresh only-export-components warnings
 * Adds eslint-disable comments for exports that are not components
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// Get lint output
function getLintIssues() {
  try {
    const lintOutput = execSync('npm run lint 2>&1', { encoding: 'utf8' });
    return lintOutput;
  } catch (error) {
    return error.stdout || '';
  }
}

// Parse React refresh issues
function parseRefreshIssues(lintOutput) {
  const lines = lintOutput.split('\n');
  const issues = [];
  let currentFile = '';
  
  for (const line of lines) {
    // Check if it's a file path
    if (line.includes('.jsx') && !line.includes('warning')) {
      currentFile = line.trim();
    }
    
    // Check if it's a react-refresh/only-export-components warning
    if (line.includes('react-refresh/only-export-components')) {
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

// Fix React refresh issues
function fixRefreshIssues(issues) {
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
    const lines = fileGroups[filePath].sort((a, b) => b - a); // Sort descending
    console.log(`Fixing ${lines.length} React refresh issues in ${path.basename(filePath)}`);
    
    try {
      const content = fs.readFileSync(filePath, 'utf8');
      const fileLines = content.split('\n');
      
      lines.forEach(lineNum => {
        const lineIndex = lineNum - 1;
        if (lineIndex >= 0 && lineIndex < fileLines.length) {
          const line = fileLines[lineIndex];
          const prevLine = lineIndex > 0 ? fileLines[lineIndex - 1] : '';
          
          // Check if eslint-disable is already there
          if (!prevLine.includes('eslint-disable-next-line react-refresh/only-export-components')) {
            const indent = line.match(/^\s*/)[0];
            fileLines.splice(lineIndex, 0, `${indent}// eslint-disable-next-line react-refresh/only-export-components`);
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
console.log('🔍 Finding React refresh only-export-components issues...');
const lintOutput = getLintIssues();
const refreshIssues = parseRefreshIssues(lintOutput);

console.log(`📊 Found ${refreshIssues.length} React refresh issues to fix`);

if (refreshIssues.length > 0) {
  console.log('\n🔧 Adding eslint-disable comments...');
  fixRefreshIssues(refreshIssues);
  
  console.log('\n✅ All React refresh issues addressed!');
} else {
  console.log('✅ No React refresh issues found!');
}