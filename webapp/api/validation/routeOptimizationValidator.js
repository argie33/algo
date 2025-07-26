/**
 * Route Optimization Validator
 * Ensures all functionality is preserved after optimization
 */

const fs = require('fs');
const path = require('path');

class RouteOptimizationValidator {
  constructor() {
    this.originalRoutes = new Map();
    this.enhancedRoutes = new Map();
    this.validationResults = {
      passed: [],
      failed: [],
      warnings: []
    };
  }

  /**
   * Validate that all original functionality is preserved
   */
  async validateOptimization() {
    console.log('🔍 Starting route optimization validation...');
    
    // Step 1: Catalog original routes
    await this.catalogOriginalRoutes();
    
    // Step 2: Catalog enhanced routes
    await this.catalogEnhancedRoutes();
    
    // Step 3: Validate functionality preservation
    await this.validateFunctionalityPreservation();
    
    // Step 4: Validate enhanced features
    await this.validateEnhancedFeatures();
    
    // Step 5: Generate validation report
    this.generateValidationReport();
    
    return this.validationResults;
  }

  /**
   * Catalog all original routes and their endpoints
   */
  async catalogOriginalRoutes() {
    console.log('📋 Cataloging original routes...');
    
    const routeFiles = [
      '../routes/backtest.js',
      '../routes/backtest-new.js',
      '../routes/websocket.js',
      '../routes/websocket-simple.js',
      '../routes/trading.js',
      '../routes/trading_enhanced.js',
      '../routes/stocks.js',
      '../routes/stocks-simple.js',
      '../routes/settings.js'
    ];

    for (const routeFile of routeFiles) {
      try {
        const fullPath = path.resolve(__dirname, routeFile);
        if (fs.existsSync(fullPath)) {
          const endpoints = await this.extractEndpoints(fullPath);
          this.originalRoutes.set(routeFile, endpoints);
          console.log(`✅ Cataloged ${routeFile}: ${endpoints.length} endpoints`);
        } else {
          console.log(`⚠️ Route file not found: ${routeFile}`);
        }
      } catch (error) {
        console.log(`❌ Error cataloging ${routeFile}: ${error.message}`);
      }
    }
  }

  /**
   * Catalog all enhanced routes and their endpoints
   */
  async catalogEnhancedRoutes() {
    console.log('📋 Cataloging enhanced routes...');
    
    const enhancedRouteFiles = [
      '../routes/enhanced/unifiedBacktest.js',
      '../routes/enhanced/unifiedWebsocket.js',
      '../routes/enhanced/unifiedTrading.js',
      '../routes/enhanced/consolidatedSettings.js'
    ];

    for (const routeFile of enhancedRouteFiles) {
      try {
        const fullPath = path.resolve(__dirname, routeFile);
        if (fs.existsSync(fullPath)) {
          const endpoints = await this.extractEndpoints(fullPath);
          this.enhancedRoutes.set(routeFile, endpoints);
          console.log(`✅ Cataloged enhanced ${routeFile}: ${endpoints.length} endpoints`);
        }
      } catch (error) {
        console.log(`❌ Error cataloging enhanced ${routeFile}: ${error.message}`);
      }
    }
  }

  /**
   * Extract endpoints from a route file
   */
  async extractEndpoints(filePath) {
    try {
      const content = fs.readFileSync(filePath, 'utf8');
      const endpoints = [];
      
      // Extract router methods
      const routerMethods = ['get', 'post', 'put', 'delete', 'patch'];
      const routePattern = new RegExp(`router\\.(${routerMethods.join('|')})\\s*\\(\\s*['"\`]([^'"\`]+)['"\`]`, 'g');
      
      let match;
      while ((match = routePattern.exec(content)) !== null) {
        endpoints.push({
          method: match[1].toUpperCase(),
          path: match[2],
          line: this.getLineNumber(content, match.index)
        });
      }
      
      // Extract app methods from index.js style files
      const appPattern = new RegExp(`app\\.(${routerMethods.join('|')})\\s*\\(\\s*['"\`]([^'"\`]+)['"\`]`, 'g');
      while ((match = appPattern.exec(content)) !== null) {
        endpoints.push({
          method: match[1].toUpperCase(),
          path: match[2],
          line: this.getLineNumber(content, match.index)
        });
      }
      
      return endpoints;
    } catch (error) {
      console.error(`Error extracting endpoints from ${filePath}:`, error.message);
      return [];
    }
  }

