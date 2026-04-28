/**
 * Development Authentication Service
 * Mirrors the AWS Amplify auth API for local development when Cognito is not configured.
 * Stores users in localStorage for persistence across page reloads.
 */

const STORAGE_KEY = 'devAuth_users';
const SESSION_KEY = 'devAuth_session';

// Default dev user — always available in development
const DEV_USER = {
  username: 'admin',
  password: 'Admin123!',
  email: 'admin@localhost.dev',
  firstName: 'Dev',
  lastName: 'Admin',
  confirmed: true,
};

function getUsers() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
  } catch {
    return {};
  }
}

function saveUsers(users) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(users));
}

function getSession() {
  try {
    return JSON.parse(localStorage.getItem(SESSION_KEY) || 'null');
  } catch {
    return null;
  }
}

function saveSession(session) {
  if (session) {
    localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  } else {
    localStorage.removeItem(SESSION_KEY);
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
    const session = getSession();
    if (!session) throw new Error('No current user');
    return {
      username: session.username,
      userId: session.username,
      email: session.email,
      firstName: session.firstName,
      lastName: session.lastName,
      signInDetails: { loginId: session.email },
    };
  },

  async fetchAuthSession() {
    const session = getSession();
    if (!session) throw new Error('No active session');
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
        user: { username: DEV_USER.username, userId: DEV_USER.username, email: DEV_USER.email, firstName: DEV_USER.firstName, lastName: DEV_USER.lastName },
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
      user: { username, userId: username, email: user.email, firstName: user.firstName, lastName: user.lastName },
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
