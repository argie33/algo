// Mock AWS Amplify for build compatibility
export const Amplify = {
  configure: (config) => {
    console.log("Mock Amplify configured with:", config);
  }
};

export const Auth = {
  signIn: async () => ({ isSignedIn: false }),
  signUp: async () => ({ isSignUpComplete: false }),
  signOut: async () => ({}),
  getCurrentUser: async () => { throw new Error("No user authenticated"); },
  fetchAuthSession: async () => ({ tokens: null }),
  confirmSignUp: async () => ({ isSignUpComplete: true }),
  resendSignUpCode: async () => ({}),
  resetPassword: async () => ({ nextStep: { resetPasswordStep: "CONFIRM_RESET_PASSWORD" } }),
  confirmResetPassword: async () => ({})
};

export const CookieStorage = class MockCookieStorage {};
export const defaultStorage = {};

// Mock providers
export const CognitoUserPoolsTokenProvider = class MockTokenProvider {};
export const cognitoCredentialsProvider = {};

export default Amplify;