  /**
   * Get line number for a string index
   */
  getLineNumber(content, index) {
    return content.substring(0, index).split('\n').length;
  }

  /**
   * Validate that all original functionality is preserved
   */
  async validateFunctionalityPreservation() {
    console.log('🔍 Validating functionality preservation...');
    
    // Define route mappings
    const routeMappings = [
      {
        original: ['../routes/backtest.js', '../routes/backtest-new.js'],
        enhanced: '../routes/enhanced/unifiedBacktest.js',
        name: 'Backtest Routes'
      },
      {
        original: ['../routes/websocket.js', '../routes/websocket-simple.js'],
        enhanced: '../routes/enhanced/unifiedWebsocket.js',
        name: 'WebSocket Routes'
      },
      {
        original: ['../routes/trading.js', '../routes/trading_enhanced.js'],
        enhanced: '../routes/enhanced/unifiedTrading.js',
        name: 'Trading Routes'
      },
      {
        original: ['../routes/settings.js'],
        enhanced: '../routes/enhanced/consolidatedSettings.js',
        name: 'Settings Routes'
      }
    ];

    for (const mapping of routeMappings) {
      await this.validateRouteMapping(mapping);
    }
  }

  /**
   * Validate a specific route mapping
   */
  async validateRouteMapping(mapping) {
    console.log(`🔍 Validating ${mapping.name}...`);
    
    // Collect all original endpoints
    const originalEndpoints = new Map();
    for (const originalRoute of mapping.original) {
      const endpoints = this.originalRoutes.get(originalRoute) || [];
      for (const endpoint of endpoints) {
        const key = `${endpoint.method}:${endpoint.path}`;
        originalEndpoints.set(key, { ...endpoint, source: originalRoute });
      }
    }

    // Get enhanced endpoints
    const enhancedEndpoints = new Map();
    const enhanced = this.enhancedRoutes.get(mapping.enhanced) || [];
    for (const endpoint of enhanced) {
      const key = `${endpoint.method}:${endpoint.path}`;
      enhancedEndpoints.set(key, { ...endpoint, source: mapping.enhanced });
    }

    // Check coverage
    let preserved = 0;
    let missing = 0;
    let enhanced_count = 0;

    for (const [key, originalEndpoint] of originalEndpoints.entries()) {
      if (enhancedEndpoints.has(key)) {
        preserved++;
        this.validationResults.passed.push({
          test: `${mapping.name} - ${key}`,
          status: 'preserved',
          original_source: originalEndpoint.source,
          enhanced_source: mapping.enhanced
        });
      } else {
        missing++;
        this.validationResults.failed.push({
          test: `${mapping.name} - ${key}`,
          status: 'missing',
          original_source: originalEndpoint.source,
          enhanced_source: mapping.enhanced,
          issue: `Endpoint ${key} not found in enhanced implementation`
        });
      }
    }

    // Check for new endpoints
    for (const [key, enhancedEndpoint] of enhancedEndpoints.entries()) {
      if (!originalEndpoints.has(key)) {
        enhanced_count++;
        this.validationResults.passed.push({
          test: `${mapping.name} - ${key}`,
          status: 'enhanced',
          enhanced_source: mapping.enhanced,
          issue: `New endpoint added: ${key}`
        });
      }
    }

    console.log(`✅ ${mapping.name}: ${preserved} preserved, ${missing} missing, ${enhanced_count} enhanced`);
  }

  /**
   * Validate enhanced features
   */
  async validateEnhancedFeatures() {
    console.log('🔍 Validating enhanced features...');
    
    const enhancedFeatures = [
      {
        name: 'Route Unification Layer',
        file: '../routes/enhanced/routeUnificationLayer.js',
        expectedFeatures: ['registerUnifiedRoute', 'createEnhancedBacktestRoute', 'recordMetrics']
      },
      {
        name: 'Intelligent Route Loader',
        file: '../routes/enhanced/intelligentRouteLoader.js',
        expectedFeatures: ['loadRouteWithDependencies', 'checkDependencies', 'createFallbackRoute']
      },
      {
        name: 'Enhanced Frontend Config',
        file: '../../frontend/src/routing/enhancedRouteConfig.js',
        expectedFeatures: ['EnhancedRouteManager', 'makeEnhancedAPICall', 'routeManager']
      }
    ];

    for (const feature of enhancedFeatures) {
      await this.validateEnhancedFeature(feature);
    }
  }

