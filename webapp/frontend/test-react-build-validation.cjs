#!/usr/bin/env node

/**
 * React Build Validation Test
 * Catches React dependency conflicts, production errors, and bundle issues
 */

const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

class ReactBuildValidator {
  constructor() {
    this.testResults = {
      passed: 0,
      failed: 0,
      errors: []
    };
    this.distPath = path.join(__dirname, 'dist');
  }

  log(message, level = 'info') {
    const timestamp = new Date().toISOString();
    const prefix = level === 'error' ? '❌' : level === 'success' ? '✅' : 'ℹ️';
    console.log(`${prefix} [${timestamp}] ${message}`);
  }

  recordResult(test, passed, error = null) {
    if (passed) {
      this.testResults.passed++;
      this.log(`✅ ${test}`, 'success');
    } else {
      this.testResults.failed++;
      this.testResults.errors.push(error || test);
      this.log(`❌ ${test}`, 'error');
      if (error) {
        this.log(`   Error: ${error}`, 'error');
      }
    }
  }

  async testPackageJsonDependencies() {
    this.log('=== Testing Package.json Dependencies ===');
    
    try {
      const packageJson = JSON.parse(fs.readFileSync('package.json', 'utf8'));
      
      // Test 1: Check for React version compatibility
      const reactVersion = packageJson.dependencies.react;
      const reactDomVersion = packageJson.dependencies['react-dom'];
      
      if (reactVersion === reactDomVersion) {
        this.recordResult('React and ReactDOM versions match', true);
      } else {
        this.recordResult('React and ReactDOM versions match', false, 
          `React: ${reactVersion}, ReactDOM: ${reactDomVersion}`);
      }
      
      // Test 2: Check for conflicting use-sync-external-store
      const hasSyncExternalStore = packageJson.dependencies['use-sync-external-store'];
      if (!hasSyncExternalStore) {
        this.recordResult('No conflicting use-sync-external-store dependency', true);
      } else {
        this.recordResult('No conflicting use-sync-external-store dependency', false,
          'use-sync-external-store should not be explicitly included with React 18+');
      }
      
      // Test 3: Check for React Query compatibility
      const reactQueryVersion = packageJson.dependencies['@tanstack/react-query'];
      if (reactQueryVersion && reactQueryVersion.startsWith('^4.')) {
        this.recordResult('React Query version compatible with React 18', true);
      } else {
        this.recordResult('React Query version compatible with React 18', false,
          `Version ${reactQueryVersion} may have compatibility issues`);
      }
      
    } catch (error) {
      this.recordResult('Package.json dependencies validation', false, error.message);
    }
  }

  async testViteConfiguration() {
    this.log('=== Testing Vite Configuration ===');
    
    try {
      const viteConfigContent = fs.readFileSync('vite.config.js', 'utf8');
      
      // Test 1: Check for problematic aliases
      if (!viteConfigContent.includes('use-sync-external-store/shim')) {
        this.recordResult('No problematic use-sync-external-store alias', true);
      } else {
        this.recordResult('No problematic use-sync-external-store alias', false,
          'Vite config should not alias use-sync-external-store with React 18+');
      }
      
      // Test 2: Check for React plugin
      if (viteConfigContent.includes('@vitejs/plugin-react')) {
        this.recordResult('Vite React plugin configured', true);
      } else {
        this.recordResult('Vite React plugin configured', false,
          'Missing @vitejs/plugin-react');
      }
      
    } catch (error) {
      this.recordResult('Vite configuration validation', false, error.message);
    }
  }

  async testProductionBuild() {
    this.log('=== Testing Production Build ===');
    
    return new Promise((resolve) => {
      let buildOutput = '';
      let buildErrors = '';
      
      const buildProcess = spawn('npm', ['run', 'build'], {
        stdio: ['pipe', 'pipe', 'pipe'],
        shell: true
      });
      
      buildProcess.stdout.on('data', (data) => {
        buildOutput += data.toString();
      });
      
      buildProcess.stderr.on('data', (data) => {
        buildErrors += data.toString();
      });
      
      buildProcess.on('close', (code) => {
        if (code === 0) {
          this.recordResult('Production build completes successfully', true);
          
          // Check for specific error patterns in output
          if (!buildOutput.includes('Cannot set properties of undefined')) {
            this.recordResult('No React property setting errors in build', true);
          } else {
            this.recordResult('No React property setting errors in build', false,
              'Build output contains React property errors');
          }
          
          // Check for bundle warnings
          if (buildOutput.includes('Some chunks are larger than')) {
            this.log('⚠️ Bundle size warnings detected (not critical)');
          }
          
        } else {
          this.recordResult('Production build completes successfully', false,
            `Build failed with exit code ${code}: ${buildErrors}`);
        }
        
        resolve();
      });
      
      // Timeout after 60 seconds
      setTimeout(() => {
        buildProcess.kill();
        this.recordResult('Production build completes successfully', false,
          'Build timeout after 60 seconds');
        resolve();
      }, 60000);
    });
  }

