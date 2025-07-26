import { Amplify } from 'aws-amplify';
import { AWS_CONFIG, FEATURES, IS_DEVELOPMENT } from './environment';
import configurationService from '../services/configurationService';

// Check if Cognito is configured
const isCognitoConfigured = () => {
  const { userPoolId, clientId } = AWS_CONFIG.cognito;
  
  const isValid = !!(userPoolId && 
                    clientId && 
                    userPoolId !== '' && 
                    clientId !== '' &&
                    userPoolId !== 'us-east-1_DUMMY' &&
                    clientId !== 'dummy-client-id' &&
                    userPoolId !== 'undefined' &&
                    clientId !== 'undefined' &&
                    userPoolId !== null &&
                    clientId !== null);
  
  console.log('Cognito config check:', { 
    isValid, 
    userPoolId: userPoolId ? `${userPoolId.substring(0, 15)}...` : 'null',
    clientId: clientId ? `${clientId.substring(0, 8)}...` : 'null'
  });
  
  return isValid;
};

// Get Cognito configuration from centralized config
const getCognitoConfig = () => {
  return {
    userPoolId: AWS_CONFIG.cognito.userPoolId,
    userPoolClientId: AWS_CONFIG.cognito.clientId,
    region: AWS_CONFIG.region,
    domain: AWS_CONFIG.cognito.domain,
    redirectSignIn: AWS_CONFIG.cognito.redirectSignIn,
    redirectSignOut: AWS_CONFIG.cognito.redirectSignOut
  };
};

// Amplify configuration
const getAmplifyConfig = () => {
  const cognitoConfig = getCognitoConfig();
  
  return {
    Auth: {
      Cognito: {
        userPoolId: cognitoConfig.userPoolId,
        userPoolClientId: cognitoConfig.userPoolClientId,
        region: cognitoConfig.region,
        signUpVerificationMethod: 'code',
        loginWith: {
          oauth: (cognitoConfig.domain && 
                 cognitoConfig.domain !== '' && 
                 cognitoConfig.domain !== 'undefined') ? {
            domain: cognitoConfig.domain,
            scopes: ['email', 'profile', 'openid'],
            redirectSignIn: cognitoConfig.redirectSignIn,
            redirectSignOut: cognitoConfig.redirectSignOut,
            responseType: 'code'
          } : undefined,
          username: true,
          email: true
        }
      }
    }
  };
};

// Configure Amplify
export async function configureAmplify() {
  try {
    console.log('🔧 Starting Amplify configuration...');
    
    // Use the new configuration service for robust configuration loading
    const cognitoConfig = await configurationService.getCognitoConfig();
    const isAuthConfigured = await configurationService.isAuthenticationConfigured();
    
    console.log('🔍 Configuration check results:', {
      isAuthConfigured,
      userPoolId: cognitoConfig.userPoolId ? `${cognitoConfig.userPoolId.substring(0, 15)}...` : 'null',
      clientId: cognitoConfig.clientId ? `${cognitoConfig.clientId.substring(0, 8)}...` : 'null',
      region: cognitoConfig.region
    });
    
    if (!isAuthConfigured) {
      const detailedError = {
        message: 'Authentication not properly configured',
        userPoolId: cognitoConfig.userPoolId,
        clientId: cognitoConfig.clientId,
        region: cognitoConfig.region,
        troubleshooting: [
          'Check CloudFormation stack deployment status',
          'Verify UserPool and UserPoolClient resources are created',
          'Confirm CloudFormation outputs are being loaded',
          'Check network connectivity to CloudFormation API'
        ]
      };
      console.error('❌ AUTHENTICATION CONFIGURATION FAILED:', detailedError);
      return { success: false, reason: 'Authentication not configured', details: detailedError };
    }
    
    const amplifyConfig = {
      Auth: {
        Cognito: {
          userPoolId: cognitoConfig.userPoolId,
          userPoolClientId: cognitoConfig.clientId,
          region: cognitoConfig.region,
          signUpVerificationMethod: 'code',
          loginWith: {
            oauth: (cognitoConfig.domain && 
                   cognitoConfig.domain !== '' && 
                   cognitoConfig.domain !== 'undefined') ? {
              domain: cognitoConfig.domain,
              scopes: ['email', 'profile', 'openid'],
              redirectSignIn: cognitoConfig.redirectSignIn,
              redirectSignOut: cognitoConfig.redirectSignOut,
              responseType: 'code'
            } : undefined,
            username: true,
            email: true
          }
        }
      }
    };
    
    console.log('🔧 Configuring Amplify with robust config service:', {
      userPoolId: cognitoConfig.userPoolId ? `${cognitoConfig.userPoolId.substring(0, 15)}...` : 'null',
      clientId: cognitoConfig.clientId ? `${cognitoConfig.clientId.substring(0, 8)}...` : 'null',
      region: cognitoConfig.region,
      authEnabled: FEATURES.authentication.enabled,
      cognitoEnabled: FEATURES.authentication.methods.cognito
    });
    
    // Check if authentication is required and properly configured
    if (!FEATURES.authentication.enabled) {
      console.log('🔒 Authentication is disabled in features');
      return { success: true, reason: 'Authentication disabled by feature flag' };
    }
    
    if (!FEATURES.authentication.methods.cognito) {
      console.log('🔒 Cognito authentication is disabled in features');
      return { success: true, reason: 'Cognito disabled by feature flag' };
    }
    
    try {
      Amplify.configure(amplifyConfig);
      console.log('✅ Amplify configured successfully');
      return { success: true };
    } catch (amplifyError) {
      const detailedError = {
        message: 'Amplify.configure() failed',
        originalError: amplifyError.message,
        config: {
          userPoolId: amplifyConfig.Auth.Cognito.userPoolId,
          userPoolClientId: amplifyConfig.Auth.Cognito.userPoolClientId,
          region: amplifyConfig.Auth.Cognito.region
        },
        troubleshooting: [
          'Verify Cognito User Pool exists in AWS',
          'Check User Pool Client configuration',
          'Confirm region matches AWS deployment',
          'Validate Cognito service permissions'
        ]
      };
      console.error('❌ AMPLIFY CONFIGURATION FAILED:', detailedError);
      throw new Error(`Amplify configuration failed: ${amplifyError.message}`);
    }
  } catch (error) {
    const detailedError = {
      message: 'Critical authentication setup failure',
      originalError: error.message,
      stack: error.stack,
      troubleshooting: [
        'Check CloudFormation deployment status',
        'Verify all AWS resources are created',
        'Confirm configuration service is working',
        'Check network connectivity to AWS services'
      ]
    };
    console.error('❌ CRITICAL AUTHENTICATION FAILURE:', detailedError);
    
    // Don't allow app to continue without proper AWS authentication in production
    if (!IS_DEVELOPMENT) {
      throw error; // Fail fast on production deployment
    }
    
    console.warn('⚠️ Development mode - authentication failure will prevent app functionality');
    return { success: false, error: detailedError };
  }
}

export { isCognitoConfigured, getCognitoConfig };
export default getAmplifyConfig;