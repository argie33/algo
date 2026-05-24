/**
 * Development Authentication Service
 * Mirrors the AWS Amplify auth API for local development when Cognito is not configured.
 * SECURITY: Uses sessionStorage (cleared on tab close) instead of localStorage.
 * Dev auth is disabled at build time in production (import.meta.env.PROD).
 */

const STORAGE_KEY = 'devAuth_users';
const SESSION_KEY = 'devAuth_session';

// Default dev user — always available in development
// Password is configurable via VITE_DEV_AUTH_PASSWORD env var (set in .env.local as VITE_DEV_AUTH_PASSWORD)
const DEV_PASSWORD = import.meta.env.VITE_DEV_AUTH_PASSWORD || 'Admin123!';

const DEV_USER = {
  username: 'dev-admin',
  password: DEV_PASSWORD,
  email: 'admin@dev.local',
  firstName: 'Dev',
  lastName: 'Admin',
  role: 'admin',
  groups: ['admin'],
  isAdmin: true,
  confirmed: true,
};

function getUsers() {
  try {
    return JSON.parse(sessionStorage.getItem(STORAGE_KEY) || '{}');
  } catch {
    return {};
  }
}

function saveUsers(users) {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(users));
}

function getSession() {
  try {
    return JSON.parse(sessionStorage.getItem(SESSION_KEY) || 'null');
  } catch {
    return null;
  }
}

function saveSession(session) {
  if (session) {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
  } else {
    sessionStorage.removeItem(SESSION_KEY);
  }
}

function makeTokens(username) {
  const now = Date.now();
  const payload = { sub: username, iat: Math.floor(now / 1000), exp: Math.floor(now / 1000) + 3600 };
  const encoded = btoa(JSON.stringify(payload));
  const token = `devToken.${encoded}.sig`;
  return {
    accessToken: token,
    idToken: token,
    refreshToken: `devRefresh.${encoded}`,
  };
}

const devAuth = {
  async getCurrentUser() {
    let session = getSession();
    // Auto-initialize dev user in development if no session exists
    if (!session) {
      const sessionData = {
        username: DEV_USER.username,
        email: DEV_USER.email,
        firstName: DEV_USER.firstName,
        lastName: DEV_USER.lastName
      };
      saveSession(sessionData);
      session = sessionData;
    }
    // Dev user is always admin
    return {
      username: session.username,
      userId: session.username,
      email: session.email,
      firstName: session.firstName,
      lastName: session.lastName,
      role: 'admin',
      groups: ['admin'],
      isAdmin: true,
      signInDetails: { loginId: session.email },
    };
  },

  async fetchAuthSession() {
    let session = getSession();
    // Auto-initialize dev user in development if no session exists
    if (!session) {
      const sessionData = {
        username: DEV_USER.username,
        email: DEV_USER.email,
        firstName: DEV_USER.firstName,
        lastName: DEV_USER.lastName
      };
      saveSession(sessionData);
      session = sessionData;
    }
    return { tokens: makeTokens(session.username) };
  },

  async signIn(username, password) {
    // Check default dev user first
    if (username === DEV_USER.username && password === DEV_USER.password) {
      const sessionData = { username: DEV_USER.username, email: DEV_USER.email, firstName: DEV_USER.firstName, lastName: DEV_USER.lastName };
      saveSession(sessionData);
      return {
        success: true,
        tokens: makeTokens(username),
        user: {
          username: DEV_USER.username,
          userId: DEV_USER.username,
          email: DEV_USER.email,
          firstName: DEV_USER.firstName,
          lastName: DEV_USER.lastName,
          role: 'admin',
          groups: ['admin'],
          isAdmin: true,
        },
      };
    }

    // Check registered users
    const users = getUsers();
    const user = users[username];
    if (!user) throw Object.assign(new Error('User not found'), { name: 'NotAuthorizedException' });
    if (user.password !== password) throw Object.assign(new Error('Incorrect password'), { name: 'NotAuthorizedException' });
    if (!user.confirmed) throw Object.assign(new Error('Account not confirmed'), { name: 'UserNotConfirmedException' });

    const sessionData = { username, email: user.email, firstName: user.firstName, lastName: user.lastName };
    saveSession(sessionData);
    return {
      success: true,
      tokens: makeTokens(username),
      user: {
        username,
        userId: username,
        email: user.email,
        firstName: user.firstName,
        lastName: user.lastName,
        role: 'admin',
        groups: ['admin'],
        isAdmin: true,
      },
    };
  },

  async signUp(username, password, email, firstName, lastName) {
    const users = getUsers();
    if (users[username]) throw Object.assign(new Error('Username taken'), { name: 'UsernameExistsException' });
    users[username] = { password, email, firstName, lastName, confirmed: false };
    saveUsers(users);
    return { isSignUpComplete: false, nextStep: { signUpStep: 'CONFIRM_SIGN_UP' } };
  },

  async confirmSignUp(username, _code) {
    const users = getUsers();
    if (!users[username]) throw new Error('User not found');
    users[username].confirmed = true;
    saveUsers(users);
    return { isSignUpComplete: true };
  },

  async resetPassword(username) {
    const users = getUsers();
    const isKnown = users[username] || username === DEV_USER.username;
    if (!isKnown) throw new Error('User not found');
    return { nextStep: { resetPasswordStep: 'CONFIRM_RESET_PASSWORD_WITH_CODE', codeDeliveryDetails: { deliveryMedium: 'EMAIL' } } };
  },

  async confirmResetPassword(username, _code, newPassword) {
    if (username === DEV_USER.username) return; // Can't change built-in dev user
    const users = getUsers();
    if (!users[username]) throw new Error('User not found');
    users[username].password = newPassword;
    saveUsers(users);
  },

  async signOut() {
    saveSession(null);
  },
};

export default devAuth;
