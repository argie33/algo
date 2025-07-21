/**
 * Package Inspector - Comprehensive dependency analysis
 * Identifies exactly which packages are causing useState undefined errors
 */

const PackageInspector = {
  inspections: [],
  
  inspectCurrentPackageState() {
    const inspection = {
      timestamp: Date.now(),
      location: window.location.href,
      analysis: {}
    };
    
    console.log('🔍 PACKAGE INSPECTOR - Starting comprehensive analysis...');
    
    // 1. Check what's actually installed vs what we expect
    inspection.analysis.packageExpectations = this.analyzePackageExpectations();
    
    // 2. Check React Query specifically
    inspection.analysis.reactQuery = this.analyzeReactQuery();
    
    // 3. Check for conflicting versions
    inspection.analysis.versionConflicts = this.detectVersionConflicts();
    
    // 4. Check module resolution
    inspection.analysis.moduleResolution = this.analyzeModuleResolution();
    
    // 5. Check bundler state
    inspection.analysis.bundlerState = this.analyzeBundlerState();
    
    // 6. Check for hidden dependencies
    inspection.analysis.hiddenDependencies = this.findHiddenDependencies();
    
    this.inspections.push(inspection);
    
    console.log('📊 PACKAGE INSPECTION COMPLETE:', inspection);
    
    // Auto-generate recommendations
    const recommendations = this.generateRecommendations(inspection);
    console.log('💡 PACKAGE RECOMMENDATIONS:', recommendations);
    
    return {
      inspection,
      recommendations
    };
  },
  
  analyzePackageExpectations() {
    console.log('🔍 Analyzing package expectations vs reality...');
    
    return {
      expectedPackages: {
        'react': '^18.3.1',
        'react-dom': '^18.3.1',
        '../hooks/useSimpleFetch.js': '^4.35.3',
        'use-sync-external-store': 'REMOVED (should not be present)'
      },
      actuallyLoaded: this.getActuallyLoadedPackages(),
      discrepancies: this.findPackageDiscrepancies()
    };
  },
  
  getActuallyLoadedPackages() {
    const loaded = {};
    
    // Check if we can access package info through different means
    try {
      // Method 1: Check script tags
      const scripts = Array.from(document.scripts);
      scripts.forEach(script => {
        if (script.src) {
          // Extract package info from CDN URLs
          const packageMatch = script.src.match(/\/([^\/]+)@([^\/]+)\//);
          if (packageMatch) {
            loaded[packageMatch[1]] = {
              version: packageMatch[2],
              source: 'cdn-script',
              url: script.src
            };
          }
          
          // Check for specific packages
          if (script.src.includes('react')) {
            loaded.react = loaded.react || { source: 'script', url: script.src };
          }
          if (script.src.includes('use-sync-external-store')) {
            loaded['use-sync-external-store'] = { source: 'script', url: script.src, WARNING: 'Should not be present!' };
          }
        }
      });
      
      // Method 2: Check webpack/vite chunks
      if (window.__webpack_require__) {
        const cache = window.__webpack_require__.cache || {};
        Object.keys(cache).forEach(key => {
          if (key.includes('react')) {
            loaded[`webpack-${key}`] = { source: 'webpack-cache' };
          }
        });
      }
      
      // Method 3: Check for global variables
      if (window.React) {
        loaded.reactGlobal = {
          version: window.React.version,
          source: 'global-variable',
          hooks: Object.keys(window.React).filter(k => k.startsWith('use'))
        };
      }
      
    } catch (error) {
      loaded.error = error.message;
    }
    
    return loaded;
  },
  
  findPackageDiscrepancies() {
    const discrepancies = [];
    
    // Check if use-sync-external-store is somehow still present
    try {
      const useSyncStore = require('use-sync-external-store');
      discrepancies.push({
        severity: 'CRITICAL',
        package: 'use-sync-external-store',
        issue: 'Package still available via require() despite being removed from package.json',
        evidence: useSyncStore
      });
    } catch (e) {
      // Good - it should not be available
    }
    
    // Check React version consistency
    if (window.React && window.React.version) {
      const expectedVersion = '18.3.1';
      if (!window.React.version.startsWith('18.')) {
        discrepancies.push({
          severity: 'HIGH',
          package: 'react',
          issue: `React version mismatch. Expected 18.x, got ${window.React.version}`,
          evidence: window.React.version
        });
      }
    }
    
    return discrepancies;
  },
  
  analyzeReactQuery() {
    console.log('🔍 Analyzing React Query specifically...');
    
    const analysis = {
      available: false,
      version: null,
      dependencies: [],
      usesUseSyncExternalStore: false,
      potentialIssues: []
    };
    
    try {
      // Check if React Query is available
      const reactQuery = require('../hooks/useSimpleFetch.js');
      analysis.available = true;
      analysis.version = reactQuery.version || 'unknown';
      
      // Check if React Query internals use useSyncExternalStore
      const queryClient = reactQuery.QueryClient;
      if (queryClient) {
        const clientString = queryClient.toString();
        analysis.usesUseSyncExternalStore = clientString.includes('useSyncExternalStore');
        
        if (analysis.usesUseSyncExternalStore) {
          analysis.potentialIssues.push({
            severity: 'HIGH',
            issue: 'React Query uses useSyncExternalStore internally',
            recommendation: 'Ensure React 18 is properly configured with built-in useSyncExternalStore'
          });
        }
      }
      
      // Check React Query dependencies
      if (reactQuery.__esModule) {
        analysis.dependencies = Object.keys(reactQuery);
      }
      
    } catch (error) {
      analysis.error = error.message;
      analysis.potentialIssues.push({
        severity: 'MEDIUM',
        issue: 'Could not analyze React Query',
        error: error.message
      });
    }
    
    return analysis;
  },
  
  detectVersionConflicts() {
    console.log('🔍 Detecting version conflicts...');
    
    const conflicts = [];
    
    // Check for multiple React versions
    const reactVersions = this.findAllReactVersions();
    if (reactVersions.length > 1) {
      conflicts.push({
        package: 'react',
        conflict: 'Multiple React versions detected',
        versions: reactVersions,
        severity: 'CRITICAL'
      });
    }
    
    // Check for React DOM mismatches
    const reactDomVersions = this.findAllReactDomVersions();
    if (reactDomVersions.length > 1) {
      conflicts.push({
        package: 'react-dom',
        conflict: 'Multiple React DOM versions detected',
        versions: reactDomVersions,
        severity: 'CRITICAL'
      });
    }
    
    return conflicts;
  },
  
  findAllReactVersions() {
    const versions = [];
    
    // Check global React
    if (window.React?.version) {
      versions.push({
        source: 'window.React',
        version: window.React.version
      });
    }
    
    // Check require cache
    try {
      const reactModule = require('react');
      if (reactModule.version) {
        versions.push({
          source: 'require(react)',
          version: reactModule.version
        });
      }
    } catch (e) {
      // Ignore
    }
    
    return versions;
  },
  
  findAllReactDomVersions() {
    const versions = [];
    
    // Check require cache
    try {
      const reactDomModule = require('react-dom');
      if (reactDomModule.version) {
        versions.push({
          source: 'require(react-dom)',
          version: reactDomModule.version
        });
      }
    } catch (e) {
      // Ignore
    }
    
    return versions;
  },
  
  analyzeModuleResolution() {
    console.log('🔍 Analyzing module resolution...');
    
    const resolution = {
      strategy: 'unknown',
      cache: {},
      conflicts: []
    };
    
    // Detect bundler/module system
    if (typeof __webpack_require__ !== 'undefined') {
      resolution.strategy = 'webpack';
      resolution.cache = Object.keys(window.__webpack_require__.cache || {});
    } else if (typeof __vite__ !== 'undefined') {
      resolution.strategy = 'vite';
    } else if (typeof require !== 'undefined') {
      resolution.strategy = 'commonjs';
      resolution.cache = Object.keys(require.cache || {});
    } else {
      resolution.strategy = 'esm';
    }
    
    return resolution;
  },
  
  analyzeBundlerState() {
    console.log('🔍 Analyzing bundler state...');
    
    const state = {
      bundler: 'unknown',
      chunks: [],
      modules: [],
      issues: []
    };
    
    // Webpack analysis
    if (typeof __webpack_require__ !== 'undefined') {
      state.bundler = 'webpack';
      
      if (window.__webpack_require__.cache) {
        state.modules = Object.keys(window.__webpack_require__.cache);
        
        // Look for React-related modules
        const reactModules = state.modules.filter(m => 
          m.includes('react') || 
          m.includes('use-sync-external-store') ||
          m.includes('tanstack')
        );
        
        if (reactModules.length > 0) {
          state.chunks = reactModules;
        }
      }
    }
    
    // Vite analysis
    if (typeof __vite__ !== 'undefined') {
      state.bundler = 'vite';
      // Vite-specific analysis would go here
    }
    
    return state;
  },
  
  findHiddenDependencies() {
    console.log('🔍 Finding hidden dependencies...');
    
    const hidden = [];
    
    // Check for dependencies that might be bundled but not obvious
    const suspiciousGlobals = [
      'useSyncExternalStore',
      '__REACT_DEVTOOLS_GLOBAL_HOOK__',
      '__webpack_require__',
      '__vite__'
    ];
    
    suspiciousGlobals.forEach(global => {
      if (window[global]) {
        hidden.push({
          name: global,
          type: typeof window[global],
          source: 'window global'
        });
      }
    });
    
    return hidden;
  },
  
  generateRecommendations(inspection) {
    const recommendations = [];
    
    // Check for critical issues
    inspection.analysis.versionConflicts.forEach(conflict => {
      if (conflict.severity === 'CRITICAL') {
        recommendations.push({
          priority: 'IMMEDIATE',
          action: `Resolve ${conflict.package} version conflict`,
          details: conflict,
          fix: `Use package.json resolutions to force single version of ${conflict.package}`
        });
      }
    });
    
    // Check for React Query issues
    if (inspection.analysis.reactQuery.potentialIssues.length > 0) {
      recommendations.push({
        priority: 'HIGH',
        action: 'Fix React Query useSyncExternalStore compatibility',
        details: inspection.analysis.reactQuery.potentialIssues,
        fix: 'Ensure React Query uses React 18 built-in useSyncExternalStore'
      });
    }
    
    // Check for package expectation mismatches
    const discrepancies = inspection.analysis.packageExpectations.discrepancies;
    if (discrepancies.length > 0) {
      recommendations.push({
        priority: 'HIGH',
        action: 'Fix package expectation mismatches',
        details: discrepancies,
        fix: 'Update package.json and run clean install'
      });
    }
    
    return recommendations;
  },
  
  // Export inspection data
  exportInspectionReport() {
    const report = {
      timestamp: Date.now(),
      url: window.location.href,
      userAgent: navigator.userAgent,
      inspections: this.inspections,
      summary: this.generateSummary()
    };
    
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `package-inspection-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
    
    return report;
  },
  
  generateSummary() {
    const latestInspection = this.inspections[this.inspections.length - 1];
    if (!latestInspection) return null;
    
    return {
      totalIssues: latestInspection.analysis.versionConflicts.length + 
                   latestInspection.analysis.packageExpectations.discrepancies.length,
      criticalIssues: latestInspection.analysis.versionConflicts.filter(c => c.severity === 'CRITICAL').length,
      reactQueryIssues: latestInspection.analysis.reactQuery.potentialIssues.length,
      bundler: latestInspection.analysis.bundlerState.bundler,
      recommendations: latestInspection.analysis.versionConflicts.length > 0 ? 'IMMEDIATE ACTION REQUIRED' : 'OK'
    };
  }
};

// Auto-run inspection on load
if (typeof window !== 'undefined') {
  window.packageInspector = PackageInspector;
  
  // Run initial inspection after a delay
  setTimeout(() => {
    console.log('🚀 RUNNING PACKAGE INSPECTION...');
    PackageInspector.inspectCurrentPackageState();
  }, 2000);
}

export default PackageInspector;