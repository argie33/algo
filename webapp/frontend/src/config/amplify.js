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
    // Use the new configuration service for robust configuration loading
    const cognitoConfig = await configurationService.getCognitoConfig();
    const isAuthConfigured = await configurationService.isAuthenticationConfigured();
    
    if (!isAuthConfigured) {
      console.warn('⚠️ Authentication not properly configured - skipping Amplify setup');
      return { success: false, reason: 'Authentication not configured' };
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
    
    Amplify.configure(amplifyConfig);
    console.log('✅ Amplify configured successfully');
    return true;
  } catch (error) {
    console.error('❌ Failed to configure Amplify:', error);
    
    // Don't allow app to continue without proper AWS authentication in production
    if (!IS_DEVELOPMENT) {
      throw error; // Fail fast on production deployment
    }
    
    console.warn('⚠️ Development mode fallback - authentication disabled');
    return false;
  }
}

export { isCognitoConfigured, getCognitoConfig };
export default getAmplifyConfig;