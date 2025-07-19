/**
 * Global E2E Test Teardown
 * Cleanup and reporting for comprehensive testing
 * Ensures no test data pollution in real systems
 */

const fs = require('fs').promises;
const path = require('path');

async function globalTeardown(config) {
  console.log('🧹 Starting comprehensive E2E test environment teardown...');
  
  const teardownResults = {
    timestamp: new Date().toISOString(),
    cleanup: {},
    reports: {},
    performance: {},
    summary: {}
  };

  // Step 1: Test data cleanup
  console.log('🗑️ Step 1: Cleaning up test data...');
  try {
    // Clean up test users and data via API
    const fetch = (await import('node-fetch')).default;
    const apiUrl = process.env.E2E_API_URL;
    
    // List of test data patterns to clean
    const testDataPatterns = [
      'e2e-test-user',
      'E2E Test Portfolio',
      'E2E Tech Watchlist',
      'E2E Financial Watchlist',
      'concurrent-user-',
      'test-position-',
      'automated-test-'
    ];
    
    // Attempt cleanup (may fail if auth is required)
    try {
      const cleanupResponse = await fetch(`${apiUrl}/api/admin/cleanup`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'X-Test-Cleanup': 'true'
        },
        body: JSON.stringify({ patterns: testDataPatterns }),
        timeout: 30000
      });
      
      teardownResults.cleanup.api = {
        status: cleanupResponse.status,
        success: cleanupResponse.status === 200,
        patterns: testDataPatterns.length
      };
      
      if (cleanupResponse.status === 200) {
        console.log('✅ API test data cleanup completed');
      } else {
        console.warn(`⚠️ API cleanup returned status: ${cleanupResponse.status}`);
      }
    } catch (cleanupError) {
      console.warn('⚠️ API cleanup not available:', cleanupError.message);
      teardownResults.cleanup.api = { success: false, error: cleanupError.message };
    }
    
    // Clean up local test data files
    try {
      const testDataDir = path.join(__dirname, 'test-data');
      const files = await fs.readdir(testDataDir).catch(() => []);
      
      for (const file of files) {
        await fs.unlink(path.join(testDataDir, file));
      }
      
      await fs.rmdir(testDataDir).catch(() => {});
      
      teardownResults.cleanup.localFiles = {
        success: true,
        filesRemoved: files.length
      };
      
      console.log(`✅ Local test data cleanup completed (${files.length} files)`);
    } catch (fileError) {
      console.warn('⚠️ Local file cleanup failed:', fileError.message);
      teardownResults.cleanup.localFiles = { success: false, error: fileError.message };
    }
    
  } catch (error) {
    console.error('❌ Test data cleanup failed:', error);
    teardownResults.cleanup.error = error.message;
  }

  // Step 2: Generate comprehensive test report
  console.log('📊 Step 2: Generating test reports...');
  try {
    const reportsDir = path.join(__dirname, 'e2e-reports');
    
    // Read setup results
    let setupResults = {};
    try {
      const setupData = await fs.readFile(path.join(reportsDir, 'setup-results.json'), 'utf8');
      setupResults = JSON.parse(setupData);
    } catch (setupError) {
      console.warn('⚠️ Could not read setup results');
    }
    
    // Read Playwright test results
    let playwrightResults = {};
    try {
      const playwrightData = await fs.readFile(path.join(reportsDir, 'results.json'), 'utf8');
      playwrightResults = JSON.parse(playwrightData);
    } catch (playwrightError) {
      console.warn('⚠️ Could not read Playwright results');
    }
    
    // Generate comprehensive summary
    const comprehensiveReport = {
      timestamp: new Date().toISOString(),
      testRun: {
        duration: setupResults.timestamp ? 
          Date.now() - new Date(setupResults.timestamp).getTime() : 
          'unknown',
        environment: setupResults.environment || {},
        services: setupResults.services || {}
      },
      testResults: {
        playwright: playwrightResults,
        setup: setupResults,
        teardown: teardownResults
      },
      performance: {
        baseline: setupResults.performance || {},
        // Additional performance metrics would be collected during tests
      },
      coverage: {
        // Test coverage analysis
        functionalAreas: [
          'authentication',
          'portfolio-management', 
          'market-data',
          'trading-simulation',
          'error-recovery',
          'performance',
          'security'
        ],
        completionStatus: 'calculated-during-tests'
      },
      recommendations: []
    };
    
    // Add recommendations based on test results
    if (setupResults.services?.api?.healthy === false) {
      comprehensiveReport.recommendations.push({
        priority: 'high',
        category: 'infrastructure',
        issue: 'API service health issues detected',
        recommendation: 'Investigate API service stability and error handling'
      });
    }
    
    if (setupResults.services?.database?.healthy === false) {
      comprehensiveReport.recommendations.push({
        priority: 'critical',
        category: 'infrastructure', 
        issue: 'Database connectivity issues detected',
        recommendation: 'Review database connection pooling and circuit breaker configuration'
      });
    }
    
    if (setupResults.performance?.apiResponseTime > 5000) {
      comprehensiveReport.recommendations.push({
        priority: 'medium',
        category: 'performance',
        issue: 'API response times exceed 5 seconds',
        recommendation: 'Optimize API endpoints and implement caching strategies'
      });
    }
    
    // Save comprehensive report
    await fs.writeFile(
      path.join(reportsDir, 'comprehensive-report.json'),
      JSON.stringify(comprehensiveReport, null, 2)
    );
    
    // Generate human-readable summary
    const summaryText = generateTextSummary(comprehensiveReport);
    await fs.writeFile(
      path.join(reportsDir, 'test-summary.txt'),
      summaryText
    );
    
    teardownResults.reports = {
      generated: true,
      files: ['comprehensive-report.json', 'test-summary.txt'],
      recommendations: comprehensiveReport.recommendations.length
    };
    
    console.log('✅ Test reports generated successfully');
    
  } catch (error) {
    console.error('❌ Test report generation failed:', error);
    teardownResults.reports = { generated: false, error: error.message };
  }

  // Step 3: Performance analysis
  console.log('⚡ Step 3: Analyzing performance metrics...');
  try {
    // Final performance check
    const fetch = (await import('node-fetch')).default;
    const apiUrl = process.env.E2E_API_URL;
    
    const finalStart = Date.now();
    const finalResponse = await fetch(`${apiUrl}/api/health?quick=true`, {
      timeout: 30000
    });
    const finalResponseTime = Date.now() - finalStart;
    
    teardownResults.performance = {
      finalApiResponseTime: finalResponseTime,
      timestamp: new Date().toISOString(),
      healthStatus: finalResponse.status
    };
    
    console.log(`✅ Final performance check: ${finalResponseTime}ms`);
    
  } catch (error) {
    console.warn('⚠️ Final performance check failed:', error.message);
    teardownResults.performance = { error: error.message };
  }

  // Step 4: Summary and next steps
  console.log('📋 Step 4: Generating final summary...');
  teardownResults.summary = {
    cleanup: teardownResults.cleanup.api?.success && teardownResults.cleanup.localFiles?.success,
    reports: teardownResults.reports.generated,
    performance: !!teardownResults.performance.finalApiResponseTime,
    recommendations: teardownResults.reports.recommendations || 0
  };

  // Save teardown results
  try {
    const reportsDir = path.join(__dirname, 'e2e-reports');
    await fs.writeFile(
      path.join(reportsDir, 'teardown-results.json'),
      JSON.stringify(teardownResults, null, 2)
    );
  } catch (error) {
    console.warn('⚠️ Could not save teardown results:', error.message);
  }

  // Final summary
  console.log('\n📋 E2E Test Environment Teardown Summary:');
  console.log(`Cleanup: ${teardownResults.summary.cleanup ? '✅' : '⚠️'}`);
  console.log(`Reports: ${teardownResults.summary.reports ? '✅' : '❌'}`);
  console.log(`Performance: ${teardownResults.summary.performance ? '✅' : '⚠️'}`);
  console.log(`Recommendations: ${teardownResults.summary.recommendations || 0} issues identified`);
  
  console.log('\n🎯 E2E testing completed!');
  console.log('📊 Check e2e-reports/ directory for detailed results');
  console.log('🔧 Review recommendations for system improvements\n');
  
  return teardownResults;
}

