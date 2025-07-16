#!/usr/bin/env node
/**
 * Comprehensive API Health Check Script
 * Tests all endpoints and generates detailed health report
 */

const HealthChecker = require('./utils/healthChecker');

async function runHealthCheck() {
  console.log('🚀 Starting comprehensive API health check...');
  console.log('📍 Testing API at: https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev');
  console.log('🕐 Started at:', new Date().toISOString());
  console.log();
  
  const checker = new HealthChecker();
  
  try {
    // Run comprehensive health check
    const results = await checker.checkAllEndpoints();
    
    // Generate and display report
    const report = checker.generateReport();
    console.log(report);
    
    // Display detailed statistics
    console.log('📋 DETAILED STATISTICS:');
    console.log('─'.repeat(80));
    console.log(`Total Endpoints Tested: ${results.summary.total_endpoints}`);
    console.log(`Healthy: ${results.summary.healthy} (${Math.round(results.summary.healthy/results.summary.total_endpoints*100)}%)`);
    console.log(`Unhealthy: ${results.summary.unhealthy} (${Math.round(results.summary.unhealthy/results.summary.total_endpoints*100)}%)`);
    console.log(`Errors: ${results.summary.errors} (${Math.round(results.summary.errors/results.summary.total_endpoints*100)}%)`);
    console.log(`Overall Success Rate: ${results.summary.success_rate}%`);
    console.log(`Total Check Time: ${results.summary.total_check_time}ms`);
    console.log(`Average Response Time: ${results.summary.average_response_time}ms`);
    console.log();
    
    // Show improvement recommendations
    const categorized = checker.getCategorizedResults();
    
    if (categorized.categories.errors.length > 0 || categorized.categories.unhealthy.length > 0) {
      console.log('🔧 IMPROVEMENT RECOMMENDATIONS:');
      console.log('─'.repeat(80));
      
      if (categorized.categories.timeout.length > 0) {
        console.log('⏰ Timeout Issues:');
        categorized.categories.timeout.forEach(ep => {
          console.log(`   • ${ep.name}: Consider optimizing database queries or increasing timeout`);
        });
      }
      
      if (categorized.categories.errors.length > 0) {
        console.log('❌ Error Issues:');
        categorized.categories.errors.forEach(ep => {
          console.log(`   • ${ep.name}: ${ep.error} - Check route loading and dependencies`);
        });
      }
      
      if (categorized.categories.unhealthy.filter(ep => ep.statusCode !== 401).length > 0) {
        console.log('⚠️  Unhealthy Endpoints:');
        categorized.categories.unhealthy.filter(ep => ep.statusCode !== 401).forEach(ep => {
          console.log(`   • ${ep.name}: HTTP ${ep.statusCode} - Check route implementation`);
        });
      }
      
      console.log();
    }
    
    // Performance analysis
    const fastEndpoints = results.results.filter(r => r.responseTime < 500 && r.status === 'healthy');
    const slowEndpoints = results.results.filter(r => r.responseTime > 2000);
    
    if (fastEndpoints.length > 0) {
      console.log('⚡ FASTEST ENDPOINTS (< 500ms):');
      console.log('─'.repeat(80));
      fastEndpoints
        .sort((a, b) => a.responseTime - b.responseTime)
        .slice(0, 5)
        .forEach(ep => {
          console.log(`   ${ep.name}: ${ep.responseTime}ms`);
        });
      console.log();
    }
    
    if (slowEndpoints.length > 0) {
      console.log('🐌 SLOWEST ENDPOINTS (> 2000ms):');
      console.log('─'.repeat(80));
      slowEndpoints
        .sort((a, b) => b.responseTime - a.responseTime)
        .forEach(ep => {
          console.log(`   ${ep.name}: ${ep.responseTime}ms - Consider optimization`);
        });
      console.log();
    }
    
    // Exit with appropriate code
    const hasErrors = results.summary.errors > 0 || 
                     categorized.categories.unhealthy.filter(ep => ep.statusCode !== 401).length > 0;
    
    if (hasErrors) {
      console.log('❌ Health check completed with issues. See recommendations above.');
      process.exit(1);
    } else {
      console.log('✅ All critical endpoints are healthy!');
      process.exit(0);
    }
    
  } catch (error) {
    console.error('❌ Health check failed:', error.message);
    console.error('Stack:', error.stack);
    process.exit(1);
  }
}

// Run if called directly
if (require.main === module) {
  runHealthCheck().catch(error => {
    console.error('Fatal error:', error);
    process.exit(1);
  });
}

module.exports = { runHealthCheck, HealthChecker };