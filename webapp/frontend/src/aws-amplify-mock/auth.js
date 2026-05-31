// Vitest mock for aws-amplify/auth (replaces real package in test environment)
const mockUser = { username: 'test@example.com', userId: 'mock-user-id' };

export const fetchAuthSession = async () => ({
  tokens: {
    accessToken: { payload: { 'cognito:groups': [] }, toString: () => 'mock-access-token' },
    idToken: { payload: { email: 'test@example.com' }, toString: () => 'mock-id-token' },
  },
  credentials: {},
  identityId: 'mock-identity-id',
  userSub: 'mock-user-sub',
});

export const signIn = async ({ username, password }) => ({
  isSignedIn: true,
  nextStep: { signInStep: 'DONE' },
});

export const signUp = async (params) => ({
  isSignUpComplete: false,
  userId: 'mock-user-id',
  nextStep: { signUpStep: 'CONFIRM_SIGN_UP', codeDeliveryDetails: {} },
});

export const confirmSignUp = async (params) => ({
  isSignUpComplete: true,
  nextStep: { signUpStep: 'DONE' },
});

export const resendSignUpCode = async (params) => ({
  destination: params.username,
  deliveryMedium: 'EMAIL',
  attributeName: 'email',
});

export const signOut = async () => {};

export const resetPassword = async (params) => ({
  isPasswordReset: false,
  nextStep: { resetPasswordStep: 'CONFIRM_RESET_PASSWORD_WITH_CODE', codeDeliveryDetails: {} },
});

export const confirmResetPassword = async (params) => {};

export const getCurrentUser = async () => mockUser;

export const confirmSignIn = async (params) => ({
  isSignedIn: true,
  nextStep: { signInStep: 'DONE' },
});

export const updatePassword = async (params) => {};

export const fetchUserAttributes = async () => ({
  email: 'test@example.com',
  sub: 'mock-user-sub',
});
