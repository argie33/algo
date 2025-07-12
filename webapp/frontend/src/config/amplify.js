import { Amplify } from 'aws-amplify';

// Check if Cognito is configured
const isCognitoConfigured = () => {
  // First check runtime config
  const runtimeConfig = window.__CONFIG__?.COGNITO;
  if (runtimeConfig?.USER_POOL_ID && runtimeConfig?.CLIENT_ID) {
    const isValid = !!(runtimeConfig.USER_POOL_ID !== 'us-east-1_DUMMY' && 
                      runtimeConfig.CLIENT_ID !== 'dummy-client-id' &&
                      runtimeConfig.USER_POOL_ID !== 'undefined' &&
                      runtimeConfig.CLIENT_ID !== 'undefined');
    console.log('Runtime Cognito config check:', { isValid, userPoolId: runtimeConfig.USER_POOL_ID, clientId: runtimeConfig.CLIENT_ID });
    return isValid;
  }
  
  // Fallback to environment variables
  const userPoolId = import.meta.env.VITE_COGNITO_USER_POOL_ID;
  const clientId = import.meta.env.VITE_COGNITO_CLIENT_ID;
  
  const isValid = !!(userPoolId && 
                    clientId && 
                    userPoolId !== '' && 
                    clientId !== '' &&
                    userPoolId !== 'us-east-1_DUMMY' &&
                    clientId !== 'dummy-client-id' &&
                    userPoolId !== 'undefined' &&
                    clientId !== 'undefined');
  
  console.log('Environment Cognito config check:', { isValid, userPoolId, clientId });
  return isValid;
};

// Get configuration from runtime config or environment variables
const getCognitoConfig = () => {
  const runtimeConfig = window.__CONFIG__?.COGNITO;
  
  return {
    userPoolId: runtimeConfig?.USER_POOL_ID || import.meta.env.VITE_COGNITO_USER_POOL_ID || 'us-east-1_DUMMY',
    userPoolClientId: runtimeConfig?.CLIENT_ID || import.meta.env.VITE_COGNITO_CLIENT_ID || 'dummy-client-id',
    region: runtimeConfig?.REGION || import.meta.env.VITE_AWS_REGION || 'us-east-1',
    domain: runtimeConfig?.DOMAIN || import.meta.env.VITE_COGNITO_DOMAIN || '',
    redirectSignIn: runtimeConfig?.REDIRECT_SIGN_IN || import.meta.env.VITE_COGNITO_REDIRECT_SIGN_IN || window.location.origin,
    redirectSignOut: runtimeConfig?.REDIRECT_SIGN_OUT || import.meta.env.VITE_COGNITO_REDIRECT_SIGN_OUT || window.location.origin
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
    
    console.log('🔧 Configuring Amplify with:', {
      userPoolId: cognitoConfig.userPoolId,
      clientId: cognitoConfig.userPoolClientId,
      region: cognitoConfig.region
    });
    
    if (!isCognitoConfigured()) {
      console.warn('⚠️  Cognito not configured - using dummy values for development');
      console.warn('App will work but authentication will be disabled');
    } else {
      console.log('✅ Cognito configured with real values');
    }
    
    Amplify.configure(amplifyConfig);
    console.log('✅ Amplify configured successfully');
    return true;
  } catch (error) {
    console.error('❌ Failed to configure Amplify:', error);
    console.warn('⚠️  Continuing without Amplify - authentication will be disabled');
    return false;
  }
}

export { isCognitoConfigured, getCognitoConfig };
export default getAmplifyConfig;