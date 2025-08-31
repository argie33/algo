// Development authentication service
// Simulates AWS Cognito functionality for development environment

const DEV_USERS_KEY = "dev_users";
const DEV_SESSION_KEY = "dev_session";
const DEV_PENDING_KEY = "dev_pending";

class DevAuthService {
  constructor() {
    this.users = this.loadUsers();
    this.session = this.loadSession();
    this.pendingVerifications = this.loadPendingVerifications();
    
    // Create default dev user if none exist
    this.ensureDevUser();
  }

  loadUsers() {
    const stored = localStorage.getItem(DEV_USERS_KEY);
    return stored ? JSON.parse(stored) : {};
  }

  saveUsers() {
    localStorage.setItem(DEV_USERS_KEY, JSON.stringify(this.users));
  }

  loadSession() {
    const stored = localStorage.getItem(DEV_SESSION_KEY);
    return stored ? JSON.parse(stored) : null;
  }

  saveSession(session) {
    this.session = session;
    localStorage.setItem(DEV_SESSION_KEY, JSON.stringify(session));
  }

  clearSession() {
    this.session = null;
    localStorage.removeItem(DEV_SESSION_KEY);
  }

  loadPendingVerifications() {
    const stored = localStorage.getItem(DEV_PENDING_KEY);
    return stored ? JSON.parse(stored) : {};
  }

  savePendingVerifications() {
    localStorage.setItem(
      DEV_PENDING_KEY,
      JSON.stringify(this.pendingVerifications)
    );
  }

  ensureDevUser() {
    // Create a default user for easy development testing
    if (Object.keys(this.users).length === 0) {
      const defaultUser = {
        username: 'devuser',
        email: 'argeropolos@gmail.com',
        firstName: 'Dev',
        lastName: 'User',
        password: 'password123',
        confirmed: true,
        createdAt: Date.now(),
      };
      
      this.users['devuser'] = defaultUser;
      this.saveUsers();
      
      console.log('🔧 DEV: Created default dev user');
      console.log('📧 Email: argeropolos@gmail.com');
      console.log('🔑 Username: devuser');
      console.log('🔒 Password: password123');
      console.log('✅ User can sign in with either email or username');
    }
  }

  generateVerificationCode() {
    return Math.floor(100000 + Math.random() * 900000).toString();
  }

  generateDevTokens(username) {
    const timestamp = Date.now();
    return {
      accessToken: `dev-access-${username}-${timestamp}`,
      idToken: `dev-id-${username}-${timestamp}`,
      refreshToken: `dev-refresh-${username}-${timestamp}`,
    };
  }

  async signUp(username, password, email, firstName, lastName) {
    // DEV: Simulating sign up

    // Check if user already exists
    if (this.users[username]) {
      throw new Error("UsernameExistsException: Username already exists");
    }

    // Check if email is already used
    const existingUser = Object.values(this.users).find(
      (user) => user.email === email
    );
    if (existingUser) {
      throw new Error("UsernameExistsException: Email already exists");
    }

    // Generate verification code
    const verificationCode = this.generateVerificationCode();

    // Store pending verification
    this.pendingVerifications[username] = {
      username,
      password,
      email,
      firstName,
      lastName,
      verificationCode,
      createdAt: Date.now(),
    };
    this.savePendingVerifications();

    // Simulate email being sent
    console.log("📧 DEV: Email verification code sent to", email);
    console.log("🔑 DEV: Verification code:", verificationCode);

    // In development, log the verification code to console
    console.log("📧 DEV AUTH: Verification code for", email, ":", verificationCode);
    console.log("🔑 DEV AUTH: Copy this code to complete registration");
    
    // Store dev code for debugging (non-production only)
    if (window.DEV_AUTH_DEBUG !== false) {
      window.lastDevCode = verificationCode;
      console.log("💡 DEV AUTH: Access code via window.lastDevCode");
    }
    
    // Show verification code in browser alert for easy access in development
    if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
      setTimeout(() => {
        alert(`🔑 DEV AUTH VERIFICATION CODE\n\nFor: ${email}\nCode: ${verificationCode}\n\nCopy this code to complete your registration.`);
      }, 100);
    }

