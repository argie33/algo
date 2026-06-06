/**
 * Development Authentication Helper
 * Provides utilities for testing and development authentication
 */

export class DevAuthHelper {
  static createTestUser() {
    const user = {
      username: 'testuser',
      email: 'test@example.com',
      firstName: 'Test',
      lastName: 'User',
      password: 'password123',
      confirmed: true,
      createdAt: Date.now(),
    };

    const stored = localStorage.getItem('dev_users');
    const users = stored ? JSON.parse(stored) : {};
    users.testuser = user;
    localStorage.setItem('dev_users', JSON.stringify(users));

    return user;
  }

  static createSession(user) {
    const session = {
      user: {
        username: user.username,
        userId: `dev-${user.username}`,
        email: user.email,
        firstName: user.firstName,
        lastName: user.lastName,
      },
      tokens: {
        accessToken: `dev-access-${user.username}-${Date.now()}`,
        idToken: `dev-id-${user.username}-${Date.now()}`,
        refreshToken: `dev-refresh-${user.username}-${Date.now()}`,
      },
      expiresAt: Date.now() + 3600000, // 1 hour from now
    };

    localStorage.setItem('dev_session', JSON.stringify(session));
    return session;
  }

  static setupDevAuth() {
    const hostname = typeof window !== 'undefined' ? window.location.hostname : 'unknown';
    const isLocalhost = hostname === 'localhost' || hostname === '127.0.0.1';

    if (!isLocalhost) {
      return false;
    }

    try {
      const sessionStr = localStorage.getItem('dev_session');
      if (sessionStr) {
        const session = JSON.parse(sessionStr);
        if (session.expiresAt && session.expiresAt > Date.now()) {
          // Session is still valid
          return true;
        }
      }
    } catch (error) {
      // Invalid JSON, create new session
    }

    // Create new session with test user
    const testUser = this.createTestUser();
    this.createSession(testUser);
    return true;
  }

  static getDevUser() {
    try {
      const sessionStr = localStorage.getItem('dev_session');
      if (!sessionStr) {
        return null;
      }

      const session = JSON.parse(sessionStr);
      if (session.expiresAt && session.expiresAt <= Date.now()) {
        // Session has expired
        return null;
      }

      return session.user || null;
    } catch (error) {
      return null;
    }
  }

  static clearDevAuth() {
    localStorage.removeItem('dev_session');
    localStorage.removeItem('dev_users');
  }
}

export default DevAuthHelper;