  async testBundleIntegrity() {
    this.log('=== Testing Bundle Integrity ===');
    
    try {
      // Test 1: Check if dist folder exists
      if (fs.existsSync(this.distPath)) {
        this.recordResult('Dist folder created', true);
      } else {
        this.recordResult('Dist folder created', false, 'No dist folder found');
        return;
      }
      
      // Test 2: Check for main bundles
      const files = fs.readdirSync(path.join(this.distPath, 'assets'));
      const hasIndexJs = files.some(f => f.startsWith('index-') && f.endsWith('.js'));
      const hasVendorJs = files.some(f => f.startsWith('vendor-') && f.endsWith('.js'));
      
      if (hasIndexJs) {
        this.recordResult('Main index bundle exists', true);
      } else {
        this.recordResult('Main index bundle exists', false, 'No index-*.js bundle found');
      }
      
      if (hasVendorJs) {
        this.recordResult('Vendor bundle exists', true);
      } else {
        this.recordResult('Vendor bundle exists', false, 'No vendor-*.js bundle found');
      }
      
      // Test 3: Check for React in bundles (should not be duplicated)
      const indexBundle = files.find(f => f.startsWith('index-') && f.endsWith('.js'));
      if (indexBundle) {
        const bundleContent = fs.readFileSync(path.join(this.distPath, 'assets', indexBundle), 'utf8');
        
        // Check for React production indicators (check in vendor bundle specifically)
        const vendorBundle = files.find(f => f.startsWith('vendor-') && f.endsWith('.js'));
        if (vendorBundle) {
          const vendorContent = fs.readFileSync(path.join(this.distPath, 'assets', vendorBundle), 'utf8');
          if (vendorContent.includes('react.production')) {
            this.recordResult('Bundle uses React production build', true);
          } else {
            this.recordResult('Bundle uses React production build', false,
              'Vendor bundle missing react.production indicator');
          }
        } else {
          this.recordResult('Bundle uses React production build', false, 'No vendor bundle found');
        }
        
        // Check for use-sync-external-store conflicts
        const syncStoreOccurrences = (bundleContent.match(/use-sync-external-store/g) || []).length;
        if (syncStoreOccurrences <= 2) { // Some occurrences are expected
          this.recordResult('No excessive use-sync-external-store references', true);
        } else {
          this.recordResult('No excessive use-sync-external-store references', false,
            `Found ${syncStoreOccurrences} references, may indicate conflicts`);
        }
      }
      
    } catch (error) {
      this.recordResult('Bundle integrity validation', false, error.message);
    }
  }

  async testRuntimeErrors() {
    this.log('=== Testing Runtime Error Patterns ===');
    
    try {
      // Check for known error patterns in built files
      const assetsPath = path.join(this.distPath, 'assets');
      if (!fs.existsSync(assetsPath)) {
        this.recordResult('Runtime error pattern detection', false, 'No assets folder');
        return;
      }
      
      const jsFiles = fs.readdirSync(assetsPath).filter(f => f.endsWith('.js'));
      let hasProblematicPatterns = false;
      
      for (const file of jsFiles) {
        const content = fs.readFileSync(path.join(assetsPath, file), 'utf8');
        
        // Check for actual runtime error patterns (not minified library code)
        const problematicPatterns = [
          /Cannot set properties of undefined \(setting 'Children'\)/,
          /TypeError: Cannot read propert(y|ies) of undefined.*Children/,
          /\.Children is undefined/,
          /useSyncExternalStore.*undefined.*error/,
          /React\.Children.*undefined.*error/
        ];
        
        for (const pattern of problematicPatterns) {
          if (pattern.test(content)) {
            hasProblematicPatterns = true;
            this.recordResult('No problematic error patterns in bundles', false,
              `Found problematic pattern in ${file}`);
            break;
          }
        }
      }
      
      if (!hasProblematicPatterns) {
        this.recordResult('No problematic error patterns in bundles', true);
      }
      
    } catch (error) {
      this.recordResult('Runtime error pattern detection', false, error.message);
    }
  }

