/**
 * Database Configuration Validator
 * Validates and fixes database configuration issues
 */

const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');

class DatabaseConfigValidator {
  constructor() {
    this.secretsClient = new SecretsManagerClient({ 
      region: process.env.AWS_REGION || 'us-east-1' 
    });
  }

  /**
   * Validate current database configuration
   */
  validateConfig() {
    const validation = {
      isValid: false,
      errors: [],
      warnings: [],
      config: null,
      suggestions: []
    };

    // Check environment variables
    const envVars = {
      DB_HOST: process.env.DB_HOST,
      DB_USER: process.env.DB_USER,
      DB_PASSWORD: process.env.DB_PASSWORD,
      DB_NAME: process.env.DB_NAME,
      DB_SECRET_ARN: process.env.DB_SECRET_ARN
    };

    // Check for direct database credentials
    if (envVars.DB_HOST && envVars.DB_USER && envVars.DB_PASSWORD) {
      validation.isValid = true;
      validation.config = {
        method: 'environment_variables',
        host: envVars.DB_HOST,
        user: envVars.DB_USER,
        database: envVars.DB_NAME || 'financial_dashboard',
        hasPassword: !!envVars.DB_PASSWORD
      };
      validation.suggestions.push('Direct environment variables detected - ensure they are properly secured');
    }

    // Check Secrets Manager ARN
    if (envVars.DB_SECRET_ARN) {
      if (envVars.DB_SECRET_ARN.includes('${') || envVars.DB_SECRET_ARN === '${DB_SECRET_ARN}') {
        validation.errors.push('DB_SECRET_ARN contains placeholder values - not properly substituted during deployment');
        validation.suggestions.push('Update CloudFormation template to properly substitute DB_SECRET_ARN parameter');
      } else if (envVars.DB_SECRET_ARN.startsWith('arn:aws:secretsmanager:')) {
        validation.config = {
          method: 'secrets_manager',
          secretArn: envVars.DB_SECRET_ARN
        };
        if (!validation.isValid) {
          validation.isValid = true;
        }
      } else {
        validation.errors.push('DB_SECRET_ARN does not appear to be a valid AWS Secrets Manager ARN');
      }
    }

    // No valid configuration found
    if (!validation.isValid) {
      validation.errors.push('No valid database configuration found');
      validation.suggestions.push('Set either DB_HOST/DB_USER/DB_PASSWORD environment variables or valid DB_SECRET_ARN');
    }

    return validation;
  }

  /**
   * Test database connection with current configuration
   */
  async testConnection() {
    try {
      const { query } = require('./database');
      const result = await query('SELECT 1 as test, NOW() as timestamp');
      return {
        success: true,
        timestamp: result[0]?.timestamp,
        responseTime: Date.now()
      };
    } catch (error) {
      return {
        success: false,
        error: error.message,
        suggestions: this.getDiagnosticSuggestions(error)
      };
    }
  }

  /**
   * Generate diagnostic suggestions based on error
   */
  getDiagnosticSuggestions(error) {
    const suggestions = [];
    
    if (error.message.includes('getaddrinfo ENOTFOUND')) {
      suggestions.push('Database host cannot be resolved - check DB_HOST value');
      suggestions.push('Ensure RDS instance is running and accessible from Lambda');
    }
    
    if (error.message.includes('authentication failed')) {
      suggestions.push('Database credentials are incorrect - verify DB_USER and DB_PASSWORD');
      suggestions.push('Check Secrets Manager secret contains correct credentials');
    }
    
    if (error.message.includes('timeout')) {
      suggestions.push('Database connection timeout - check security groups and network connectivity');
      suggestions.push('Ensure Lambda is in VPC with access to RDS subnet');
    }
    
    if (error.message.includes('unavailable')) {
      suggestions.push('Using stub configuration - database not properly configured');
      suggestions.push('Set proper environment variables or DB_SECRET_ARN');
    }

    return suggestions;
  }

  /**
   * Generate configuration recommendations
   */
  getConfigurationRecommendations() {
    const recommendations = [];

    // Production recommendations
    if (process.env.NODE_ENV === 'production') {
      recommendations.push({
        priority: 'high',
        category: 'security',
        message: 'Use AWS Secrets Manager for production database credentials',
        action: 'Set DB_SECRET_ARN instead of plain text environment variables'
      });
    }

    // Performance recommendations
    recommendations.push({
      priority: 'medium',
      category: 'performance',
      message: 'Configure connection pooling for optimal performance',
      action: 'Ensure max pool size is appropriate for Lambda concurrency'
    });

    // Monitoring recommendations
    recommendations.push({
      priority: 'medium',
      category: 'monitoring',
      message: 'Enable database performance monitoring',
      action: 'Configure CloudWatch metrics for RDS instance'
    });

    return recommendations;
  }

  /**
   * Generate deployment checklist
   */
  getDeploymentChecklist() {
    return [
      {
        item: 'RDS instance is running and accessible',
        check: 'aws rds describe-db-instances --db-instance-identifier your-db-instance'
      },
      {
        item: 'Security groups allow Lambda to connect to RDS',
        check: 'Verify Lambda security group has outbound rule for RDS port 5432'
      },
      {
        item: 'Secrets Manager secret exists and contains correct format',
        check: 'aws secretsmanager get-secret-value --secret-id your-secret-arn'
      },
      {
        item: 'Lambda has IAM permissions to read Secrets Manager',
        check: 'Verify Lambda execution role has secretsmanager:GetSecretValue permission'
      },
      {
        item: 'Environment variables are properly set',
        check: 'Check Lambda environment variables in AWS Console'
      }
    ];
  }
}

module.exports = DatabaseConfigValidator;