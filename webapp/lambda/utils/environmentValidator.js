// Environment Variable Validator
// This module validates that all required environment variables are set

const REQUIRED_ENV_VARS = [
  {
    name: 'API_KEY_ENCRYPTION_SECRET_ARN',
    description: 'ARN of the Secrets Manager secret containing API key encryption secret',
    required: process.env.NODE_ENV === 'production',
    sensitive: true
  },
  {
    name: 'DB_SECRET_ARN',
    description: 'ARN of the Secrets Manager secret containing database credentials',
    required: true,
    sensitive: true
  },
  {
    name: 'DB_ENDPOINT',
    description: 'RDS database endpoint',
    required: true,
    sensitive: false
  },
  {
    name: 'COGNITO_SECRET_ARN',
    description: 'ARN of the Secrets Manager secret containing Cognito configuration',
    required: false,
    sensitive: true
  },
  {
    name: 'COGNITO_USER_POOL_ID',
    description: 'Cognito User Pool ID for authentication',
    required: false,
    sensitive: false
  },
  {
    name: 'COGNITO_CLIENT_ID',
    description: 'Cognito App Client ID for authentication',
    required: false,
    sensitive: false
  },
  {
    name: 'WEBAPP_AWS_REGION',
    description: 'AWS region for the webapp deployment',
    required: true,
    sensitive: false
  },
  {
    name: 'NODE_ENV',
    description: 'Node.js environment (development, staging, production)',
    required: false,
    sensitive: false,
    default: 'development'
  }
];

class EnvironmentValidator {
  constructor() {
    this.validationResults = [];
    this.isValid = true;
  }

  validateEnvironment() {
    console.log('🔍 Validating environment variables...');
    
    this.validationResults = [];
    this.isValid = true;

    for (const envVar of REQUIRED_ENV_VARS) {
      const result = this.validateVariable(envVar);
      this.validationResults.push(result);
      
      if (!result.isValid) {
        this.isValid = false;
      }
    }

    this.logResults();
    return {
      isValid: this.isValid,
      results: this.validationResults,
      missingRequired: this.validationResults.filter(r => !r.isValid && r.required),
      warnings: this.validationResults.filter(r => r.warning)
    };
  }

  validateVariable(envVar) {
    const value = process.env[envVar.name];
    const result = {
      name: envVar.name,
      description: envVar.description,
      required: envVar.required,
      isValid: true,
      warning: null,
      error: null,
      hasValue: !!value
    };

    // Check if required variable is missing
    if (envVar.required && !value) {
      result.isValid = false;
      result.error = `Required environment variable ${envVar.name} is not set`;
      return result;
    }

    // Check if optional variable is missing but has default
    if (!envVar.required && !value && envVar.default) {
      result.warning = `Using default value for ${envVar.name}: ${envVar.default}`;
      return result;
    }

    // Skip further validation if variable is not set and not required
    if (!value) {
      return result;
    }

    // Check minimum length
    if (envVar.minLength && value.length < envVar.minLength) {
      result.isValid = false;
      result.error = `${envVar.name} must be at least ${envVar.minLength} characters long`;
      return result;
    }

    // Additional validation for specific variables
    switch (envVar.name) {
      case 'COGNITO_USER_POOL_ID':
        if (!value.match(/^[a-zA-Z0-9-_]+$/)) {
          result.warning = `${envVar.name} format may be invalid`;
        }
        break;
      case 'API_KEY_ENCRYPTION_SECRET_ARN':
      case 'DB_SECRET_ARN':
        if (!value.includes('arn:aws:secretsmanager:')) {
          result.warning = `${envVar.name} does not appear to be a valid Secrets Manager ARN`;
        }
        break;
      case 'WEBAPP_AWS_REGION':
        if (!value.match(/^[a-z0-9-]+$/)) {
          result.warning = `${envVar.name} format may be invalid`;
        }
        break;
    }

    return result;
  }

  logResults() {
    console.log('\n📋 Environment Variable Validation Results:');
    console.log('=' .repeat(50));

    let validCount = 0;
    let warningCount = 0;
    let errorCount = 0;

    for (const result of this.validationResults) {
      const status = result.isValid ? '✅' : '❌';
      const valueStatus = result.hasValue ? 
        (result.required ? '[SET]' : '[SET]') : 
        (result.required ? '[MISSING]' : '[OPTIONAL]');
      
      console.log(`${status} ${result.name} ${valueStatus}`);
      
      if (result.error) {
        console.log(`   ❌ Error: ${result.error}`);
        errorCount++;
      } else if (result.warning) {
        console.log(`   ⚠️  Warning: ${result.warning}`);
        warningCount++;
      } else {
        validCount++;
      }
    }

    console.log('=' .repeat(50));
    console.log(`📊 Summary: ${validCount} valid, ${warningCount} warnings, ${errorCount} errors`);
    
    if (this.isValid) {
      console.log('✅ All required environment variables are configured correctly');
    } else {
      console.log('❌ Some required environment variables are missing or invalid');
    }
    console.log('');
  }

  getEnvironmentSummary() {
    return {
      valid: this.validationResults.filter(r => r.isValid).length,
      warnings: this.validationResults.filter(r => r.warning).length,
      errors: this.validationResults.filter(r => !r.isValid).length,
      total: this.validationResults.length
    };
  }
}

// Export singleton instance
module.exports = new EnvironmentValidator();