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
          oauth: {
            domain:
              runtimeConfig.USER_POOL_DOMAIN ||
              import.meta.env.VITE_COGNITO_DOMAIN ||
              "dummy-domain",
            scopes: ["email", "profile", "openid"],
            redirectSignIn:
              import.meta.env.VITE_COGNITO_REDIRECT_SIGN_IN ||
              (typeof window !== "undefined" ? window.location.origin : ""),
            redirectSignOut:
              import.meta.env.VITE_COGNITO_REDIRECT_SIGN_OUT ||
              (typeof window !== "undefined" ? window.location.origin : ""),
            responseType: "code",
          },
          username: true,
          email: true,
        },
      },
    },
  };
};

// Configure Amplify
export function configureAmplify() {
  try {
    const config = getAmplifyConfig();
    const runtimeConfig = getRuntimeConfig();

    console.log("🔧 [AMPLIFY CONFIG] Configuration details:", {
      userPoolId: config.Auth.Cognito.userPoolId,
      clientId: config.Auth.Cognito.userPoolClientId,
      domain: config.Auth.Cognito.loginWith.oauth.domain,
      runtimeConfigAvailable: !!Object.keys(runtimeConfig).length,
      isCognitoConfigured: isCognitoConfigured(),
    });

    if (!isCognitoConfigured()) {
      console.warn(
        "⚠️  Cognito not configured - using dummy values for development"
      );
      console.log("Environment variables needed:");
      console.log("- VITE_COGNITO_USER_POOL_ID");
      console.log("- VITE_COGNITO_CLIENT_ID");
      console.log("- VITE_COGNITO_DOMAIN");
      console.log("Or set runtime config in window.__CONFIG__");
    }

    Amplify.configure(config);
    console.log("✅ Amplify configured successfully");
  } catch (error) {
    console.error("❌ Failed to configure Amplify:", error);
  }
}

export { isCognitoConfigured, getAmplifyConfig };
export default getAmplifyConfig;
