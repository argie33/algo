import { Amplify } from 'aws-amplify';

// Amplify configuration
const amplifyConfig = {
  Auth: {
    Cognito: {
      userPoolId: import.meta.env.VITE_COGNITO_USER_POOL_ID,
      userPoolClientId: import.meta.env.VITE_COGNITO_CLIENT_ID,
      region: import.meta.env.VITE_AWS_REGION || 'us-east-1',
      signUpVerificationMethod: 'code',
      loginWith: {
        oauth: {
          domain: import.meta.env.VITE_COGNITO_DOMAIN,
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
    Amplify.configure(amplifyConfig);
    console.log('Amplify configured successfully');
  } catch (error) {
    console.error('Failed to configure Amplify:', error);
  }
}

export default amplifyConfig;