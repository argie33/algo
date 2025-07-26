/**
 * Authentication Diagnostics System
 * Provides detailed error analysis and troubleshooting for authentication failures
 * 
 * Design Goals:
 * - Immediate problem identification
 * - Clear, actionable error messages
 * - Step-by-step troubleshooting guides
 * - Real-time configuration validation
 */

class AuthDiagnostics {
  constructor() {
    this.diagnosticResults = {};
    this.errorHistory = [];
  }

  /**
   * Run comprehensive authentication diagnostics
   */
  async runFullDiagnostics() {
    console.log('🔍 Running comprehensive authentication diagnostics...');
    
    const diagnostics = {
      timestamp: new Date().toISOString(),
      environment: this.getEnvironmentInfo(),
      configurationSources: await this.diagnoseConfigurationSources(),
      amplifyStatus: await this.diagnoseAmplifyStatus(),
      cognitoConnectivity: await this.diagnoseCognitoConnectivity(),
      apiConnectivity: await this.diagnoseApiConnectivity(),
      sessionState: this.diagnoseSessionState(),
      recommendations: []
    };

    // Generate recommendations based on findings
    diagnostics.recommendations = this.generateRecommendations(diagnostics);

    this.diagnosticResults = diagnostics;
    this.logDiagnosticResults();
    
    return diagnostics;
  }

  /**
   * Get environment information
   */
  getEnvironmentInfo() {
    return {
      userAgent: navigator.userAgent,
      url: window.location.href,
      timestamp: new Date().toISOString(),
      nodeEnv: import.meta.env.MODE,
      viteEnv: {
        apiUrl: import.meta.env.VITE_API_BASE_URL,
        userPoolId: import.meta.env.VITE_COGNITO_USER_POOL_ID ? 'SET' : 'NOT_SET',
        clientId: import.meta.env.VITE_COGNITO_CLIENT_ID ? 'SET' : 'NOT_SET',
        region: import.meta.env.VITE_AWS_REGION || 'DEFAULT'
      },
      windowConfig: {
        hasConfig: !!window.__CONFIG__,
        hasCloudFormationConfig: !!window.__CLOUDFORMATION_CONFIG__,
        configKeys: window.__CONFIG__ ? Object.keys(window.__CONFIG__) : []
      }
    };
  }

  /**
   * Diagnose configuration sources
   */
  async diagnoseConfigurationSources() {
    const sources = {
      cloudformation: await this.testCloudFormationConfig(),
      environment: this.testEnvironmentConfig(),
      runtimeApi: await this.testRuntimeApiConfig(),
      windowConfig: this.testWindowConfig()
    };

    return sources;
  }

  /**
   * Test CloudFormation configuration
   */
  async testCloudFormationConfig() {
    const result = {
      available: false,
      valid: false,
      errors: [],
      data: {}
    };

    try {
      const cfConfig = window.__CLOUDFORMATION_CONFIG__ || window.__CONFIG__;
      
      if (!cfConfig) {
        result.errors.push('❌ CloudFormation config not found in window.__CONFIG__ or window.__CLOUDFORMATION_CONFIG__');
        result.errors.push('💡 This usually means the config.js file is not loaded or the CloudFormation stack outputs are not properly set');
        return result;
      }

      result.available = true;
      result.data = {
        userPoolId: cfConfig.UserPoolId,
        clientId: cfConfig.UserPoolClientId,
        region: cfConfig.Region,
        apiUrl: cfConfig.ApiGatewayUrl
      };

      // Validate each required field
      const requiredFields = [
        { key: 'UserPoolId', value: cfConfig.UserPoolId, pattern: /^us-[a-z0-9-]+_[A-Za-z0-9]+$/ },
        { key: 'UserPoolClientId', value: cfConfig.UserPoolClientId, pattern: /^[a-z0-9]{26}$/ },
        { key: 'Region', value: cfConfig.Region, pattern: /^us-[a-z]+-\d+$/ },
        { key: 'ApiGatewayUrl', value: cfConfig.ApiGatewayUrl, pattern: /^https:\/\/[a-z0-9]+\.execute-api\.[a-z0-9-]+\.amazonaws\.com/ }
      ];

      let validFields = 0;
      for (const field of requiredFields) {
        if (!field.value) {
          result.errors.push(`❌ Missing ${field.key}`);
        } else if (field.value === 'undefined' || field.value === 'null') {
          result.errors.push(`❌ ${field.key} is placeholder value: ${field.value}`);
        } else if (!field.pattern.test(field.value)) {
          result.errors.push(`❌ ${field.key} has invalid format: ${field.value}`);
          result.errors.push(`💡 Expected format: ${field.pattern.source}`);
        } else {
          validFields++;
        }
      }

      result.valid = validFields === requiredFields.length;

      if (result.valid) {
        result.errors.push('✅ CloudFormation configuration is valid');
      } else {
        result.errors.push('💡 Check your CloudFormation stack deployment and outputs');
      }

    } catch (error) {
      result.errors.push(`❌ CloudFormation config error: ${error.message}`);
    }

    return result;
  }

