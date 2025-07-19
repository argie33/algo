/**
 * World-Class Test Runner - NO MOCKS
 * Comprehensive test execution and reporting system
 */

const { spawn } = require('child_process');
const fs = require('fs').promises;
const path = require('path');

class WorldClassTestRunner {
  constructor() {
    this.testSuites = [
      {
        name: 'Real Database Tests',
        file: 'real-database.test.js',
        category: 'Infrastructure',
        priority: 1,
        timeout: 60000
      },
      {
        name: 'Real Authentication Tests',
        file: 'real-authentication.test.js',
        category: 'Security',
        priority: 1,
        timeout: 45000
      },
      {
        name: 'Real API Services Tests',
        file: 'real-api-services.test.js',
        category: 'Integration',
        priority: 2,
        timeout: 90000
      },
      {
        name: 'Real Financial Calculations Tests',
        file: 'real-financial-calculations.test.js',
        category: 'Business Logic',
        priority: 2,
        timeout: 120000
      },
      {
        name: 'Real Security & Compliance Tests',
        file: 'real-security-compliance.test.js',
        category: 'Security',
        priority: 1,
        timeout: 90000
      },
      {
        name: 'Real Performance & Load Tests',
        file: 'real-performance-load.test.js',
        category: 'Performance',
        priority: 3,
        timeout: 180000
      },
      {
        name: 'Real API Integration Tests',
        file: 'real-api-integration.test.js',
        category: 'Integration',
        priority: 2,
        timeout: 120000
      },
      {
        name: 'Real End-to-End Tests',
        file: 'real-end-to-end.test.js',
        category: 'E2E',
        priority: 3,
        timeout: 300000
      }
    ];
    
    this.results = {};
    this.startTime = Date.now();
  }
  
  async runTestSuite(suite) {
    console.log(`\n🚀 Running ${suite.name}...`);
    console.log(`   Category: ${suite.category} | Priority: ${suite.priority} | Timeout: ${suite.timeout / 1000}s`);
    
    const startTime = Date.now();
    
    return new Promise((resolve) => {
      const testProcess = spawn('npm', ['test', '--', suite.file, '--verbose'], {
        stdio: 'pipe',
        cwd: process.cwd(),
        timeout: suite.timeout
      });
      
      let output = '';
      let errorOutput = '';
      
      testProcess.stdout.on('data', (data) => {
        const text = data.toString();
        output += text;
        
        // Real-time output for important messages
        if (text.includes('✅') || text.includes('❌') || text.includes('⚠️')) {
          process.stdout.write(text);
        }
      });
      
      testProcess.stderr.on('data', (data) => {
        errorOutput += data.toString();
      });
      
      testProcess.on('close', (code) => {
        const duration = Date.now() - startTime;
        
        const result = {
          suite: suite.name,
          category: suite.category,
          priority: suite.priority,
          exitCode: code,
          duration,
          success: code === 0,
          output,
          errorOutput
        };
        
        this.results[suite.file] = result;
        
        console.log(`   ${result.success ? '✅' : '❌'} ${suite.name} completed in ${duration}ms`);
        
        if (!result.success && errorOutput) {
          console.log(`   Error: ${errorOutput.substring(0, 200)}...`);
        }
        
        resolve(result);
      });
      
      testProcess.on('error', (error) => {
        const duration = Date.now() - startTime;
        
        const result = {
          suite: suite.name,
          category: suite.category,
          priority: suite.priority,
          exitCode: -1,
          duration,
          success: false,
          output: '',
          errorOutput: error.message
        };
        
        this.results[suite.file] = result;
        console.log(`   ❌ ${suite.name} failed to start: ${error.message}`);
        resolve(result);
      });
    });
  }
  
  async runAllTests() {
    console.log('🎯 Starting World-Class Test Suite Execution');
    console.log('=====================================');
    console.log(`Total Test Suites: ${this.testSuites.length}`);
    console.log(`Execution Strategy: Sequential (Infrastructure → Security → Business Logic → Performance → E2E)`);
    console.log();
    
    // Sort by priority (1 = highest)
    const sortedSuites = [...this.testSuites].sort((a, b) => a.priority - b.priority);
    
    // Run tests sequentially to avoid resource conflicts
    for (const suite of sortedSuites) {
      await this.runTestSuite(suite);
    }
    
    return this.generateReport();
  }
  
  async runTestsByCategory(category) {
    console.log(`🎯 Running ${category} Tests Only`);
    console.log('=====================================');
    
    const categoryTests = this.testSuites.filter(suite => suite.category === category);
    
    if (categoryTests.length === 0) {
      console.log(`❌ No tests found for category: ${category}`);
      return;
    }
    
    console.log(`Found ${categoryTests.length} test suites in ${category} category`);
    console.log();
    
    for (const suite of categoryTests) {
      await this.runTestSuite(suite);
    }
    
    return this.generateReport();
  }
  