    return {
      isSignUpComplete: false,
      nextStep: {
        signUpStep: "CONFIRM_SIGN_UP",
        codeDeliveryDetails: {
          deliveryMedium: "EMAIL",
          destination: email,
        },
      },
    };
  }

  async confirmSignUp(username, confirmationCode) {
    console.log("🔧 DEV: Confirming sign up for", username);

    const pending = this.pendingVerifications[username];
    if (!pending) {
      throw new Error("UserNotFoundException: User not found");
    }

    if (pending.verificationCode !== confirmationCode) {
      throw new Error("CodeMismatchException: Invalid verification code");
    }

    // Check if code is expired (5 minutes)
    if (Date.now() - pending.createdAt > 5 * 60 * 1000) {
      throw new Error("ExpiredCodeException: Verification code has expired");
    }

    // Create user account
    this.users[username] = {
      username,
      email: pending.email,
      firstName: pending.firstName,
      lastName: pending.lastName,
      password: pending.password, // In real app, this would be hashed
      confirmed: true,
      createdAt: Date.now(),
    };
    this.saveUsers();

    // Remove from pending
    delete this.pendingVerifications[username];
    this.savePendingVerifications();

    console.log("✅ DEV: User confirmed successfully");

    return {
      isSignUpComplete: true,
    };
  }

  async signIn(usernameOrEmail, password) {
    console.log("🔧 DEV: Signing in user", usernameOrEmail);

    // Try to find user by username first
    let user = this.users[usernameOrEmail];
    let actualUsername = usernameOrEmail;

    // If not found by username, try to find by email
    if (!user) {
      const userEntry = Object.entries(this.users).find(
        ([, userData]) => userData.email === usernameOrEmail
      );
      if (userEntry) {
        actualUsername = userEntry[0];
        user = userEntry[1];
        console.log("🔧 DEV: Found user by email, username is", actualUsername);
      }
    }

    if (!user) {
      throw new Error("UserNotFoundException: User not found");
    }

    if (!user.confirmed) {
      throw new Error("UserNotConfirmedException: User not confirmed");
    }

    if (user.password !== password) {
      throw new Error("NotAuthorizedException: Invalid password");
    }

    // Generate session
    const tokens = this.generateDevTokens(actualUsername);
    const session = {
      user: {
        username: user.username,
        userId: `dev-${user.username}`,
        email: user.email,
        firstName: user.firstName,
        lastName: user.lastName,
      },
      tokens,
      expiresAt: Date.now() + 3600000, // 1 hour
    };

    this.saveSession(session);
    console.log("✅ DEV: User signed in successfully");

    return {
      isSignedIn: true,
      user: session.user,
      tokens: session.tokens,
    };
  }

  async signOut() {
    console.log("🔧 DEV: Signing out user");
    this.clearSession();
    return true;
  }

  async getCurrentUser() {
    if (!this.session || Date.now() > this.session.expiresAt) {
      throw new Error("No authenticated user");
    }
    return this.session.user;
  }

  async fetchAuthSession() {
    if (!this.session || Date.now() > this.session.expiresAt) {
      throw new Error("No valid session");
    }
    return {
      tokens: this.session.tokens,
    };
  }

  async resetPassword(username) {
    console.log("🔧 DEV: Initiating password reset for", username);

    const user = this.users[username];
    if (!user) {
      throw new Error("UserNotFoundException: User not found");
    }

    const resetCode = this.generateVerificationCode();

    // Store reset code
    this.pendingVerifications[`reset_${username}`] = {
      username,
      resetCode,
      createdAt: Date.now(),
    };
    this.savePendingVerifications();

    console.log("📧 DEV: Password reset code sent to", user.email);
    console.log("🔑 DEV: Reset code:", resetCode);

    // In development, log the reset code to console
    console.log("📧 DEV AUTH: Password reset code for", user.email, ":", resetCode);
    console.log("🔑 DEV AUTH: Copy this code to reset your password");
    
    // Store dev code for debugging (non-production only)
    if (window.DEV_AUTH_DEBUG !== false) {
      window.lastDevResetCode = resetCode;
      console.log("💡 DEV AUTH: Access code via window.lastDevResetCode");
    }
    
    // Show reset code in browser alert for easy access in development
    if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
      setTimeout(() => {
        alert(`🔑 DEV AUTH PASSWORD RESET CODE\n\nFor: ${user.email}\nReset Code: ${resetCode}\n\nCopy this code to reset your password.`);
      }, 100);
    }

    return {
      nextStep: {
        resetPasswordStep: "CONFIRM_RESET_PASSWORD_WITH_CODE",
        codeDeliveryDetails: {
          deliveryMedium: "EMAIL",
          destination: user.email,
        },
      },
    };
  }

  async confirmResetPassword(username, confirmationCode, newPassword) {
    console.log("🔧 DEV: Confirming password reset for", username);

    const resetKey = `reset_${username}`;
    const pending = this.pendingVerifications[resetKey];

    if (!pending) {
      throw new Error("Invalid reset request");
    }

    if (pending.resetCode !== confirmationCode) {
      throw new Error("CodeMismatchException: Invalid verification code");
    }

    // Check if code is expired (5 minutes)
    if (Date.now() - pending.createdAt > 5 * 60 * 1000) {
      throw new Error("ExpiredCodeException: Verification code has expired");
    }

    // Update password
    this.users[username].password = newPassword;
    this.saveUsers();

    // Remove from pending
    delete this.pendingVerifications[resetKey];
    this.savePendingVerifications();

    console.log("✅ DEV: Password reset successfully");

    return true;
  }

  // Helper method to check if user is logged in
  isAuthenticated() {
    return this.session && Date.now() < this.session.expiresAt;
  }

  // Helper method to get current user info
  getCurrentUserInfo() {
    if (this.isAuthenticated()) {
      return this.session.user;
    }
    return null;
  }
}

export default new DevAuthService();