  /**
   * Test environment configuration
   */
  testEnvironmentConfig() {
    const result = {
      available: false,
      valid: false,
      errors: [],
      data: {}
    };

    const env = import.meta.env;
    const requiredVars = ['VITE_COGNITO_USER_POOL_ID', 'VITE_COGNITO_CLIENT_ID'];
    const optionalVars = ['VITE_AWS_REGION', 'VITE_API_BASE_URL'];

    result.data = {
      userPoolId: env.VITE_COGNITO_USER_POOL_ID,
      clientId: env.VITE_COGNITO_CLIENT_ID,
      region: env.VITE_AWS_REGION,
      apiUrl: env.VITE_API_BASE_URL
    };

    let foundVars = 0;
    for (const varName of requiredVars) {
      if (env[varName]) {
        foundVars++;
        result.errors.push(`✅ ${varName} is set`);
      } else {
        result.errors.push(`❌ ${varName} is not set`);
        result.errors.push(`💡 Add ${varName} to your .env file`);
      }
    }

    result.available = foundVars > 0;
    result.valid = foundVars === requiredVars.length;

    if (!result.available) {
      result.errors.push('💡 Create a .env file in your project root with required variables');
    }

    return result;
  }

  /**
   * Test runtime API configuration
   */
  async testRuntimeApiConfig() {
    const result = {
      available: false,
      valid: false,
      errors: [],
      data: {},
      responseTime: null
    };

    try {
      const startTime = Date.now();
      const response = await fetch('/api/config/auth', {
        method: 'GET',
        headers: { 'Accept': 'application/json' },
        signal: AbortSignal.timeout(10000)
      });
      result.responseTime = Date.now() - startTime;

      if (!response.ok) {
        result.errors.push(`❌ API config request failed: ${response.status} ${response.statusText}`);
        result.errors.push(`💡 Check if your API Gateway is deployed and the /config/auth endpoint exists`);
        return result;
      }

      const data = await response.json();
      result.available = true;
      result.data = data;

      if (data.userPoolId && data.clientId && data.region) {
        result.valid = true;
        result.errors.push(`✅ Runtime API config is valid (${result.responseTime}ms)`);
      } else {
        result.errors.push('❌ Runtime API config is incomplete');
        result.errors.push(`💡 Missing fields: ${['userPoolId', 'clientId', 'region'].filter(field => !data[field]).join(', ')}`);
      }

    } catch (error) {
      if (error.name === 'TimeoutError') {
        result.errors.push('❌ API config request timed out (>10s)');
        result.errors.push('💡 Check your API Gateway deployment and network connectivity');
      } else if (error.message.includes('NetworkError')) {
        result.errors.push('❌ Network error accessing API config');
        result.errors.push('💡 Check if your API Gateway URL is correct and accessible');
      } else {
        result.errors.push(`❌ API config error: ${error.message}`);
      }
    }

    return result;
  }

  /**
   * Test window configuration
   */
  testWindowConfig() {
    const result = {
      available: false,
      valid: false,
      errors: [],
      data: {}
    };

    if (window.__AUTH_CONFIG__) {
      result.available = true;
      result.data = window.__AUTH_CONFIG__;
      result.valid = !!(result.data.userPoolId && result.data.clientId);
      result.errors.push(result.valid ? '✅ Window auth config is valid' : '❌ Window auth config is incomplete');
    } else {
      result.errors.push('❌ window.__AUTH_CONFIG__ not found');
      result.errors.push('💡 This is set by your application initialization code');
    }

    return result;
  }

