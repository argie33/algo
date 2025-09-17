// Mock AWS Amplify for test environment - avoid circular import
// Direct exports for common Cognito functions
export const signIn = () => Promise.resolve({});
export const signOut = () => Promise.resolve({});
export const getCurrentUser = () => Promise.resolve({});
export const fetchAuthSession = () => Promise.resolve({});
export const confirmSignUp = () => Promise.resolve({});
export const resendSignUpCode = () => Promise.resolve({});
export const resetPassword = () => Promise.resolve({});
export const confirmResetPassword = () => Promise.resolve({});

// Additional common exports
export const signUp = () => Promise.resolve({});
export const updateUserAttributes = () => Promise.resolve({});
export const deleteUserAttributes = () => Promise.resolve({});
export const verifyTOTPSetup = () => Promise.resolve({});
export const setUpTOTP = () => Promise.resolve({});
export const updateMFAPreference = () => Promise.resolve({});
export const fetchMFAPreference = () => Promise.resolve({});

// Default export
export default {
  signIn,
  signOut,
  getCurrentUser,
  fetchAuthSession,
  confirmSignUp,
  resendSignUpCode,
  resetPassword,
  confirmResetPassword,
  signUp,
  updateUserAttributes,
  deleteUserAttributes,
  verifyTOTPSetup,
  setUpTOTP,
  updateMFAPreference,
  fetchMFAPreference,
};