  async runCriticalTests() {
    console.log('🚨 Running Critical Tests Only (Priority 1)');
    console.log('=====================================');
    
    const criticalTests = this.testSuites.filter(suite => suite.priority === 1);
    
    for (const suite of criticalTests) {
      await this.runTestSuite(suite);
    }
    
    return this.generateReport();
  }
  
  generateReport() {
    const totalDuration = Date.now() - this.startTime;
    const results = Object.values(this.results);
    
    const summary = {
      total: results.length,
      passed: results.filter(r => r.success).length,
      failed: results.filter(r => !r.success).length,
      duration: totalDuration,
      categories: this.getCategoryStats(results),
      priorities: this.getPriorityStats(results)
    };
    
    console.log('\n📊 WORLD-CLASS TEST EXECUTION REPORT');
    console.log('=====================================');
    console.log(`Total Test Suites: ${summary.total}`);
    console.log(`Passed: ${summary.passed} ✅`);
    console.log(`Failed: ${summary.failed} ❌`);
    console.log(`Success Rate: ${(summary.passed / summary.total * 100).toFixed(2)}%`);
    console.log(`Total Duration: ${(summary.duration / 1000).toFixed(2)}s`);
    console.log();
    
    console.log('📈 Results by Category:');
    Object.entries(summary.categories).forEach(([category, stats]) => {
      const successRate = (stats.passed / stats.total * 100).toFixed(2);
      console.log(`  ${category}: ${stats.passed}/${stats.total} (${successRate}%) - ${(stats.duration / 1000).toFixed(2)}s`);
    });
    console.log();
    
    console.log('🎯 Results by Priority:');
    Object.entries(summary.priorities).forEach(([priority, stats]) => {
      const successRate = (stats.passed / stats.total * 100).toFixed(2);
      const priorityName = priority === '1' ? 'Critical' : priority === '2' ? 'Important' : 'Standard';
      console.log(`  ${priorityName} (P${priority}): ${stats.passed}/${stats.total} (${successRate}%) - ${(stats.duration / 1000).toFixed(2)}s`);
    });
    console.log();
    
    if (summary.failed > 0) {
      console.log('❌ Failed Test Suites:');
      results.filter(r => !r.success).forEach(result => {
        console.log(`  • ${result.suite} (${result.category}) - Exit Code: ${result.exitCode}`);
        if (result.errorOutput) {
          const errorLines = result.errorOutput.split('\n').slice(0, 3);
          errorLines.forEach(line => {
            if (line.trim()) console.log(`    ${line.trim()}`);
          });
        }
      });
      console.log();
    }
    
    console.log('🎉 WORLD-CLASS QUALITY ASSESSMENT');
    console.log('=====================================');
    
    const qualityScore = this.calculateQualityScore(summary);
    console.log(`Overall Quality Score: ${qualityScore.score}/100`);
    console.log(`Quality Grade: ${qualityScore.grade}`);
    console.log();
    
    console.log('📋 Quality Breakdown:');
    Object.entries(qualityScore.breakdown).forEach(([aspect, score]) => {
      console.log(`  ${aspect}: ${score}/25`);
    });
    console.log();
    
    console.log('🚀 Recommendations:');
    this.generateRecommendations(summary).forEach(rec => {
      console.log(`  • ${rec}`);
    });
    
    return {
      summary,
      results: this.results,
      qualityScore,
      recommendations: this.generateRecommendations(summary)
    };
  }
  
  getCategoryStats(results) {
    const categories = {};
    
    results.forEach(result => {
      if (!categories[result.category]) {
        categories[result.category] = {
          total: 0,
          passed: 0,
          failed: 0,
          duration: 0
        };
      }
      
      categories[result.category].total++;
      categories[result.category].duration += result.duration;
      
      if (result.success) {
        categories[result.category].passed++;
      } else {
        categories[result.category].failed++;
      }
    });
    
    return categories;
  }
  
  getPriorityStats(results) {
    const priorities = {};
    
    results.forEach(result => {
      const priority = result.priority.toString();
      
      if (!priorities[priority]) {
        priorities[priority] = {
          total: 0,
          passed: 0,
          failed: 0,
          duration: 0
        };
      }
      
      priorities[priority].total++;
      priorities[priority].duration += result.duration;
      
      if (result.success) {
        priorities[priority].passed++;
      } else {
        priorities[priority].failed++;
      }
    });
    
    return priorities;
  }
  
