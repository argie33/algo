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
    if (typeof localStorage === "undefined") {
      return {}; // Return empty object in test environment
    }
    const stored = localStorage.getItem(DEV_USERS_KEY);
    return stored ? JSON.parse(stored) : {};
  }

  saveUsers() {
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(DEV_USERS_KEY, JSON.stringify(this.users));
    }
  }

  loadSession() {
    if (typeof localStorage === "undefined") {
      return null; // Return null in test environment
    }
    const stored = localStorage.getItem(DEV_SESSION_KEY);
    return stored ? JSON.parse(stored) : null;
  }

  saveSession(session) {
    this.session = session;
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(DEV_SESSION_KEY, JSON.stringify(session));
    }
  }

  clearSession() {
    this.session = null;
    if (typeof localStorage !== "undefined") {
      localStorage.removeItem(DEV_SESSION_KEY);
    }
  }

  loadPendingVerifications() {
    if (typeof localStorage === "undefined") {
      return {}; // Return empty object in test environment
    }
    const stored = localStorage.getItem(DEV_PENDING_KEY);
    return stored ? JSON.parse(stored) : {};
  }

  savePendingVerifications() {
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(
        DEV_PENDING_KEY,
        JSON.stringify(this.pendingVerifications)
      );
    }
  }

  ensureDevUser() {
    // Always ensure the default user exists with consistent credentials
    const defaultUser = {
      username: "devuser",
      email: "argeropolos@gmail.com",
      firstName: "Dev",
      lastName: "User",
      password: "password123",
      confirmed: true,
      createdAt: Date.now(),
    };

    // Always set/update the default user to ensure consistency
    this.users["devuser"] = defaultUser;
    this.users["argeropolos@gmail.com"] = defaultUser; // Allow email login too
    this.saveUsers();

    if (typeof console !== "undefined") {
      console.log("🔧 DEV: Ensured default dev user exists");
      console.log("📧 Email: argeropolos@gmail.com");
      console.log("🔑 Username: devuser");
      console.log("🔒 Password: password123");
      console.log("✅ User can sign in with either email or username");
    }
  }

  generateVerificationCode() {
    return Math.floor(100000 + Math.random() * 900000).toString();
  }

  generateDevTokens(_username) {
    // Use the token that the backend auth middleware recognizes for dev bypass
    return {
      accessToken: "dev-bypass-token",
      idToken: "dev-bypass-token",
      refreshToken: "dev-bypass-token",
    };
  }

  async signUp(username, password, email, firstName, lastName) {
    // DEV: Simulating sign up

    // Check if user already exists in confirmed users
    if (this.users[username]) {
      throw new Error("UsernameExistsException: Username already exists");
    }

    // Check if user already exists in pending verifications
    if (this.pendingVerifications[username]) {
      throw new Error("UsernameExistsException: Username already exists");
    }

    // Check if email is already used in confirmed users
    const existingUser = Object.values(this.users).find(
      (user) => user.email === email
    );
    if (existingUser) {
      throw new Error("UsernameExistsException: Email already exists");
    }

    // Check if email is already used in pending verifications
    const existingPending = Object.values(this.pendingVerifications).find(
      (pending) => pending.email === email
    );
    if (existingPending) {
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
    if (typeof console !== "undefined") {
      console.log("📧 DEV: Email verification code sent to", email);
      console.log("🔑 DEV: Verification code:", verificationCode);
      console.log(
        "📧 DEV AUTH: Verification code for",
        email,
        ":",
        verificationCode
      );
      console.log("🔑 DEV AUTH: Copy this code to complete registration");
    }

    // Store dev code for debugging (non-production only)
    if (typeof window !== "undefined" && window.DEV_AUTH_DEBUG !== false) {
      window.lastDevCode = verificationCode;
      if (typeof console !== "undefined") {
        console.log("💡 DEV AUTH: Access code via window.lastDevCode");
      }
    }

    // Show verification code in browser alert for easy access in development
    if (
      typeof window !== "undefined" &&
      window.location &&
      (window.location.hostname === "localhost" ||
        window.location.hostname === "127.0.0.1")
    ) {
      setTimeout(() => {
        alert(
          `🔑 DEV AUTH VERIFICATION CODE\n\nFor: ${email}\nCode: ${verificationCode}\n\nCopy this code to complete your registration.`
        );
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
    if (typeof console !== "undefined") {
      console.log("🔧 DEV: Confirming sign up for", username);
    }

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

    if (typeof console !== "undefined") {
      console.log("✅ DEV: User confirmed successfully");
    }

    return {
      isSignUpComplete: true,
    };
  }

  async signIn(usernameOrEmail, password) {
    if (typeof console !== "undefined") {
      console.log("🔧 DEV: Signing in user", usernameOrEmail);
    }

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
        if (typeof console !== "undefined") {
          console.log(
            "🔧 DEV: Found user by email, username is",
            actualUsername
          );
        }
      }
    }

    if (!user) {
      // Check if user exists in pending verifications
      const pendingUser = this.pendingVerifications[usernameOrEmail];
      if (pendingUser) {
        throw new Error("UserNotConfirmedException: User not confirmed");
      }

      // Check if user exists by email in pending verifications
      const pendingByEmail = Object.values(this.pendingVerifications).find(
        (pending) => pending.email === usernameOrEmail
      );
      if (pendingByEmail) {
        throw new Error("UserNotConfirmedException: User not confirmed");
      }

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
    if (typeof console !== "undefined") {
      console.log("✅ DEV: User signed in successfully");
    }

    return {
      isSignedIn: true,
      user: session.user,
      tokens: session.tokens,
    };
  }

  async signOut() {
    if (typeof console !== "undefined") {
      console.log("🔧 DEV: Signing out user");
    }
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
    if (typeof console !== "undefined") {
      console.log("🔧 DEV: Initiating password reset for", username);
    }

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

    if (typeof console !== "undefined") {
      console.log("📧 DEV: Password reset code sent to", user.email);
      console.log("🔑 DEV: Reset code:", resetCode);
      console.log(
        "📧 DEV AUTH: Password reset code for",
        user.email,
        ":",
        resetCode
      );
      console.log("🔑 DEV AUTH: Copy this code to reset your password");
    }

    // Store dev code for debugging (non-production only)
    if (typeof window !== "undefined" && window.DEV_AUTH_DEBUG !== false) {
      window.lastDevResetCode = resetCode;
      if (typeof console !== "undefined") {
        console.log("💡 DEV AUTH: Access code via window.lastDevResetCode");
      }
    }

    // Show reset code in browser alert for easy access in development
    if (
      typeof window !== "undefined" &&
      window.location &&
      (window.location.hostname === "localhost" ||
        window.location.hostname === "127.0.0.1")
    ) {
      setTimeout(() => {
        alert(
          `🔑 DEV AUTH PASSWORD RESET CODE\n\nFor: ${user.email}\nReset Code: ${resetCode}\n\nCopy this code to reset your password.`
        );
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
    if (typeof console !== "undefined") {
      console.log("🔧 DEV: Confirming password reset for", username);
    }

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

    if (typeof console !== "undefined") {
      console.log("✅ DEV: Password reset successfully");
    }

    return true;
  }

  // Helper method to check if user is logged in
  isAuthenticated() {
    return !!(this.session && Date.now() < this.session.expiresAt);
  }

  // Helper method to get current user info
  getCurrentUserInfo() {
    if (this.isAuthenticated()) {
      return this.session.user;
    }
    return null;
  }

  // Wrapper method for tests - matches expected API
  async signUpWrapper(userData) {
    try {
      const { username, password, email, firstName, lastName } = userData;

      // Check if user already exists in confirmed users
      if (this.users[username]) {
        return {
          success: false,
          error: {
            code: "UsernameExistsException",
            message: "Username already exists",
          },
        };
      }

      // Check if user already exists in pending verifications
      if (this.pendingVerifications[username]) {
        return {
          success: false,
          error: {
            code: "UsernameExistsException",
            message: "Username already exists",
          },
        };
      }

      // Check if email is already used in confirmed users
      const existingUser = Object.values(this.users).find(
        (user) => user.email === email
      );
      if (existingUser) {
        return {
          success: false,
          error: {
            code: "UsernameExistsException",
            message: "Email already exists",
          },
        };
      }

      // Check if email is already used in pending verifications
      const existingPending = Object.values(this.pendingVerifications).find(
        (pending) => pending.email === email
      );
      if (existingPending) {
        return {
          success: false,
          error: {
            code: "UsernameExistsException",
            message: "Email already exists",
          },
        };
      }

      // Call the original signUp method directly to avoid circular reference
      const result = await DevAuthService.prototype.signUp.call(
        this,
        username,
        password,
        email,
        firstName || "Dev",
        lastName || "User"
      );

      return {
        success: true,
        user: {
          username,
          email,
        },
        userConfirmed: false,
        isSignUpComplete: result.isSignUpComplete,
        nextStep: result.nextStep,
      };
    } catch (error) {
      return {
        success: false,
        error: {
          code: error.message.split(":")[0],
          message: error.message.split(":")[1] || error.message,
        },
      };
    }
  }

  // Wrapper method for tests - matches expected API
  async signInWrapper(username, password) {
    try {
      const result = await DevAuthService.prototype.signIn.call(
        this,
        username,
        password
      );
      return {
        success: true,
        user: result.user,
        tokens: result.tokens,
        isSignedIn: result.isSignedIn,
      };
    } catch (error) {
      return {
        success: false,
        error: {
          code: error.message.split(":")[0],
          message: error.message.split(":")[1] || error.message,
        },
      };
    }
  }

  // Password validation method
  validatePassword(password) {
    const errors = [];

    if (password.length < 8) {
      errors.push("Password must be at least 8 characters long");
    }

    if (!/[a-z]/.test(password)) {
      errors.push("Password must contain at least one lowercase letter");
    }

    if (!/[A-Z]/.test(password)) {
      errors.push("Password must contain at least one uppercase letter");
    }

    if (!/\d/.test(password)) {
      errors.push("Password must contain at least one digit");
    }

    if (!/[!@#$%^&*(),.?":{}|<>]/.test(password)) {
      errors.push("Password must contain at least one special character");
    }

    return {
      isValid: errors.length === 0,
      errors,
    };
  }

  // Wrapper for getCurrentUser that matches test expectations
  async getCurrentUserWrapper() {
    try {
      const user = await DevAuthService.prototype.getCurrentUser.call(this);
      return {
        success: true,
        user,
      };
    } catch (error) {
      return {
        success: false,
        error: {
          code: "NotAuthorizedException",
          message: error.message,
        },
      };
    }
  }

  // Get JWT token method for tests
  async getJwtToken() {
    try {
      const session = await this.fetchAuthSession();
      return session.tokens.accessToken;
    } catch (error) {
      return null;
    }
  }

  // Sign out wrapper for tests
  async signOutWrapper() {
    try {
      await DevAuthService.prototype.signOut.call(this);
      return {
        success: true,
      };
    } catch (error) {
      return {
        success: false,
        error: {
          code: "SignOutError",
          message: error.message,
        },
      };
    }
  }

  // Password reset wrapper for tests
  async forgotPasswordWrapper(username) {
    try {
      await DevAuthService.prototype.resetPassword.call(this, username);
      return {
        success: true,
      };
    } catch (error) {
      return {
        success: false,
        error: {
          code: error.message.split(":")[0],
          message: error.message.split(":")[1] || error.message,
        },
      };
    }
  }

  // Confirm password reset wrapper for tests
  async confirmResetPasswordWrapper(username, code, newPassword) {
    try {
      await DevAuthService.prototype.confirmResetPassword.call(
        this,
        username,
        code,
        newPassword
      );
      return {
        success: true,
      };
    } catch (error) {
      return {
        success: false,
        error: {
          code: error.message.split(":")[0],
          message: error.message.split(":")[1] || error.message,
        },
      };
    }
  }

  // JWT token validation methods
  validateJwtToken(token) {
    // Simple validation for dev environment
    return !!(token && typeof token === "string" && token.length > 0);
  }

  isTokenExpired(_token) {
    // In dev environment, tokens don't really expire
    return false;
  }

  // MFA confirmation wrapper
  async confirmMFA(user, _code) {
    // Dev environment doesn't have real MFA, so just return success
    return {
      success: true,
      user: user || { username: "testuser" },
    };
  }

  // Update user attributes wrapper
  async updateUserAttributes(user, attributes) {
    try {
      // In dev environment, just update the local user
      if (this.users[user.username]) {
        Object.assign(this.users[user.username], attributes);
        this.saveUsers();
      }
      return {
        success: true,
      };
    } catch (error) {
      return {
        success: false,
        error: {
          code: "UpdateAttributesError",
          message: error.message,
        },
      };
    }
  }
}

// Create service instance
const devAuthService = new DevAuthService();

// Override methods directly for test compatibility
devAuthService.signUp = devAuthService.signUpWrapper;
devAuthService.signIn = devAuthService.signInWrapper;
devAuthService.getCurrentUser = devAuthService.getCurrentUserWrapper;
devAuthService.signOut = devAuthService.signOutWrapper;
devAuthService.forgotPassword = devAuthService.forgotPasswordWrapper;
devAuthService.forgotPasswordSubmit =
  devAuthService.confirmResetPasswordWrapper;
devAuthService.changePassword = devAuthService.confirmResetPasswordWrapper;

// Ensure all methods are available on the instance
devAuthService.generateVerificationCode =
  devAuthService.generateVerificationCode.bind(devAuthService);
devAuthService.generateDevTokens =
  devAuthService.generateDevTokens.bind(devAuthService);
devAuthService.loadUsers = devAuthService.loadUsers.bind(devAuthService);
devAuthService.saveUsers = devAuthService.saveUsers.bind(devAuthService);
devAuthService.loadSession = devAuthService.loadSession.bind(devAuthService);
devAuthService.saveSession = devAuthService.saveSession.bind(devAuthService);
devAuthService.loadPendingVerifications =
  devAuthService.loadPendingVerifications.bind(devAuthService);
devAuthService.savePendingVerifications =
  devAuthService.savePendingVerifications.bind(devAuthService);
devAuthService.confirmSignUp =
  devAuthService.confirmSignUp.bind(devAuthService);
devAuthService.validateJwtToken =
  devAuthService.validateJwtToken.bind(devAuthService);
devAuthService.isTokenExpired =
  devAuthService.isTokenExpired.bind(devAuthService);
devAuthService.confirmMFA = devAuthService.confirmMFA.bind(devAuthService);
devAuthService.updateUserAttributes =
  devAuthService.updateUserAttributes.bind(devAuthService);
devAuthService.validatePassword =
  devAuthService.validatePassword.bind(devAuthService);

export default devAuthService;