  /**
   * Validate a specific enhanced feature
   */
  async validateEnhancedFeature(feature) {
    try {
      const fullPath = path.resolve(__dirname, feature.file);
      
      if (!fs.existsSync(fullPath)) {
        this.validationResults.failed.push({
          test: `Enhanced Feature - ${feature.name}`,
          status: 'missing_file',
          issue: `File not found: ${feature.file}`
        });
        return;
      }

      const content = fs.readFileSync(fullPath, 'utf8');
      let foundFeatures = 0;
      
      for (const expectedFeature of feature.expectedFeatures) {
        if (content.includes(expectedFeature)) {
          foundFeatures++;
        } else {
          this.validationResults.warnings.push({
            test: `Enhanced Feature - ${feature.name}`,
            status: 'missing_feature',
            issue: `Expected feature not found: ${expectedFeature}`
          });
        }
      }

      if (foundFeatures === feature.expectedFeatures.length) {
        this.validationResults.passed.push({
          test: `Enhanced Feature - ${feature.name}`,
          status: 'complete',
          features_found: foundFeatures,
          total_features: feature.expectedFeatures.length
        });
      } else {
        this.validationResults.failed.push({
          test: `Enhanced Feature - ${feature.name}`,
          status: 'incomplete',
          features_found: foundFeatures,
          total_features: feature.expectedFeatures.length
        });
      }

      console.log(`✅ ${feature.name}: ${foundFeatures}/${feature.expectedFeatures.length} features found`);

    } catch (error) {
      this.validationResults.failed.push({
        test: `Enhanced Feature - ${feature.name}`,
        status: 'error',
        issue: error.message
      });
    }
  }

  /**
   * Generate comprehensive validation report
   */
  generateValidationReport() {
    console.log('\n📊 ROUTE OPTIMIZATION VALIDATION REPORT');
    console.log('=' .repeat(50));
    
    const totalTests = this.validationResults.passed.length + this.validationResults.failed.length;
    const successRate = totalTests > 0 ? Math.round((this.validationResults.passed.length / totalTests) * 100) : 0;
    
    console.log(`✅ Passed: ${this.validationResults.passed.length}`);
    console.log(`❌ Failed: ${this.validationResults.failed.length}`);
    console.log(`⚠️ Warnings: ${this.validationResults.warnings.length}`);
    console.log(`📈 Success Rate: ${successRate}%`);
    
    if (this.validationResults.failed.length > 0) {
      console.log('\n❌ FAILED TESTS:');
      this.validationResults.failed.forEach(failure => {
        console.log(`   - ${failure.test}: ${failure.issue}`);
      });
    }
    
    if (this.validationResults.warnings.length > 0) {
      console.log('\n⚠️ WARNINGS:');
      this.validationResults.warnings.forEach(warning => {
        console.log(`   - ${warning.test}: ${warning.issue}`);
      });
    }
    
    console.log('\n🎯 VALIDATION SUMMARY:');
    if (this.validationResults.failed.length === 0) {
      console.log('✅ ALL FUNCTIONALITY PRESERVED - Optimization successful!');
    } else {
      console.log('❌ Some functionality may be missing - Review failed tests');
    }
    
    return {
      success: this.validationResults.failed.length === 0,
      successRate,
      totalTests,
      passed: this.validationResults.passed.length,
      failed: this.validationResults.failed.length,
      warnings: this.validationResults.warnings.length
    };
  }
}

// Export for use in tests
module.exports = RouteOptimizationValidator;

// Run validation if called directly
if (require.main === module) {
  const validator = new RouteOptimizationValidator();
  validator.validateOptimization()
    .then(results => {
      process.exit(results.success ? 0 : 1);
    })
    .catch(error => {
      console.error('Validation failed:', error);
      process.exit(1);
    });
}