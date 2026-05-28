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

  return {
    Auth: {
      Cognito: {
        userPoolId:
          runtimeConfig.USER_POOL_ID ||
          import.meta.env.VITE_COGNITO_USER_POOL_ID ||
          "us-east-1_DUMMY",
        userPoolClientId:
          runtimeConfig.USER_POOL_CLIENT_ID ||
          import.meta.env.VITE_COGNITO_CLIENT_ID ||
          "dummy-client-id",
        region: import.meta.env.VITE_AWS_REGION || "us-east-1",
        signUpVerificationMethod: "code",
        loginWith: {
          username: true,
          email: true,
        },
        // CRITICAL: Cognito client only allows USER_PASSWORD_AUTH (not SRP)
        // This prevents Amplify from trying SRP first and getting a 400 error
        allowUserPasswordAuth: true,
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