  /**
   * Diagnose Amplify status
   */
  async diagnoseAmplifyStatus() {
    const result = {
      configured: false,
      errors: [],
      configDetails: {}
    };

    try {
      const { Amplify } = await import('aws-amplify');
      
      // Try to get current config
      try {
        const currentConfig = Amplify.getConfig();
        result.configured = !!(currentConfig?.Auth?.Cognito);
        
        if (result.configured) {
          result.configDetails = {
            userPoolId: currentConfig.Auth.Cognito.userPoolId,
            userPoolClientId: currentConfig.Auth.Cognito.userPoolClientId,
            region: currentConfig.Auth.Cognito.region
          };
          result.errors.push('✅ Amplify is properly configured');
        } else {
          result.errors.push('❌ Amplify is not configured');
          result.errors.push('💡 Call Amplify.configure() with valid Cognito configuration');
        }
      } catch (configError) {
        result.errors.push(`❌ Amplify configuration error: ${configError.message}`);
        if (configError.message.includes('not configured')) {
          result.errors.push('💡 Amplify.configure() has not been called yet');
        }
      }

    } catch (importError) {
      result.errors.push(`❌ Cannot import Amplify: ${importError.message}`);
      result.errors.push('💡 Check if aws-amplify package is installed');
    }

    return result;
  }

  /**
   * Diagnose Cognito connectivity
   */
  async diagnoseCognitoConnectivity() {
    const result = {
      reachable: false,
      errors: [],
      responseTime: null
    };

    try {
      // Try to reach Cognito service
      const region = import.meta.env.VITE_AWS_REGION || 'us-east-1';
      const cognitoUrl = `https://cognito-idp.${region}.amazonaws.com/`;
      
      const startTime = Date.now();
      const response = await fetch(cognitoUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-amz-json-1.1' },
        body: '{}',
        signal: AbortSignal.timeout(5000)
      });
      result.responseTime = Date.now() - startTime;

      // Any response (even error) means Cognito is reachable
      result.reachable = true;
      result.errors.push(`✅ Cognito service is reachable (${result.responseTime}ms)`);

    } catch (error) {
      if (error.name === 'TimeoutError') {
        result.errors.push('❌ Cognito service timeout');
        result.errors.push('💡 Check your internet connection and AWS service status');
      } else {
        result.errors.push(`❌ Cannot reach Cognito: ${error.message}`);
        result.errors.push('💡 Check your network connection and region configuration');
      }
    }

