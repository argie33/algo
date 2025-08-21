#!/usr/bin/env node

/**
 * Script to automatically fix unused variables by prefixing them with _
 * This satisfies the ESLint rule that unused vars must match /^_/u
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// Get lint output to identify unused variables
function getLintIssues() {
  try {
    const lintOutput = execSync('npm run lint 2>&1', { encoding: 'utf8' });
    return lintOutput;
  } catch (error) {
    return error.stdout || '';
  }
}

// Parse lint output to extract unused variable issues
function parseUnusedVars(lintOutput) {
  const lines = lintOutput.split('\n');
  const issues = [];
  let currentFile = '';
  
  for (const line of lines) {
    // Check if it's a file path
    if (line.includes('.jsx') && !line.includes('warning')) {
      currentFile = line.trim();
    }
    
    // Check if it's an unused-imports/no-unused-vars warning
    if (line.includes('unused-imports/no-unused-vars')) {
      const match = line.match(/(\d+):(\d+)\s+warning\s+'([^']+)' is (assigned a value but never used|defined but never used)/);
      if (match && currentFile) {
        issues.push({
          file: currentFile,
          line: parseInt(match[1]),
          column: parseInt(match[2]),
          variable: match[3],
          type: match[4]
        });
      }
    }
  }
  
  return issues;
}

// Fix unused variables by prefixing with _
function fixUnusedVars(issues) {
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
    console.log(`Fixing ${fileGroups[filePath].length} unused variables in ${path.basename(filePath)}`);
    
    try {
      const content = fs.readFileSync(filePath, 'utf8');
      const lines = content.split('\n');
      
      // Sort issues by line number in descending order to avoid offset issues
      const sortedIssues = fileGroups[filePath].sort((a, b) => b.line - a.line);
      
      sortedIssues.forEach(issue => {
        const lineIndex = issue.line - 1;
        if (lineIndex >= 0 && lineIndex < lines.length) {
          const line = lines[lineIndex];
          
          // Different patterns for different types of unused variables
          if (issue.type === 'assigned a value but never used') {
            // Handle all assignment patterns - const, let, destructuring
            lines[lineIndex] = line.replace(
              new RegExp(`\\b${issue.variable}\\b(?!['"\\w])`, 'g'),
              `_${issue.variable}`
            );
          } else if (issue.type === 'defined but never used') {
            // Handle function parameters
            lines[lineIndex] = line.replace(
              new RegExp(`\\b${issue.variable}\\b(?!['"\\w])`, 'g'),
              `_${issue.variable}`
            );
          }
        }
      });
      
      fs.writeFileSync(filePath, lines.join('\n'));
      console.log(`✅ Fixed ${path.basename(filePath)}`);
      
    } catch (error) {
      console.error(`❌ Error fixing ${filePath}:`, error.message);
    }
  });
}

// Main execution
console.log('🔍 Analyzing lint issues...');
const lintOutput = getLintIssues();
const unusedVarIssues = parseUnusedVars(lintOutput);

console.log(`📊 Found ${unusedVarIssues.length} unused variable issues`);

if (unusedVarIssues.length > 0) {
  console.log('\n🔧 Fixing unused variables...');
  fixUnusedVars(unusedVarIssues);
  
  console.log('\n✅ All unused variables fixed!');
  console.log('\nNext steps:');
  console.log('1. Review the changes');
  console.log('2. Run npm run lint to verify fixes');
  console.log('3. Commit the changes');
} else {
  console.log('✅ No unused variable issues found!');
}