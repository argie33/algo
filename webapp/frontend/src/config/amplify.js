import { Amplify } from 'aws-amplify';

// Check if Cognito is configured
const isCognitoConfigured = () => {
  const userPoolId = import.meta.env.VITE_COGNITO_USER_POOL_ID;
  const clientId = import.meta.env.VITE_COGNITO_CLIENT_ID;
  
  // Check if we have real values (not dummy values)
  return !!(userPoolId && 
           clientId && 
           userPoolId !== '' && 
           clientId !== '' &&
           userPoolId !== 'us-east-1_DUMMY' &&
           clientId !== 'dummy-client-id');
};

// Amplify configuration
const amplifyConfig = {
  Auth: {
    Cognito: {
      userPoolId: import.meta.env.VITE_COGNITO_USER_POOL_ID || 'us-east-1_DUMMY',
      userPoolClientId: import.meta.env.VITE_COGNITO_CLIENT_ID || 'dummy-client-id',
      region: import.meta.env.VITE_AWS_REGION || 'us-east-1',
      signUpVerificationMethod: 'code',
      loginWith: {
        oauth: {
          domain: import.meta.env.VITE_COGNITO_DOMAIN || 'dummy-domain',
          scopes: ['email', 'profile', 'openid'],
          redirectSignIn: import.meta.env.VITE_COGNITO_REDIRECT_SIGN_IN || window.location.origin,
          redirectSignOut: import.meta.env.VITE_COGNITO_REDIRECT_SIGN_OUT || window.location.origin,
          responseType: 'code'
        },
        username: true,
        email: true
      }
    }
  }
};

// Configure Amplify
export function configureAmplify() {
  try {
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

export { isCognitoConfigured };
export default amplifyConfig;