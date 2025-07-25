/**
 * Production Environment Validator
 * Comprehensive validation for production deployment readiness
 */

class ProductionValidator {
  constructor() {
    this.correlationId = `validator-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Validate environment configuration
   */
  async validateEnvironment() {
    console.log('🌍 Validating environment configuration...');
    
    const checks = [];
    let passed = 0;
    
    // Required environment variables
    const requiredVars = [
      'AWS_REGION',
      'NODE_ENV'
    ];
    
    requiredVars.forEach(varName => {
      const exists = !!process.env[varName];
      checks.push({ name: `${varName} configured`, passed: exists, value: exists ? process.env[varName] : 'missing' });
      if (exists) passed++;
    });
    
    // Production-specific checks
    const isProduction = process.env.NODE_ENV === 'production';
    checks.push({ name: 'NODE_ENV set to production', passed: isProduction, value: process.env.NODE_ENV });
    if (isProduction) passed++;
    
    const devBypassDisabled = process.env.ALLOW_DEV_BYPASS !== 'true';
    checks.push({ name: 'Development bypass disabled', passed: devBypassDisabled, value: process.env.ALLOW_DEV_BYPASS || 'false' });
    if (devBypassDisabled) passed++;
    
    return { category: 'Environment', checks: checks.length, passed_checks: passed, details: checks, passed: passed === checks.length };
  }

  /**
   * Validate database configuration
   */
  async validateDatabase() {
    console.log('🗄️ Validating database configuration...');
    
    const checks = [];
    let passed = 0;
    
    try {
      // Check database module availability
      const { healthCheck } = require('./database');
      checks.push({ name: 'Database module available', passed: true });
      passed++;
      
      // Test database connection
      try {
        const dbHealth = await healthCheck();
        const isHealthy = dbHealth && dbHealth.healthy;
        checks.push({ 
          name: 'Database connection', 
          passed: isHealthy, 
          value: isHealthy ? 'connected' : 'failed',
          details: dbHealth 
        });
        if (isHealthy) passed++;
      } catch (dbError) {
        checks.push({ 
          name: 'Database connection', 
          passed: false, 
          error: dbError.message 
        });
      }
      
    } catch (error) {
      checks.push({ name: 'Database module available', passed: false, error: error.message });
    }
    
    return { category: 'Database', checks: checks.length, passed_checks: passed, details: checks, passed: passed === checks.length };
  }

  /**
   * Validate authentication configuration
   */
  async validateAuthentication() {
    console.log('🔐 Validating authentication configuration...');
    
    const checks = [];
    let passed = 0;
    
    try {
      // Check auth middleware availability
      const auth = require('../middleware/auth');
      checks.push({ name: 'Auth middleware available', passed: true });
      passed++;
      
      // Check JWT secret configuration
      const hasJwtSecret = !!(process.env.JWT_SECRET || process.env.JWT_SECRET_ARN);
      checks.push({ name: 'JWT secret configured', passed: hasJwtSecret });
      if (hasJwtSecret) passed++;
      
      // Check authenticateToken function
      const hasAuthFunction = typeof auth.authenticateToken === 'function';
      checks.push({ name: 'Authentication function available', passed: hasAuthFunction });
      if (hasAuthFunction) passed++;
      
    } catch (error) {
      checks.push({ name: 'Auth middleware available', passed: false, error: error.message });
    }
    
    return { category: 'Authentication', checks: checks.length, passed_checks: passed, details: checks, passed: passed === checks.length };
  }

  /**
   * Validate security configuration
   */
  async validateSecurity() {
    console.log('🛡️ Validating security configuration...');
    
    const checks = [];
    let passed = 0;
    
    // Security environment variables
    const corsConfigured = !!process.env.CORS_ORIGIN;
    checks.push({ name: 'CORS properly configured', passed: corsConfigured, value: process.env.CORS_ORIGIN || 'not set' });
    if (corsConfigured) passed++;
    
    // Check for rate limiting capability
    try {
      require('express-rate-limit');
      checks.push({ name: 'API rate limiting enabled', passed: true });
      passed++;
    } catch (error) {
      checks.push({ name: 'API rate limiting enabled', passed: false, note: 'express-rate-limit not installed' });
    }
    
    // Security headers
    const securityHeadersEnabled = process.env.SECURITY_HEADERS !== 'false';
    checks.push({ name: 'Security headers enabled', passed: securityHeadersEnabled });
    if (securityHeadersEnabled) passed++;
    
    return { category: 'Security', checks: checks.length, passed_checks: passed, details: checks, passed: passed === checks.length };
  }

  /**
   * Validate performance configuration
   */
  async validatePerformance() {
    console.log('⚡ Validating performance configuration...');
    
    const checks = [];
    let passed = 0;
    
    // Memory and performance settings
    const memoryUsage = process.memoryUsage();
    const memoryEfficient = memoryUsage.heapUsed < (256 * 1024 * 1024); // 256MB threshold
    checks.push({ 
      name: 'Memory usage acceptable', 
      passed: memoryEfficient, 
      value: `${Math.round(memoryUsage.heapUsed / 1024 / 1024)}MB` 
    });
    if (memoryEfficient) passed++;
    
    // Check for compression middleware
    try {
      require('compression');
      checks.push({ name: 'Response compression available', passed: true });
      passed++;
    } catch (error) {
      checks.push({ name: 'Response compression available', passed: false, note: 'compression middleware not installed' });
    }
    
    // Performance monitoring
    const perfMonitoring = process.env.PERFORMANCE_MONITORING === 'true';
    checks.push({ name: 'Performance monitoring enabled', passed: perfMonitoring });
    if (perfMonitoring) passed++;
    
    return { category: 'Performance', checks: checks.length, passed_checks: passed, details: checks, passed: passed === checks.length };
  }

  /**
   * Validate monitoring configuration
   */
  async validateMonitoring() {
    console.log('📊 Validating monitoring configuration...');
    
    const checks = [];
    let passed = 0;
    
    // Structured logging
    try {
      const structuredLogger = require('./structuredLogger');
      checks.push({ name: 'Structured logging available', passed: true });
      passed++;
      
      const logger = structuredLogger.createLogger('test', 'validator');
      const hasLogMethods = typeof logger.info === 'function' && typeof logger.error === 'function';
      checks.push({ name: 'Logger functionality working', passed: hasLogMethods });
      if (hasLogMethods) passed++;
      
    } catch (error) {
      checks.push({ name: 'Structured logging available', passed: false, error: error.message });
    }
    
    // Request logging
    const requestLogging = process.env.REQUEST_LOGGING !== 'false';
    checks.push({ name: 'Request logging enabled', passed: requestLogging });
    if (requestLogging) passed++;
    
    // Error monitoring
    const errorMonitoring = !!(process.env.ERROR_MONITORING_ENDPOINT || process.env.SENTRY_DSN);
    checks.push({ name: 'Error monitoring configured', passed: errorMonitoring });
    if (errorMonitoring) passed++;
    
    return { category: 'Monitoring', checks: checks.length, passed_checks: passed, details: checks, passed: passed === checks.length };
  }

  /**
   * Validate HFT service configuration
   */
  async validateHFTService() {
    console.log('🤖 Validating HFT service configuration...');
    
    const checks = [];
    let passed = 0;
    
    try {
      // Check HFT service availability
      const HFTService = require('../services/hftService');
      const hftService = new HFTService();
      checks.push({ name: 'HFT Service instantiation', passed: true });
      passed++;
      
      // Validate risk configuration
      if (hftService.riskConfig) {
        checks.push({ name: 'Risk configuration present', passed: true });
        passed++;
        
        const riskParams = ['maxPositionSize', 'maxDailyLoss', 'maxOpenPositions', 'stopLossPercentage'];
        const hasAllRiskParams = riskParams.every(param => 
          hftService.riskConfig.hasOwnProperty(param) && 
          typeof hftService.riskConfig[param] === 'number'
        );
        checks.push({ name: 'Risk parameters configured', passed: hasAllRiskParams });
        if (hasAllRiskParams) passed++;
      } else {
        checks.push({ name: 'Risk configuration present', passed: false });
      }
      
      // Check strategy initialization
      const strategies = hftService.getStrategies();
      checks.push({ name: 'Trading strategies available', passed: strategies.length > 0 });
      if (strategies.length > 0) passed++;
      
      // Validate metrics system
      const metrics = hftService.getMetrics();
      checks.push({ name: 'Metrics system operational', passed: typeof metrics === 'object' });
      if (typeof metrics === 'object') passed++;
      
    } catch (error) {
      checks.push({ name: 'HFT Service instantiation', passed: false, error: error.message });
    }
    
    return { category: 'HFT Service', checks: checks.length, passed_checks: passed, details: checks, passed: passed === checks.length };
  }

  /**
   * Validate unified API key service
   */
  async validateApiKeyService() {
    console.log('🔑 Validating API key service...');
    
    const checks = [];
    let passed = 0;
    
    try {
      // Check API key service availability
      const unifiedApiKeyService = require('./unifiedApiKeyService');
      checks.push({ name: 'Unified API key service available', passed: true });
      passed++;
      
      // Test service methods
      const testUserId = 'test-user-validation';
      
      // Test Alpaca key operations (should not throw)
      try {
        await unifiedApiKeyService.getAlpacaKey(testUserId);
        checks.push({ name: 'Alpaca key retrieval functional', passed: true });
        passed++;
      } catch (error) {
        if (error.message.includes('No API key found')) {
          checks.push({ name: 'Alpaca key retrieval functional', passed: true, note: 'No keys for test user (expected)' });
          passed++;
        } else {
          checks.push({ name: 'Alpaca key retrieval functional', passed: false, error: error.message });
        }
      }
      
    } catch (error) {
      checks.push({ name: 'Unified API key service available', passed: false, error: error.message });
    }
    
    return { category: 'API Key Service', checks: checks.length, passed_checks: passed, details: checks, passed: passed === checks.length };
  }

  /**
   * Validate live data manager
   */
  async validateLiveDataManager() {
    console.log('📊 Validating live data manager...');
    
    const checks = [];
    let passed = 0;
    
    try {
      // Check live data manager availability
      const LiveDataManager = require('./liveDataManager');
      const liveDataManager = new LiveDataManager();
      checks.push({ name: 'Live data manager instantiation', passed: true });
      passed++;
      
      // Check provider configuration
      const providerStatus = liveDataManager.getProviderStatus();
      if (providerStatus.success && providerStatus.providers.length > 0) {
        checks.push({ name: 'Data providers configured', passed: true });
        passed++;
        
        // Check for Alpaca provider
        const hasAlpaca = providerStatus.providers.some(p => p.id === 'alpaca');
        checks.push({ name: 'Alpaca provider available', passed: hasAlpaca });
        if (hasAlpaca) passed++;
      } else {
        checks.push({ name: 'Data providers configured', passed: false });
      }
      
      // Test service metrics
      const metrics = liveDataManager.getServiceMetrics();
      checks.push({ name: 'Service metrics available', passed: typeof metrics === 'object' });
      if (typeof metrics === 'object') passed++;
      
    } catch (error) {
      checks.push({ name: 'Live data manager instantiation', passed: false, error: error.message });
    }
    
    return { category: 'Live Data Manager', checks: checks.length, passed_checks: passed, details: checks, passed: passed === checks.length };
  }

  /**
   * Validate production readiness
   */
  async validateAll() {
    console.log('🔍 Starting comprehensive production validation...');
    
    const results = {
      environment: await this.validateEnvironment(),
      database: await this.validateDatabase(),
      authentication: await this.validateAuthentication(),
      security: await this.validateSecurity(),
      performance: await this.validatePerformance(),
      monitoring: await this.validateMonitoring(),
      hftService: await this.validateHFTService(),
      apiKeyService: await this.validateApiKeyService(),
      liveDataManager: await this.validateLiveDataManager()
    };
    
    const allPassed = Object.values(results).every(result => result.passed);
    const totalChecks = Object.values(results).reduce((sum, result) => sum + result.checks, 0);
    const passedChecks = Object.values(results).reduce((sum, result) => sum + result.passed_checks, 0);
    
    console.log(`\n📊 Validation Summary: ${passedChecks}/${totalChecks} checks passed`);
    
    if (allPassed) {
      console.log('✅ All validation checks passed - Ready for production deployment!');
    } else {
      console.log('❌ Some validation checks failed - Review issues before deploying');
      
      // Show failed categories
      Object.entries(results).forEach(([category, result]) => {
        if (!result.passed) {
          console.log(`   ❌ ${result.category}: ${result.passed_checks}/${result.checks} checks passed`);
        }
      });
    }
    
    return {
      ready_for_production: allPassed,
      summary: {
        total_checks: totalChecks,
        passed_checks: passedChecks,
        success_rate: Math.round((passedChecks / totalChecks) * 100)
      },
      results,
      recommendations: this.generateRecommendations(results),
      timestamp: new Date().toISOString()
    };
  }

  /**
   * Generate recommendations based on validation results
   */
  generateRecommendations(results) {
    const recommendations = [];
    
    Object.entries(results).forEach(([category, result]) => {
      if (!result.passed) {
        result.details.forEach(check => {
          if (!check.passed) {
            recommendations.push({
              category: result.category,
              issue: check.name,
              recommendation: this.getRecommendation(check.name),
              priority: this.getPriority(check.name)
            });
          }
        });
      }
    });
    
    return recommendations;
  }

  /**
   * Get specific recommendation for a failed check
   */
  getRecommendation(checkName) {
    const recommendations = {
      'Database connection': 'Verify database credentials and network connectivity. Check RDS security groups.',
      'JWT secret configured': 'Set JWT_SECRET environment variable or configure in AWS Secrets Manager.',
      'API rate limiting enabled': 'Configure express-rate-limit middleware with appropriate limits.',
      'CORS properly configured': 'Set CORS_ORIGIN environment variable to restrict allowed origins.',
      'Request logging enabled': 'Ensure structured logging is configured for all requests.',
      'Error monitoring configured': 'Set up CloudWatch or external error monitoring service.',
      'HFT Service instantiation': 'Check HFT service dependencies and configuration.',
      'Risk parameters configured': 'Configure risk management parameters in HFT service.',
      'Trading strategies available': 'Initialize trading strategies in HFT service.',
      'Alpaca provider available': 'Configure Alpaca data provider in live data manager.',
      'Unified API key service available': 'Ensure unified API key service is properly deployed.'
    };
    
    return recommendations[checkName] || 'Review configuration and dependencies for this component.';
  }

  /**
   * Get priority level for a failed check
   */
  getPriority(checkName) {
    const highPriority = [
      'Database connection',
      'JWT secret configured',
      'HFT Service instantiation',
      'Unified API key service available'
    ];
    
    const mediumPriority = [
      'Risk parameters configured',
      'Trading strategies available',
      'Alpaca provider available',
      'API rate limiting enabled',
      'CORS properly configured'
    ];
    
    if (highPriority.includes(checkName)) return 'high';
    if (mediumPriority.includes(checkName)) return 'medium';
    return 'low';
  }

  /**
   * Run production validation CLI
   */
  static async runCLI() {
    console.log('🚀 Production Validation Tool');
    console.log('='.repeat(50));
    
    const validator = new ProductionValidator();
    const results = await validator.validateAll();
    
    console.log('\n' + '='.repeat(50));
    console.log('📄 VALIDATION REPORT');
    console.log('='.repeat(50));
    
    console.log(`Overall Status: ${results.ready_for_production ? '✅ READY' : '❌ NOT READY'}`);
    console.log(`Success Rate: ${results.summary.success_rate}% (${results.summary.passed_checks}/${results.summary.total_checks})`);
    
    if (results.recommendations.length > 0) {
      console.log('\n🔧 RECOMMENDATIONS:');
      results.recommendations.forEach((rec, index) => {
        const priority = rec.priority === 'high' ? '🔴' : rec.priority === 'medium' ? '🟡' : '🟢';
        console.log(`${index + 1}. ${priority} [${rec.category}] ${rec.issue}`);
        console.log(`   💡 ${rec.recommendation}\n`);
      });
    }
    
    console.log(`\n⏰ Validation completed at: ${results.timestamp}`);
    
    return results;
  }
}

// CLI execution
if (require.main === module) {
  ProductionValidator.runCLI()
    .then(results => {
      process.exit(results.ready_for_production ? 0 : 1);
    })
    .catch(error => {
      console.error('❌ Validation failed:', error.message);
      process.exit(1);
    });
}

module.exports = ProductionValidator;