    return result;
  }

  /**
   * Diagnose API connectivity
   */
  async diagnoseApiConnectivity() {
    const result = {
      reachable: false,
      errors: [],
      responseTime: null,
      endpoints: {}
    };

    const apiUrl = import.meta.env.VITE_API_BASE_URL || 
                   window.__CONFIG__?.ApiGatewayUrl ||
                   'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev';

    const endpoints = [
      { name: 'health', path: '/health' },
      { name: 'config', path: '/api/config' },
      { name: 'auth-status', path: '/api/auth/status' }
    ];

    for (const endpoint of endpoints) {
      try {
        const startTime = Date.now();
        const response = await fetch(`${apiUrl}${endpoint.path}`, {
          signal: AbortSignal.timeout(5000)
        });
        const responseTime = Date.now() - startTime;

        result.endpoints[endpoint.name] = {
          reachable: true,
          status: response.status,
          responseTime
        };

        if (response.ok) {
          result.errors.push(`✅ ${endpoint.name} endpoint OK (${responseTime}ms)`);
        } else {
          result.errors.push(`⚠️ ${endpoint.name} endpoint returned ${response.status}`);
        }

        result.reachable = true;

      } catch (error) {
        result.endpoints[endpoint.name] = {
          reachable: false,
          error: error.message
        };
        result.errors.push(`❌ ${endpoint.name} endpoint failed: ${error.message}`);
      }
    }

    if (!result.reachable) {
      result.errors.push('💡 Check your API Gateway deployment and URL configuration');
    }

    return result;
  }

  /**
   * Diagnose session state
   */
  diagnoseSessionState() {
    const result = {
      hasSession: false,
      sessionData: {},
      errors: []
    };

    // Check various session storage locations
    const sessionChecks = [
      { name: 'localStorage', storage: localStorage },
      { name: 'sessionStorage', storage: sessionStorage }
    ];

    for (const check of sessionChecks) {
      try {
        const keys = Object.keys(check.storage).filter(key => 
          key.includes('cognito') || key.includes('amplify') || key.includes('auth')
        );

        if (keys.length > 0) {
          result.hasSession = true;
          result.sessionData[check.name] = keys;
          result.errors.push(`✅ Found ${keys.length} auth-related items in ${check.name}`);
        }
      } catch (error) {
        result.errors.push(`❌ Cannot access ${check.name}: ${error.message}`);
      }
    }

    if (!result.hasSession) {
      result.errors.push('ℹ️ No authentication session found');
      result.errors.push('💡 User needs to log in to establish a session');
    }

    return result;
  }

  /**
   * Generate recommendations based on diagnostic results
   */
  generateRecommendations(diagnostics) {
    const recommendations = [];

    // Configuration source recommendations
    const validSources = Object.entries(diagnostics.configurationSources)
      .filter(([_, source]) => source.valid);

    if (validSources.length === 0) {
      recommendations.push({
        priority: 'CRITICAL',
        category: 'Configuration',
        issue: 'No valid configuration source found',
        solution: 'Fix CloudFormation deployment or set environment variables',
        steps: [
          '1. Check AWS CloudFormation stack status',
          '2. Verify stack outputs include UserPoolId, UserPoolClientId, Region, ApiGatewayUrl',
          '3. Ensure config.js is properly loading CloudFormation outputs',
          '4. As fallback, set VITE_COGNITO_USER_POOL_ID and VITE_COGNITO_CLIENT_ID in .env'
        ]
      });
    }

    // Amplify configuration recommendations
    if (!diagnostics.amplifyStatus.configured) {
      recommendations.push({
        priority: 'HIGH',
        category: 'Amplify',
        issue: 'Amplify is not properly configured',
        solution: 'Initialize Amplify with valid Cognito configuration',
        steps: [
          '1. Ensure valid configuration is loaded from one of the sources',
          '2. Call Amplify.configure() in app initialization',
          '3. Handle configuration errors gracefully'
        ]
      });
    }

    // Connectivity recommendations
    if (!diagnostics.apiConnectivity.reachable) {
      recommendations.push({
        priority: 'HIGH',
        category: 'Connectivity',
        issue: 'API Gateway is not reachable',
        solution: 'Fix API Gateway deployment or URL configuration',
        steps: [
          '1. Verify API Gateway is deployed',
          '2. Check API Gateway URL in configuration',
          '3. Test API endpoints manually in browser',
          '4. Check CORS configuration'
        ]
      });
    }

    return recommendations;
  }

  /**
   * Log diagnostic results in a readable format
   */
  logDiagnosticResults() {
    console.group('🔍 Authentication Diagnostic Results');
    
    const { diagnosticResults: results } = this;
    
    console.log('📊 Summary:', {
      timestamp: results.timestamp,
      criticalIssues: results.recommendations.filter(r => r.priority === 'CRITICAL').length,
      highIssues: results.recommendations.filter(r => r.priority === 'HIGH').length
    });

    console.group('🌍 Environment');
    console.table(results.environment.viteEnv);
    console.groupEnd();

    console.group('⚙️ Configuration Sources');
    Object.entries(results.configurationSources).forEach(([source, data]) => {
      console.group(`${data.valid ? '✅' : '❌'} ${source}`);
      data.errors.forEach(error => console.log(error));
      if (data.data && Object.keys(data.data).length > 0) {
        console.table(data.data);
      }
      console.groupEnd();
    });
    console.groupEnd();

    console.group('🚨 Recommendations');
    results.recommendations.forEach((rec, index) => {
      console.group(`${rec.priority} - ${rec.category}: ${rec.issue}`);
      console.log('💡 Solution:', rec.solution);
      console.log('📝 Steps:', rec.steps);
      console.groupEnd();
    });
    console.groupEnd();

    console.groupEnd();
  }

  /**
   * Get human-readable error summary
   */
  getErrorSummary() {
    if (!this.diagnosticResults.recommendations) return 'No diagnostics run yet';

    const critical = this.diagnosticResults.recommendations.filter(r => r.priority === 'CRITICAL');
    const high = this.diagnosticResults.recommendations.filter(r => r.priority === 'HIGH');

    if (critical.length > 0) {
      return `CRITICAL: ${critical[0].issue} - ${critical[0].solution}`;
    }
    
    if (high.length > 0) {
      return `ISSUE: ${high[0].issue} - ${high[0].solution}`;
    }

    return 'Authentication system appears to be configured correctly';
  }
}

export default AuthDiagnostics;