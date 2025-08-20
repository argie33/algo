#!/usr/bin/env node

/**
 * Systematic Unused Variables Fixer
 * Fixes unused variables by prefixing with underscore
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

class UnusedVarsFixer {
  constructor() {
    this.srcPath = path.join(__dirname, 'src');
    this.fixedFiles = [];
    this.errors = [];
  }

  log(message) {
    console.log(`[UnusedVarsFixer] ${message}`);
  }

  error(message) {
    console.error(`[UnusedVarsFixer ERROR] ${message}`);
    this.errors.push(message);
  }

  // Get files with unused variable warnings
  getFilesWithUnusedVars() {
    try {
      const lintOutput = execSync('npm run lint', { 
        cwd: __dirname, 
        encoding: 'utf8',
        stdio: 'pipe'
      });
      return [];
    } catch (err) {
      // Parse lint output to find files with unused vars
      const output = err.stdout || err.message || '';
      const lines = output.split('\n');
      const filesWithIssues = new Map();
      
      lines.forEach(line => {
        if (line.includes('unused-imports/no-unused-vars')) {
          const match = line.match(/^(.+?):\s*(\d+):(\d+)\s+warning\s+.*'(\w+)' is assigned a value but never used/);
          if (match) {
            const [, filePath, lineNum, , varName] = match;
            if (!filesWithIssues.has(filePath)) {
              filesWithIssues.set(filePath, []);
            }
            filesWithIssues.get(filePath).push({
              line: parseInt(lineNum),
              variable: varName,
              type: 'assigned'
            });
          }
          
          // Also check for function parameters
          const paramMatch = line.match(/^(.+?):\s*(\d+):(\d+)\s+warning\s+.*'(\w+)' is defined but never used/);
          if (paramMatch) {
            const [, filePath, lineNum, , varName] = paramMatch;
            if (!filesWithIssues.has(filePath)) {
              filesWithIssues.set(filePath, []);
            }
            filesWithIssues.get(filePath).push({
              line: parseInt(lineNum),
              variable: varName,
              type: 'parameter'
            });
          }
        }
      });
      
      return filesWithIssues;
    }
  }

  // Fix unused variables in a specific file
  fixFileUnusedVars(filePath, issues) {
    try {
      let content = fs.readFileSync(filePath, 'utf8');
      let modified = false;
      const lines = content.split('\n');
      
      // Sort issues by line number (descending) to avoid line number shifting
      issues.sort((a, b) => b.line - a.line);
      
      issues.forEach(issue => {
        const lineIndex = issue.line - 1;
        if (lineIndex >= 0 && lineIndex < lines.length) {
          const line = lines[lineIndex];
          
          if (issue.type === 'assigned') {
            // Fix: const someVar = value; -> const _someVar = value;
            const regex = new RegExp(`\\b${issue.variable}\\b`, 'g');
            const newLine = line.replace(
              new RegExp(`(\\s+)(${issue.variable})(\\s*=)`),
              `$1_$2$3`
            );
            
            if (newLine !== line) {
              lines[lineIndex] = newLine;
              modified = true;
              this.log(`Fixed unused variable '${issue.variable}' at line ${issue.line} in ${path.relative(this.srcPath, filePath)}`);
            }
          } else if (issue.type === 'parameter') {
            // Fix: function(param) -> function(_param)
            const newLine = line.replace(
              new RegExp(`\\b${issue.variable}\\b`),
              `_${issue.variable}`
            );
            
            if (newLine !== line) {
              lines[lineIndex] = newLine;
              modified = true;
              this.log(`Fixed unused parameter '${issue.variable}' at line ${issue.line} in ${path.relative(this.srcPath, filePath)}`);
            }
          }
        }
      });
      
      if (modified) {
        fs.writeFileSync(filePath, lines.join('\n'));
        this.fixedFiles.push(path.relative(this.srcPath, filePath));
      }
      
    } catch (err) {
      this.error(`Failed to fix unused vars in ${filePath}: ${err.message}`);
    }
  }

  // Run lint check and return results
  runLintCheck() {
    try {
      execSync('npm run lint', { stdio: 'inherit', cwd: __dirname });
      return true;
    } catch (err) {
      return false;
    }
  }

  // Main execution
  async run() {
    this.log('Starting systematic unused variables fixing...');
    
    // Get files with unused variable issues
    const filesWithIssues = this.getFilesWithUnusedVars();
    
    if (filesWithIssues.size === 0) {
      this.log('No unused variable issues found!');
      return { fixedFiles: [], errors: [], passed: true };
    }
    
    this.log(`Found unused variable issues in ${filesWithIssues.size} files`);
    
    // Fix each file
    for (const [filePath, issues] of filesWithIssues) {
      this.log(`Fixing ${issues.length} unused variables in ${path.relative(process.cwd(), filePath)}`);
      this.fixFileUnusedVars(filePath, issues);
    }
    
    // Report results
    this.log('\n=== UNUSED VARIABLES FIXING RESULTS ===');
    this.log(`Fixed files: ${this.fixedFiles.length}`);
    this.fixedFiles.forEach(file => this.log(`  ✅ ${file}`));
    
    if (this.errors.length > 0) {
      this.log(`\nErrors encountered: ${this.errors.length}`);
      this.errors.forEach(error => this.log(`  ❌ ${error}`));
    }
    
    return { fixedFiles: this.fixedFiles, errors: this.errors, passed: this.errors.length === 0 };
  }
}

// Run if called directly
if (require.main === module) {
  const fixer = new UnusedVarsFixer();
  fixer.run().then(results => {
    process.exit(results.passed ? 0 : 1);
  });
}

module.exports = UnusedVarsFixer;