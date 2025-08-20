#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// Get all JSX files with hook issues
function getFilesWithHookIssues() {
  try {
    const lintOutput = execSync('npm run lint', { encoding: 'utf8', stdio: 'pipe' });
    return [];
  } catch (error) {
    const lines = error.stdout.split('\n');
    const files = new Set();
    
    lines.forEach(line => {
      if (line.includes('exhaustive-deps') || line.includes('missing dependencies')) {
        // Extract file path
        const match = line.match(/^([^:]+):/);
        if (match) {
          files.add(match[1]);
        }
      }
    });
    
    return Array.from(files);
  }
}

// Fix common hook dependency issues
function fixHookDependencies(filePath) {
  console.log(`Fixing hook dependencies in: ${filePath}`);
  let content = fs.readFileSync(filePath, 'utf8');
  let modified = false;
  
  // Fix pattern: useEffect(() => { someFunction(); }, []) 
  // where someFunction is defined in the component
  const useEffectPattern = /useEffect\(\(\) => \{[^}]*(\w+)\(\);[^}]*\}, \[\]\);?/g;
  content = content.replace(useEffectPattern, (match, funcName) => {
    // Check if the function is defined in the same file
    if (content.includes(`const ${funcName} = `) || content.includes(`function ${funcName}`)) {
      console.log(`  Adding ${funcName} to useEffect dependencies`);
      modified = true;
      return match.replace('[]', `[${funcName}]`);
    }
    return match;
  });
  
  // Fix pattern: useEffect with fetchData function
  content = content.replace(
    /useEffect\(\(\) => \{\s*fetchData\(\);\s*\}, \[\]\);?/g,
    (match) => {
      console.log(`  Adding fetchData to useEffect dependencies`);
      modified = true;
      return match.replace('[]', '[fetchData]');
    }
  );
  
  // Fix common missing auth dependencies
  content = content.replace(
    /useEffect\(\(\) => \{[^}]*\}, \[\]\);?/g,
    (match) => {
      if (match.includes('isAuthenticated') || match.includes('auth.')) {
        if (!match.includes('[isAuthenticated]') && !match.includes('[auth')) {
          console.log(`  Adding auth dependencies to useEffect`);
          modified = true;
          return match.replace('[]', '[isAuthenticated]');
        }
      }
      return match;
    }
  );
  
  // Fix useMemo missing dependencies
  content = content.replace(
    /useMemo\(\(\) => \{[^}]*\}, \[\]\);?/g,
    (match) => {
      // Extract variables used inside useMemo
      const variables = [];
      const usedVars = match.match(/\b[a-zA-Z_]\w*\b/g);
      
      if (usedVars) {
        // Common variables that should be dependencies
        const commonDeps = ['allColumns', 'data', 'filteredData', 'sortedData'];
        usedVars.forEach(v => {
          if (commonDeps.includes(v) && !variables.includes(v)) {
            variables.push(v);
          }
        });
      }
      
      if (variables.length > 0) {
        console.log(`  Adding [${variables.join(', ')}] to useMemo dependencies`);
        modified = true;
        return match.replace('[]', `[${variables.join(', ')}]`);
      }
      return match;
    }
  );
  
  // Add useCallback for functions used as dependencies
  const lines = content.split('\n');
  const newLines = [];
  let inComponent = false;
  let currentIndent = '';
  
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    newLines.push(line);
    
    // Detect component function definitions
    if (line.includes('const ') && line.includes('= async () => {')) {
      const funcName = line.match(/const\s+(\w+)/)?.[1];
      if (funcName && (funcName.startsWith('fetch') || funcName.includes('Data') || funcName.includes('load'))) {
        // Check if this function is used in useEffect without useCallback
        const restOfFile = lines.slice(i).join('\n');
        if (restOfFile.includes(`[${funcName}]`) && !line.includes('useCallback')) {
          console.log(`  Wrapping ${funcName} with useCallback`);
          const indent = line.match(/^(\s*)/)[1];
          newLines[newLines.length - 1] = line.replace(
            `const ${funcName} = async () => {`,
            `const ${funcName} = useCallback(async () => {`
          );
          
          // Find the closing brace and add dependency array
          let braceCount = 1;
          for (let j = i + 1; j < lines.length; j++) {
            newLines.push(lines[j]);
            braceCount += (lines[j].match(/\{/g) || []).length;
            braceCount -= (lines[j].match(/\}/g) || []).length;
            if (braceCount === 0) {
              newLines[newLines.length - 1] = lines[j] + ', []);';
              i = j;
              modified = true;
              break;
            }
          }
        }
      }
    }
  }
  
  if (modified) {
    // Add useCallback import if needed
    if (content.includes('useCallback') && !content.includes('import React') && !content.includes('from "react"')) {
      content = 'import React, { useCallback } from "react";\n' + content;
      newLines.unshift('import React, { useCallback } from "react";');
    } else if (content.includes('useCallback') && content.includes('from "react"') && !content.includes('useCallback')) {
      content = content.replace(
        /import[^{]*\{([^}]+)\}[^"]*"react"/,
        (match, imports) => {
          if (!imports.includes('useCallback')) {
            return match.replace(imports, imports.trim() + ', useCallback');
          }
          return match;
        }
      );
    }
    
    fs.writeFileSync(filePath, newLines.join('\n'));
    console.log(`  ✅ Fixed hook dependencies in: ${filePath}`);
    return true;
  }
  
  return false;
}

// Main execution
const files = getFilesWithHookIssues();
let totalModified = 0;

console.log(`Found ${files.length} files with hook dependency issues...`);

for (const file of files) {
  if (fixHookDependencies(file)) {
    totalModified++;
  }
}

console.log(`\n✅ Hook dependency fixes complete! Modified ${totalModified} files.`);

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