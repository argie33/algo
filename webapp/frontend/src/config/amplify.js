import { Amplify } from 'aws-amplify';
import { AWS_CONFIG, FEATURES, IS_DEVELOPMENT } from './environment';

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
export function configureAmplify() {
  try {
    const amplifyConfig = getAmplifyConfig();
    const cognitoConfig = getCognitoConfig();
    
    console.log('🔧 Configuring Amplify with centralized config:', {
      userPoolId: cognitoConfig.userPoolId ? `${cognitoConfig.userPoolId.substring(0, 15)}...` : 'null',
      clientId: cognitoConfig.userPoolClientId ? `${cognitoConfig.userPoolClientId.substring(0, 8)}...` : 'null',
      region: cognitoConfig.region,
      authEnabled: FEATURES.authentication.enabled,
      cognitoEnabled: FEATURES.authentication.methods.cognito
    });
    
    // Check if authentication is required and properly configured
    if (!FEATURES.authentication.enabled) {
      console.warn('⚠️ Authentication is disabled via feature flags');
      return false;
    }
    
    if (!FEATURES.authentication.methods.cognito) {
      console.warn('⚠️ Cognito authentication is disabled via feature flags');
      return false;
    }
    
    if (!isCognitoConfigured()) {
      console.error('❌ Cognito REQUIRED - AWS deployment must have valid Cognito configuration');
      console.error('Set VITE_COGNITO_USER_POOL_ID and VITE_COGNITO_CLIENT_ID environment variables');
      
      // In production, fail fast
      if (!IS_DEVELOPMENT) {
        throw new Error('Cognito configuration required for production deployment');
      } else {
        console.warn('⚠️ Development mode - continuing without Cognito authentication');
        return false;
      }
    } else {
      console.log('✅ Cognito configured with valid AWS values');
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