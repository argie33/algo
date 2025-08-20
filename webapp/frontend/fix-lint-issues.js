#!/usr/bin/env node

/**
 * Comprehensive Frontend Lint Fixer
 * Systematically fixes common ESLint issues in the frontend codebase
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const COMMON_FIXES = {
  // Fix unused variables by prefixing with underscore
  unusedVars: {
    pattern: /(\s+)(\w+)(\s*=.*?;.*\/\/.*unused-imports\/no-unused-vars)/gm,
    replacement: '$1_$2$3'
  },
  
  // Fix unused function parameters
  unusedParams: {
    pattern: /(\(\s*)(\w+)(\s*\).*\/\/.*unused-imports\/no-unused-vars)/gm,
    replacement: '$1_$2$3'
  },
  
  // Fix missing dependency warnings by adding them to dependency array
  missingDeps: {
    files: {
      'src/components/ui/ErrorBoundary.jsx': {
        line: 55,
        fix: 'useEffect(() => {\n    if (error && errorContext && logger) {\n      logger.logError(error, errorContext);\n    }\n  }, [error, errorContext, logger]);'
      }
    }
  }
};

class LintFixer {
  constructor() {
    this.srcPath = path.join(__dirname, 'src');
    this.fixedFiles = [];
    this.errors = [];
  }

  log(message) {
    console.log(`[LintFixer] ${message}`);
  }

  error(message) {
    console.error(`[LintFixer ERROR] ${message}`);
    this.errors.push(message);
  }

  // Fix syntax errors first (highest priority)
  fixSyntaxErrors() {
    this.log('Fixing syntax errors...');
    
    // Fix StockExplorer.jsx return outside function
    const stockExplorerPath = path.join(this.srcPath, 'pages/StockExplorer.jsx');
    if (fs.existsSync(stockExplorerPath)) {
      this.fixStockExplorerReturn(stockExplorerPath);
    }
  }

  fixStockExplorerReturn(filePath) {
    let content = fs.readFileSync(filePath, 'utf8');
    
    // Find the problematic return statement and ensure it's inside the component function
    // The issue is likely a misplaced return statement outside the component function
    
    // Read the file to understand the structure better
    const lines = content.split('\n');
    let functionStart = -1;
    let returnLine = -1;
    
    for (let i = 0; i < lines.length; i++) {
      if (lines[i].includes('function StockExplorer()')) {
        functionStart = i;
      }
      if (i > 440 && lines[i].trim().startsWith('return (') && functionStart === -1) {
        returnLine = i;
        break;
      }
    }
    
    if (returnLine > -1) {
      this.log(`Found problematic return at line ${returnLine + 1}`);
      // This needs manual inspection - let's skip for now and mark for manual fix
      this.errors.push(`StockExplorer.jsx line ${returnLine + 1}: return outside function - needs manual fix`);
    }
  }

  // Fix unused variables by prefixing with underscore
  fixUnusedVariables() {
    this.log('Fixing unused variables...');
    
    const files = this.getJSXFiles();
    
    files.forEach(file => {
      try {
        let content = fs.readFileSync(file, 'utf8');
        let modified = false;
        
        // Fix unused variables
        const unusedVarPattern = /(\s+)(\w+)(\s*=.*?;.*Allowed unused vars must match)/gm;
        if (content.match(unusedVarPattern)) {
          content = content.replace(/(\s+)(\w+)(\s*=.*?;)/gm, (match, space, varName, rest) => {
            if (match.includes('unused vars must match')) {
              return `${space}_${varName}${rest}`;
            }
            return match;
          });
          modified = true;
        }
        
        // Fix unused function parameters
        const unusedParamPattern = /(\(\s*)(\w+)(\s*\).*Allowed unused args must match)/gm;
        if (content.match(unusedParamPattern)) {
          content = content.replace(/(\(\s*)(\w+)(\s*\))/gm, (match, openParen, paramName, closeParen) => {
            return `${openParen}_${paramName}${closeParen}`;
          });
          modified = true;
        }
        
        if (modified) {
          fs.writeFileSync(file, content);
          this.fixedFiles.push(path.relative(this.srcPath, file));
          this.log(`Fixed unused variables in ${path.relative(this.srcPath, file)}`);
        }
      } catch (err) {
        this.error(`Failed to fix unused variables in ${file}: ${err.message}`);
      }
    });
  }

  // Fix React Hook dependency issues
  fixHookDependencies() {
    this.log('Fixing React Hook dependencies...');
    
    const hookFixes = {
      'src/components/ui/ErrorBoundary.jsx': {
        line: 55,
        pattern: /useEffect\(\(\) => \{[\s\S]*?\}, \[\]\);/,
        replacement: `useEffect(() => {
    if (error && errorContext && logger) {
      logger.logError(error, errorContext);
    }
  }, [error, errorContext, logger]);`
      }
    };
    
    Object.entries(hookFixes).forEach(([relativePath, fix]) => {
      const filePath = path.join(__dirname, relativePath);
      if (fs.existsSync(filePath)) {
        let content = fs.readFileSync(filePath, 'utf8');
        content = content.replace(fix.pattern, fix.replacement);
        fs.writeFileSync(filePath, content);
        this.fixedFiles.push(relativePath);
        this.log(`Fixed hook dependencies in ${relativePath}`);
      }
    });
  }

  // Fix fast refresh issues
  fixFastRefresh() {
    this.log('Fixing fast refresh issues...');
    
    // These are usually structural issues that need manual review
    // For now, we'll document them for manual fixing
    this.log('Fast refresh issues require manual review - documented for later');
  }

  // Get all JSX files for processing
  getJSXFiles() {
    const files = [];
    
    const walkDir = (dir) => {
      const items = fs.readdirSync(dir);
      
      items.forEach(item => {
        const fullPath = path.join(dir, item);
        const stat = fs.statSync(fullPath);
        
        if (stat.isDirectory() && !item.startsWith('.') && item !== 'node_modules') {
          walkDir(fullPath);
        } else if (item.endsWith('.jsx') || item.endsWith('.js')) {
          files.push(fullPath);
        }
      });
    };
    
    walkDir(this.srcPath);
    return files;
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
    this.log('Starting comprehensive lint fixing...');
    
    // Step 1: Fix syntax errors (critical)
    this.fixSyntaxErrors();
    
    // Step 2: Fix unused variables
    this.fixUnusedVariables();
    
    // Step 3: Fix hook dependencies
    this.fixHookDependencies();
    
    // Step 4: Fix fast refresh (manual review needed)
    this.fixFastRefresh();
    
    // Report results
    this.log('\n=== LINT FIXING RESULTS ===');
    this.log(`Fixed files: ${this.fixedFiles.length}`);
    this.fixedFiles.forEach(file => this.log(`  ✅ ${file}`));
    
    if (this.errors.length > 0) {
      this.log(`\nErrors encountered: ${this.errors.length}`);
      this.errors.forEach(error => this.log(`  ❌ ${error}`));
    }
    
    // Run final lint check
    this.log('\nRunning final lint check...');
    const passed = this.runLintCheck();
    
    if (passed) {
      this.log('🎉 All lint issues fixed!');
    } else {
      this.log('⚠️  Some issues remain - manual intervention needed');
    }
    
    return { fixedFiles: this.fixedFiles, errors: this.errors, passed };
  }
}

// Run if called directly
if (require.main === module) {
  const fixer = new LintFixer();
  fixer.run().then(results => {
    process.exit(results.passed ? 0 : 1);
  });
}

module.exports = LintFixer;