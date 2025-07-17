#!/usr/bin/env node
/**
 * Route Diagnostic Script
 * Analyzes all routes for potential issues causing 500 errors
 */

const RouteErrorDiagnostic = require('./utils/routeErrorDiagnostic');

async function runDiagnostic() {
  console.log('🔍 Starting comprehensive route diagnostic...');
  console.log('📂 Analyzing routes in ./routes directory');
  console.log('🕐 Started at:', new Date().toISOString());
  console.log();

  const diagnostic = new RouteErrorDiagnostic('./routes');
  
  try {
    // Generate full diagnostic report
    const report = diagnostic.generateDiagnosticReport();
    console.log(report);
    
    // Get prioritized list of routes needing attention
    const priorities = diagnostic.getRoutesPriority();
    
    console.log('🎯 PRIORITY QUEUE FOR FIXES:');
    console.log('═'.repeat(80));
    
    if (priorities.critical.length > 0) {
      console.log(`\n🚨 HIGH PRIORITY (${priorities.critical.length} routes):`);
      priorities.critical.forEach((route, index) => {
        console.log(`${index + 1}. ${route.name} - ${route.status}`);
        if (route.loadTest && !route.loadTest.loadable) {
          console.log(`   Error: ${route.loadTest.error}`);
        }
        if (route.analysis.issues) {
          route.analysis.issues.filter(i => i.severity === 'critical').forEach(issue => {
            console.log(`   Issue: ${issue.issue}`);
          });
        }
      });
    }
    
    if (priorities.medium.length > 0) {
      console.log(`\n⚠️  MEDIUM PRIORITY (${priorities.medium.length} routes):`);
      priorities.medium.slice(0, 10).forEach((route, index) => {
        console.log(`${index + 1}. ${route.name} - ${route.analysis.issues.length} issues`);
      });
      if (priorities.medium.length > 10) {
        console.log(`   ... and ${priorities.medium.length - 10} more`);
      }
    }
    
    console.log(`\n✅ HEALTHY ROUTES (${priorities.healthy.length}):`);
    if (priorities.healthy.length > 0) {
      console.log('   ' + priorities.healthy.map(r => r.name).join(', '));
    } else {
      console.log('   None - all routes need attention');
    }
    
    // Provide specific fix recommendations
    console.log('\n🔧 IMMEDIATE ACTIONS NEEDED:');
    console.log('═'.repeat(80));
    
    let actionCount = 1;
    
    priorities.critical.forEach(route => {
      if (route.analysis.issues) {
        route.analysis.issues.filter(i => i.severity === 'critical').forEach(issue => {
          console.log(`${actionCount}. Fix ${route.name}: ${issue.issue}`);
          console.log(`   Action: ${issue.fix}`);
          actionCount++;
        });
      }
      
      if (route.loadTest && !route.loadTest.loadable) {
        console.log(`${actionCount}. Fix ${route.name} loading error:`);
        console.log(`   Error: ${route.loadTest.error}`);
        console.log(`   Check: Dependencies and syntax`);
        actionCount++;
      }
    });
    
    if (actionCount === 1) {
      console.log('No critical issues found! Focus on medium priority items.');
    }
    
    // Summary and next steps
    const totalIssues = priorities.critical.length + priorities.medium.length;
    const healthyPercent = Math.round((priorities.healthy.length / (priorities.critical.length + priorities.medium.length + priorities.healthy.length)) * 100);
    
    console.log('\n📊 DIAGNOSTIC SUMMARY:');
    console.log('═'.repeat(80));
    console.log(`Health Status: ${healthyPercent}% healthy routes`);
    console.log(`Issues Found: ${totalIssues} routes need attention`);
    console.log(`Recommended: Fix critical issues first, then medium priority`);
    console.log();
    
    // Exit with appropriate code
    if (priorities.critical.length > 0) {
      console.log('❌ Critical issues found. Address these first.');
      process.exit(1);
    } else if (priorities.medium.length > 0) {
      console.log('⚠️  Some issues found. Consider addressing for better reliability.');
      process.exit(0);
    } else {
      console.log('✅ All routes look healthy!');
      process.exit(0);
    }
    
  } catch (error) {
    console.error('❌ Diagnostic failed:', error.message);
    console.error('Stack:', error.stack);
    process.exit(1);
  }
}

// Run if called directly
if (require.main === module) {
  runDiagnostic().catch(error => {
    console.error('Fatal error:', error);
    process.exit(1);
  });
}

module.exports = { runDiagnostic };