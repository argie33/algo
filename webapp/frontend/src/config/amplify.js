import { Amplify } from "aws-amplify";

// Get runtime configuration values
const getRuntimeConfig = () => {
  return typeof window !== "undefined" && window.__CONFIG__
    ? window.__CONFIG__
    : {};
};

// Check if Cognito is configured
const isCognitoConfigured = () => {
  const runtimeConfig = getRuntimeConfig();
  const userPoolId =
    runtimeConfig.USER_POOL_ID || import.meta.env.VITE_COGNITO_USER_POOL_ID;
  const clientId =
    runtimeConfig.USER_POOL_CLIENT_ID || import.meta.env.VITE_COGNITO_CLIENT_ID;

  // Check if we have real values (not dummy values)
  return !!(
    userPoolId &&
    clientId &&
    userPoolId !== "" &&
    clientId !== "" &&
    userPoolId !== "us-east-1_DUMMY" &&
    clientId !== "dummy-client-id"
  );
};

// Amplify configuration with runtime config support
const getAmplifyConfig = () => {
  const runtimeConfig = getRuntimeConfig();
  const userPoolId = runtimeConfig.USER_POOL_ID || import.meta.env.VITE_COGNITO_USER_POOL_ID || "us-east-1_DUMMY";
  const region = userPoolId.split('_')[0] || (import.meta.env.VITE_AWS_REGION || "us-east-1");
  const clientId = runtimeConfig.USER_POOL_CLIENT_ID || import.meta.env.VITE_COGNITO_CLIENT_ID || "dummy-client-id";

  // Amplify Auth config for username/password authentication
  // OAuth is not required for this flow - users sign in with username/password directly
  return {
    Auth: {
      Cognito: {
        userPoolId: userPoolId,
        userPoolClientId: clientId,
        region: region,
        signUpVerificationMethod: 'code',
      },
    },
  };
};

// Configure Amplify
export function configureAmplify() {
  try {
    const config = getAmplifyConfig();
    const _runtimeConfig = getRuntimeConfig();

    Amplify.configure(config);
  } catch (error) {
    console.error("❌ Failed to configure Amplify:", error);
  }
}

export { isCognitoConfigured, getAmplifyConfig };
export default getAmplifyConfig;

