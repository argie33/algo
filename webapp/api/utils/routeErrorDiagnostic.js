/**
 * Route Error Diagnostic Utility
 * Helps identify specific causes of 500 errors in API routes
 */

const path = require('path');
const fs = require('fs');

class RouteErrorDiagnostic {
  constructor(routesDir = './routes') {
    this.routesDir = routesDir;
    this.diagnosticResults = new Map();
  }

  /**
   * Analyze a route file for potential issues
   */
  analyzeRouteFile(routeName) {
    const routePath = path.join(this.routesDir, `${routeName}.js`);
    
    if (!fs.existsSync(routePath)) {
      return {
        exists: false,
        error: `Route file ${routePath} not found`
      };
    }

    try {
      const content = fs.readFileSync(routePath, 'utf8');
      
      const analysis = {
        exists: true,
        fileSize: content.length,
        issues: [],
        dependencies: [],
        hasHealthEndpoint: false,
        hasErrorHandling: false,
        hasAsyncRoutes: false,
        hasResponseFormatter: false,
        imports: []
      };

      // Check for common import patterns
      const importLines = content.match(/^const\s+.*=\s+require\(.*\);?$/gm) || [];
      analysis.imports = importLines;
      
      // Check dependencies
      const dependencies = content.match(/require\(['"`]([^'"`]+)['"`]\)/g) || [];
      analysis.dependencies = dependencies.map(dep => dep.match(/require\(['"`]([^'"`]+)['"`]\)/)[1]);

      // Check for responseFormatter usage
      if (content.includes('responseFormatter') || content.includes('success') || content.includes('error')) {
        analysis.hasResponseFormatter = true;
      }

      // Check for health endpoint
      if (content.includes("'/health'") || content.includes('/health')) {
        analysis.hasHealthEndpoint = true;
      }

      // Check for error handling
      if (content.includes('try') && content.includes('catch')) {
        analysis.hasErrorHandling = true;
      }

      // Check for async routes
      if (content.includes('async (req, res)') || content.includes('await ')) {
        analysis.hasAsyncRoutes = true;
      }

      // Check for potential issues
      
      // Issue 1: Old responseFormatter import pattern
      if (content.includes('responseFormatter = require(')) {
        analysis.issues.push({
          type: 'import_error',
          severity: 'high',
          issue: 'Uses old responseFormatter import pattern',
          line: this.findLineNumber(content, 'responseFormatter = require('),
          fix: 'Change to destructured import: const { success, error } = require(...)'
        });
      }

      // Issue 2: Missing express import
      if (!content.includes("require('express')")) {
        analysis.issues.push({
          type: 'missing_dependency',
          severity: 'critical',
          issue: 'Missing express import',
          fix: 'Add: const express = require(\'express\');'
        });
      }

      // Issue 3: Undefined responseFormatter methods
      if (content.includes('responseFormatter.success') || content.includes('responseFormatter.error')) {
        analysis.issues.push({
          type: 'undefined_method',
          severity: 'high',
          issue: 'Uses responseFormatter.success/error without proper import',
          fix: 'Use destructured import and call success()/error() directly'
        });
      }

      // Issue 4: Missing router export
      if (!content.includes('module.exports = router')) {
        analysis.issues.push({
          type: 'export_error',
          severity: 'critical',
          issue: 'Missing module.exports = router',
          fix: 'Add: module.exports = router; at end of file'
        });
      }

      // Issue 5: Database import without error handling
      if (content.includes("require('../utils/database')") && !analysis.hasErrorHandling) {
        analysis.issues.push({
          type: 'error_handling',
          severity: 'medium',
          issue: 'Database usage without error handling',
          fix: 'Wrap database calls in try-catch blocks'
        });
      }

      // Issue 6: Async routes without error handling
      if (analysis.hasAsyncRoutes && !analysis.hasErrorHandling) {
        analysis.issues.push({
          type: 'async_error',
          severity: 'high',
          issue: 'Async routes without proper error handling',
          fix: 'Add try-catch blocks around async operations'
        });
      }

      return analysis;

    } catch (error) {
      return {
        exists: true,
        error: `Failed to analyze route: ${error.message}`,
        exception: error
      };
    }
  }

  /**
   * Find line number of a string in content
   */
  findLineNumber(content, searchString) {
    const lines = content.split('\n');
    for (let i = 0; i < lines.length; i++) {
      if (lines[i].includes(searchString)) {
        return i + 1;
      }
    }
    return null;
  }

  /**
   * Test if a route can be loaded without errors
   */
  testRouteLoading(routeName) {
    const routePath = path.join(this.routesDir, `${routeName}.js`);
    
    try {
      // Clear require cache to force fresh load
      delete require.cache[require.resolve(routePath)];
      
      const route = require(routePath);
      
      return {
        loadable: true,
        hasRouter: typeof route === 'function' || (route && typeof route.use === 'function'),
        type: typeof route,
        methods: route && typeof route === 'object' ? Object.getOwnPropertyNames(route) : []
      };
      
    } catch (error) {
      return {
        loadable: false,
        error: error.message,
        stack: error.stack,
        errorType: error.constructor.name
      };
    }
  }

  /**
   * Analyze all routes in the directory
   */
  analyzeAllRoutes() {
    const results = {
      timestamp: new Date().toISOString(),
      totalRoutes: 0,
      healthyRoutes: 0,
      routesWithIssues: 0,
      criticalIssues: 0,
      routes: {}
    };

    try {
      const files = fs.readdirSync(this.routesDir);
      const routeFiles = files.filter(file => file.endsWith('.js'));

      results.totalRoutes = routeFiles.length;

      for (const file of routeFiles) {
        const routeName = file.replace('.js', '');
        
        // Analyze file content
        const fileAnalysis = this.analyzeRouteFile(routeName);
        
        // Test loading
        const loadTest = this.testRouteLoading(routeName);
        
        const routeResult = {
          fileName: file,
          analysis: fileAnalysis,
          loadTest: loadTest,
          status: 'unknown'
        };

        // Determine overall status
        if (!fileAnalysis.exists) {
          routeResult.status = 'missing';
        } else if (fileAnalysis.error) {
          routeResult.status = 'analysis_failed';
        } else if (!loadTest.loadable) {
          routeResult.status = 'load_failed';
        } else if (fileAnalysis.issues.some(issue => issue.severity === 'critical')) {
          routeResult.status = 'critical_issues';
          results.criticalIssues++;
        } else if (fileAnalysis.issues.length > 0) {
          routeResult.status = 'has_issues';
          results.routesWithIssues++;
        } else {
          routeResult.status = 'healthy';
          results.healthyRoutes++;
        }

        results.routes[routeName] = routeResult;
      }

      return results;

    } catch (error) {
      return {
        error: `Failed to analyze routes directory: ${error.message}`,
        timestamp: new Date().toISOString()
      };
    }
  }

  /**
   * Generate detailed diagnostic report
   */
  generateDiagnosticReport() {
    const analysis = this.analyzeAllRoutes();
    
    if (analysis.error) {
      return `❌ Diagnostic failed: ${analysis.error}`;
    }

    let report = `
🔍 ROUTE ERROR DIAGNOSTIC REPORT
===============================
📊 Routes Analyzed: ${analysis.totalRoutes}
✅ Healthy: ${analysis.healthyRoutes}
⚠️  With Issues: ${analysis.routesWithIssues}
🚨 Critical Issues: ${analysis.criticalIssues}
🕐 Analysis Time: ${analysis.timestamp}

`;

    // Group routes by status
    const statusGroups = {};
    Object.entries(analysis.routes).forEach(([name, route]) => {
      if (!statusGroups[route.status]) {
        statusGroups[route.status] = [];
      }
      statusGroups[route.status].push({ name, ...route });
    });

    // Report critical issues first
    if (statusGroups.critical_issues) {
      report += `🚨 CRITICAL ISSUES (${statusGroups.critical_issues.length}):\n`;
      report += '─'.repeat(80) + '\n';
      statusGroups.critical_issues.forEach(route => {
        report += `❌ ${route.name}:\n`;
        route.analysis.issues.filter(i => i.severity === 'critical').forEach(issue => {
          report += `   • ${issue.issue}\n`;
          report += `     Fix: ${issue.fix}\n`;
        });
        if (route.loadTest && !route.loadTest.loadable) {
          report += `   • Load Error: ${route.loadTest.error}\n`;
        }
        report += '\n';
      });
    }

    // Report load failures
    if (statusGroups.load_failed) {
      report += `💥 LOAD FAILURES (${statusGroups.load_failed.length}):\n`;
      report += '─'.repeat(80) + '\n';
      statusGroups.load_failed.forEach(route => {
        report += `❌ ${route.name}: ${route.loadTest.error}\n`;
        if (route.loadTest.errorType) {
          report += `   Type: ${route.loadTest.errorType}\n`;
        }
      });
      report += '\n';
    }

    // Report routes with issues
    if (statusGroups.has_issues) {
      report += `⚠️  ROUTES WITH ISSUES (${statusGroups.has_issues.length}):\n`;
      report += '─'.repeat(80) + '\n';
      statusGroups.has_issues.forEach(route => {
        report += `⚠️  ${route.name}:\n`;
        route.analysis.issues.forEach(issue => {
          report += `   • ${issue.issue} (${issue.severity})\n`;
        });
      });
      report += '\n';
    }

    // Report healthy routes
    if (statusGroups.healthy) {
      report += `✅ HEALTHY ROUTES (${statusGroups.healthy.length}):\n`;
      report += '─'.repeat(80) + '\n';
      statusGroups.healthy.forEach(route => {
        report += `✅ ${route.name}\n`;
      });
      report += '\n';
    }

    // Summary recommendations
    report += `🔧 RECOMMENDED ACTIONS:\n`;
    report += '─'.repeat(80) + '\n';
    
    if (analysis.criticalIssues > 0) {
      report += `1. Fix ${analysis.criticalIssues} critical issues first\n`;
    }
    
    if (statusGroups.load_failed) {
      report += `2. Resolve ${statusGroups.load_failed.length} load failures\n`;
    }
    
    if (analysis.routesWithIssues > 0) {
      report += `3. Address ${analysis.routesWithIssues} routes with issues\n`;
    }
    
    const successRate = Math.round((analysis.healthyRoutes / analysis.totalRoutes) * 100);
    report += `4. Current health: ${successRate}% - Target: 90%+\n`;

    return report;
  }

  /**
   * Get routes that need immediate attention
   */
  getRoutesPriority() {
    const analysis = this.analyzeAllRoutes();
    
    return {
      critical: Object.entries(analysis.routes)
        .filter(([name, route]) => route.status === 'critical_issues' || route.status === 'load_failed')
        .map(([name, route]) => ({ name, ...route })),
      
      medium: Object.entries(analysis.routes)
        .filter(([name, route]) => route.status === 'has_issues')
        .map(([name, route]) => ({ name, ...route })),
        
      healthy: Object.entries(analysis.routes)
        .filter(([name, route]) => route.status === 'healthy')
        .map(([name, route]) => ({ name, ...route }))
    };
  }
}

module.exports = RouteErrorDiagnostic;