  async testSourceCodeImports() {
    this.log('=== Testing Source Code Imports ===');
    
    try {
      const packageJson = JSON.parse(fs.readFileSync('package.json', 'utf8'));
      const allDependencies = {
        ...packageJson.dependencies || {},
        ...packageJson.devDependencies || {}
      };
      
      // Get all JS/JSX files in src
      const srcFiles = this.getAllSourceFiles('src');
      let conflictingImports = [];
      let chartJsImports = [];
      
      for (const file of srcFiles) {
        try {
          const content = fs.readFileSync(file, 'utf8');
          
          // Extract all import statements
          const importMatches = content.match(/^import\s+.*?from\s+['"](.*?)['"];?$/gm) || [];
          
          for (const importLine of importMatches) {
            const packageMatch = importLine.match(/from\s+['"](.*?)['"];?$/);
            if (packageMatch) {
              const packageName = packageMatch[1];
              
              // Skip relative imports
              if (packageName.startsWith('.') || packageName.startsWith('/')) {
                continue;
              }
              
              // Extract base package name (handle scoped packages)
              const basePackage = packageName.startsWith('@') 
                ? packageName.split('/').slice(0, 2).join('/')
                : packageName.split('/')[0];
              
              // Check for Chart.js related imports (exclude recharts)
              if ((packageName.includes('chart') || packageName.includes('Chart')) && 
                  !packageName.includes('recharts') && 
                  (packageName.includes('chart.js') || packageName.includes('react-chartjs'))) {
                chartJsImports.push({
                  file: file.replace(process.cwd() + '/', ''),
                  package: packageName,
                  line: importLine.trim()
                });
              }
              
              // Check if package exists in dependencies (exclude Node.js built-ins and test files)
              const nodeBuiltins = ['fs', 'path', 'child_process', 'crypto', 'os', 'util', 'stream', 'events', 'http', 'https', 'url'];
              const isTestFile = file.includes('/tests/') || file.includes('.test.') || file.includes('.spec.');
              
              if (!allDependencies[basePackage] && 
                  !nodeBuiltins.includes(basePackage) && 
                  !isTestFile) {
                conflictingImports.push({
                  file: file.replace(process.cwd() + '/', ''),
                  package: basePackage,
                  fullImport: packageName,
                  line: importLine.trim()
                });
              }
            }
          }
        } catch (error) {
          // Skip files that can't be read
          continue;
        }
      }
      
      // Test 1: No Chart.js imports
      if (chartJsImports.length === 0) {
        this.recordResult('No Chart.js imports in source code', true);
      } else {
        this.recordResult('No Chart.js imports in source code', false,
          `Found Chart.js imports: ${chartJsImports.map(imp => imp.file).join(', ')}`);
        
        // Log details for debugging
        this.log('Chart.js imports found:');
        chartJsImports.forEach(imp => {
          this.log(`  ${imp.file}: ${imp.line}`, 'error');
        });
      }
      
      // Test 2: All imports have corresponding dependencies
      if (conflictingImports.length === 0) {
        this.recordResult('All imports have corresponding dependencies', true);
      } else {
        this.recordResult('All imports have corresponding dependencies', false,
          `Found imports without dependencies: ${conflictingImports.map(imp => imp.package).join(', ')}`);
        
        // Log details for debugging
        this.log('Missing dependencies:');
        conflictingImports.forEach(imp => {
          this.log(`  ${imp.file}: ${imp.fullImport}`, 'error');
        });
      }
      
    } catch (error) {
      this.recordResult('Source code import analysis', false, error.message);
    }
  }

  getAllSourceFiles(dir) {
    const files = [];
    
    try {
      const entries = fs.readdirSync(dir, { withFileTypes: true });
      
      for (const entry of entries) {
        const fullPath = path.join(dir, entry.name);
        
        if (entry.isDirectory() && !entry.name.startsWith('.') && entry.name !== 'node_modules') {
          files.push(...this.getAllSourceFiles(fullPath));
        } else if (entry.isFile() && (entry.name.endsWith('.js') || entry.name.endsWith('.jsx'))) {
          files.push(fullPath);
        }
      }
    } catch (error) {
      // Skip directories that can't be read
    }
    
    return files;
  }

  async testRuntimeConflictDetection() {
    this.log('=== Testing Runtime Conflict Detection ===');
    
    try {
      // Test 1: Check for Chart.js registration code patterns
      const srcFiles = this.getAllSourceFiles('src');
      let hasChartJsRegistration = false;
      let hasReactChartJsComponents = false;
      
      for (const file of srcFiles) {
        try {
          const content = fs.readFileSync(file, 'utf8');
          
          // Check for Chart.js registration patterns
          if (content.includes('ChartJS.register') || 
              content.includes('Chart.register') ||
              content.includes('CategoryScale') ||
              content.includes('LinearScale')) {
            hasChartJsRegistration = true;
          }
          
          // Check for react-chartjs-2 component usage
          if (content.includes('<Line') && content.includes('react-chartjs-2') ||
              content.includes('<Bar') && content.includes('react-chartjs-2')) {
            hasReactChartJsComponents = true;
          }
        } catch (error) {
          continue;
        }
      }
      
      if (!hasChartJsRegistration) {
        this.recordResult('No Chart.js registration code found', true);
      } else {
        this.recordResult('No Chart.js registration code found', false,
          'Found Chart.js registration code that can conflict with React 18');
      }
      
      if (!hasReactChartJsComponents) {
        this.recordResult('No react-chartjs-2 component usage found', true);
      } else {
        this.recordResult('No react-chartjs-2 component usage found', false,
          'Found react-chartjs-2 components that can cause useSyncExternalStore conflicts');
      }
      
      // Test 2: Check built bundles for problematic library combinations
      if (fs.existsSync(this.distPath)) {
        const assetsPath = path.join(this.distPath, 'assets');
        if (fs.existsSync(assetsPath)) {
          const jsFiles = fs.readdirSync(assetsPath).filter(file => file.endsWith('.js'));
          
          let hasChartJsInBundle = false;
          let hasReactQueryConflict = false;
          
          for (const file of jsFiles) {
            const content = fs.readFileSync(path.join(assetsPath, file), 'utf8');
            
            // Check for Chart.js in bundle (exclude Recharts which contains "Chart" in minified form)
            if (content.includes('Chart.js') || content.includes('react-chartjs') || content.includes('ChartJS')) {
              hasChartJsInBundle = true;
            }
            
            // Check for React Query + Chart.js combination (known conflict) - be more specific
            if (content.includes('useSyncExternalStore') && 
                (content.includes('Chart.js') || content.includes('react-chartjs') || content.includes('ChartJS'))) {
              hasReactQueryConflict = true;
            }
          }
          
          if (!hasChartJsInBundle) {
            this.recordResult('No Chart.js found in production bundles', true);
          } else {
            this.recordResult('No Chart.js found in production bundles', false,
              'Chart.js detected in production bundle - potential React 18 conflict');
          }
          
          if (!hasReactQueryConflict) {
            this.recordResult('No React Query + Chart.js conflicts detected', true);
          } else {
            this.recordResult('No React Query + Chart.js conflicts detected', false,
              'Detected potential useSyncExternalStore + Chart.js conflict');
          }
        }
      }
      
    } catch (error) {
      this.recordResult('Runtime conflict detection', false, error.message);
    }
  }

  async runAllTests() {
    this.log('🚀 Starting React build validation tests...');
    
    try {
      await this.testPackageJsonDependencies();
      await this.testViteConfiguration();
      await this.testSourceCodeImports();
      await this.testProductionBuild();
      await this.testBundleIntegrity();
      await this.testRuntimeErrors();
      await this.testRuntimeConflictDetection();
      
      this.log('=== Test Summary ===');
      this.log(`✅ Passed: ${this.testResults.passed}`);
      this.log(`❌ Failed: ${this.testResults.failed}`);
      
      if (this.testResults.errors.length > 0) {
        this.log('=== Errors Found ===');
        this.testResults.errors.forEach(error => {
          this.log(`❌ ${error}`, 'error');
        });
      }
      
      if (this.testResults.failed === 0) {
        this.log('🎉 All React build validation tests passed!', 'success');
        this.log('📦 Bundle is production-ready with no React conflicts!', 'success');
        process.exit(0);
      } else {
        this.log(`⚠️ ${this.testResults.failed} tests failed. React issues need attention.`, 'error');
        process.exit(1);
      }
      
    } catch (error) {
      this.log(`💥 React validation test suite failed: ${error.message}`, 'error');
      process.exit(1);
    }
  }
}

// Run tests if called directly
if (require.main === module) {
  const validator = new ReactBuildValidator();
  validator.runAllTests().catch(error => {
    console.error('❌ React validation test suite crashed:', error);
    process.exit(1);
  });
}

module.exports = ReactBuildValidator;