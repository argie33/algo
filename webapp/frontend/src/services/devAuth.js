// Stub: devAuth removed in cleanup. Use Cognito instead.
export default {
  getCurrentUser: async () => null,
  fetchAuthSession: async () => ({ tokens: null }),
  signIn: async () => ({ success: false, error: "Dev auth not available" }),
  signOut: async () => {},
  signUp: async () => ({ isSignUpComplete: false }),
  confirmSignUp: async () => ({ isSignUpComplete: false }),
  resetPassword: async () => ({ nextStep: null }),
  confirmResetPassword: async () => {},
};