function generateTextSummary(report) {
  return `
E2E Test Summary Report
Generated: ${report.timestamp}
========================

Test Environment:
- Base URL: ${report.testRun.environment.baseURL || 'N/A'}
- API URL: ${report.testRun.environment.apiURL || 'N/A'}
- Duration: ${typeof report.testRun.duration === 'number' ? 
    `${Math.round(report.testRun.duration / 1000)} seconds` : 
    report.testRun.duration}

Service Health:
- API: ${report.testRun.services.api?.healthy ? 'Healthy' : 'Issues Detected'}
- Database: ${report.testRun.services.database?.healthy ? 'Healthy' : 'Issues Detected'}
- WebSocket: ${report.testRun.services.websocket?.healthy ? 'Healthy' : 'Issues Detected'}

Performance Baseline:
- Frontend Load: ${report.performance.baseline?.frontendLoadTime || 'N/A'}ms
- API Response: ${report.performance.baseline?.apiResponseTime || 'N/A'}ms

Functional Coverage:
${report.coverage.functionalAreas.map(area => `- ${area}: ${report.coverage.completionStatus}`).join('\n')}

Recommendations (${report.recommendations.length}):
${report.recommendations.map(rec => 
  `- [${rec.priority.toUpperCase()}] ${rec.category}: ${rec.issue}\n  → ${rec.recommendation}`
).join('\n')}

Next Steps:
1. Review detailed results in comprehensive-report.json
2. Address high-priority recommendations
3. Run tests regularly for continuous validation
4. Monitor performance trends over time
`;
}

module.exports = globalTeardown;