  calculateQualityScore(summary) {
    const breakdown = {
      'Infrastructure Health': Math.min(25, (summary.categories.Infrastructure?.passed || 0) / (summary.categories.Infrastructure?.total || 1) * 25),
      'Security & Compliance': Math.min(25, (summary.categories.Security?.passed || 0) / (summary.categories.Security?.total || 1) * 25),
      'Business Logic': Math.min(25, (summary.categories['Business Logic']?.passed || 0) / (summary.categories['Business Logic']?.total || 1) * 25),
      'Performance & Scale': Math.min(25, ((summary.categories.Performance?.passed || 0) + (summary.categories.E2E?.passed || 0)) / ((summary.categories.Performance?.total || 1) + (summary.categories.E2E?.total || 1)) * 25)
    };
    
    const totalScore = Object.values(breakdown).reduce((sum, score) => sum + score, 0);
    
    let grade;
    if (totalScore >= 95) grade = 'A+ (World-Class)';
    else if (totalScore >= 90) grade = 'A (Excellent)';
    else if (totalScore >= 85) grade = 'A- (Very Good)';
    else if (totalScore >= 80) grade = 'B+ (Good)';
    else if (totalScore >= 75) grade = 'B (Acceptable)';
    else if (totalScore >= 70) grade = 'B- (Needs Improvement)';
    else if (totalScore >= 60) grade = 'C (Significant Issues)';
    else grade = 'D/F (Critical Issues)';
    
    return {
      score: Math.round(totalScore),
      grade,
      breakdown
    };
  }
  
  generateRecommendations(summary) {
    const recommendations = [];
    
    // Critical test failures
    const criticalFailures = Object.values(this.results).filter(r => !r.success && r.priority === 1);
    if (criticalFailures.length > 0) {
      recommendations.push(`🚨 CRITICAL: Fix ${criticalFailures.length} priority 1 test failures immediately`);
    }
    
    // Category-specific recommendations
    Object.entries(summary.categories).forEach(([category, stats]) => {
      const successRate = stats.passed / stats.total;
      
      if (successRate < 0.8) {
        recommendations.push(`🔧 ${category}: Improve success rate from ${(successRate * 100).toFixed(2)}% to >80%`);
      }
      
      if (category === 'Performance' && stats.duration > 180000) {
        recommendations.push(`⚡ Performance: Optimize test execution time (currently ${(stats.duration / 1000).toFixed(2)}s)`);
      }
    });
    
    // Overall recommendations
    if (summary.passed / summary.total < 0.9) {
      recommendations.push('📈 Target >90% overall test success rate for world-class quality');
    }
    
    if (summary.failed === 0) {
      recommendations.push('🎉 Excellent! All tests passing - consider adding more edge case coverage');
    }
    
    return recommendations;
  }
  
  async saveReport(report) {
    const reportPath = path.join(__dirname, 'reports', `test-report-${new Date().toISOString().replace(/[:.]/g, '-')}.json`);
    
    try {
      await fs.mkdir(path.dirname(reportPath), { recursive: true });
      await fs.writeFile(reportPath, JSON.stringify(report, null, 2));
      console.log(`📄 Test report saved to: ${reportPath}`);
    } catch (error) {
      console.log(`⚠️ Failed to save report: ${error.message}`);
    }
  }
}

// CLI Interface
async function main() {
  const args = process.argv.slice(2);
  const runner = new WorldClassTestRunner();
  
  let report;
  
  if (args.includes('--category')) {
    const categoryIndex = args.indexOf('--category');
    const category = args[categoryIndex + 1];
    report = await runner.runTestsByCategory(category);
  } else if (args.includes('--critical')) {
    report = await runner.runCriticalTests();
  } else if (args.includes('--help')) {
    console.log('World-Class Test Runner');
    console.log('Usage:');
    console.log('  node test-runner.js                    # Run all tests');
    console.log('  node test-runner.js --critical         # Run critical tests only');
    console.log('  node test-runner.js --category Security # Run specific category');
    console.log('  node test-runner.js --save             # Save detailed report');
    console.log();
    console.log('Available categories: Infrastructure, Security, Integration, Business Logic, Performance, E2E');
    return;
  } else {
    report = await runner.runAllTests();
  }
  
  if (args.includes('--save') && report) {
    await runner.saveReport(report);
  }
  
  // Exit with appropriate code
  process.exit(report && report.summary.failed === 0 ? 0 : 1);
}

if (require.main === module) {
  main().catch(error => {
    console.error('❌ Test runner failed:', error);
    process.exit(1);
  });
}

module.exports = WorldClassTestRunner;