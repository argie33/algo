/**
 * AWS Amplify Auth Mock
 * NOTE: These mocks are no longer used since vite.config.js aliases were removed.
 * The real aws-amplify/auth from node_modules is used instead.
 * Keeping this file for backwards compatibility.
 */

export const signIn = async () => {
  throw new Error('AWS Amplify Auth is not configured');
};

export const confirmSignIn = async () => {
  throw new Error('AWS Amplify Auth is not configured');
};

export const signOut = async () => {
  throw new Error('AWS Amplify Auth is not configured');
};

export const signUp = async () => {
  throw new Error('AWS Amplify Auth is not configured');
};

export const confirmSignUp = async () => {
  throw new Error('AWS Amplify Auth is not configured');
};

export const getCurrentUser = async () => {
  throw new Error('AWS Amplify Auth is not configured');
};

export const fetchAuthSession = async () => {
  throw new Error('AWS Amplify Auth is not configured');
};

export const fetchUserAttributes = async () => {
  throw new Error('AWS Amplify Auth is not configured');
};

export const updateUserAttributes = async () => {
  throw new Error('AWS Amplify Auth is not configured');
};

export const resetPassword = async () => {
  throw new Error('AWS Amplify Auth is not configured');
};

export const confirmResetPassword = async () => {
  throw new Error('AWS Amplify Auth is not configured');
};

export const resendSignUpCode = async () => {
  throw new Error('AWS Amplify Auth is not configured');
};

export const autoSignIn = async () => {
  throw new Error('AWS Amplify Auth is not configured');
};

export const deleteUser = async () => {
  throw new Error('AWS Amplify Auth is not configured');
};

export const updatePassword = async () => {
  throw new Error('AWS Amplify Auth is not configured');
};

export default {
  signIn,
  confirmSignIn,
  signOut,
  signUp,
  confirmSignUp,
  getCurrentUser,
  fetchAuthSession,
  fetchUserAttributes,
  updateUserAttributes,
  resetPassword,
  confirmResetPassword,
  resendSignUpCode,
  autoSignIn,
  deleteUser,
  updatePassword,
};

