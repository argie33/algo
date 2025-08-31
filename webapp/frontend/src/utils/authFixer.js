/**
 * Development Authentication Helper
 * Creates and manages dev users for testing Settings page
 */

export class DevAuthHelper {
  static createTestUser() {
    // Creating development test user
    
    const devUser = {
      username: 'testuser',
      email: 'test@example.com',
      firstName: 'Test',
      lastName: 'User',
      password: 'password123',
      confirmed: true,
      createdAt: Date.now(),
    };
    
    // Add to dev users
    const users = JSON.parse(localStorage.getItem('dev_users') || '{}');
    users['testuser'] = devUser;
    localStorage.setItem('dev_users', JSON.stringify(users));
    
    // Test user created
    return devUser;
  }
  
  static createSession(user) {
    // Creating development session
    
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
      expiresAt: Date.now() + 3600000, // 1 hour
    };
    
    localStorage.setItem('dev_session', JSON.stringify(session));
    
    // Development session created
    
    return session;
  }
  
  static setupDevAuth() {
    // Setting up development authentication
    
    // Only run in development
    if (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
      // Dev auth setup only available in development
      return false;
    }
    
    // Check if session already exists and is valid
    const existingSession = localStorage.getItem('dev_session');
    if (existingSession) {
      try {
        const session = JSON.parse(existingSession);
        if (Date.now() < session.expiresAt) {
          // Valid development session already exists
          return true;
        }
      } catch (e) {
        // Invalid existing session, creating new one
      }
    }
    
    // Create test user and session
    const user = this.createTestUser();
    const _session = this.createSession(user);
    
    // Development authentication setup complete
    
    return true;
  }
  
  static getDevUser() {
    const session = localStorage.getItem('dev_session');
    if (!session) return null;
    
    try {
      const parsed = JSON.parse(session);
      return Date.now() < parsed.expiresAt ? parsed.user : null;
    } catch (e) {
      return null;
    }
  }
  
  static isDevAuthenticated() {
    return this.getDevUser() !== null;
  }
  
  static clearDevAuth() {
    localStorage.removeItem('dev_session');
    localStorage.removeItem('dev_users');
    // Development authentication cleared
  }
}

// Auto-setup in development if needed
if (typeof window !== 'undefined') {
  // Make available globally for debugging
  window.DevAuthHelper = DevAuthHelper;
  
  // Auto-setup if not authenticated and dev auth is forced
  if (import.meta.env.VITE_FORCE_DEV_AUTH === 'true') {
    setTimeout(() => {
      if (!DevAuthHelper.isDevAuthenticated()) {
        // Auto-setting up dev authentication
        DevAuthHelper.setupDevAuth();
      }
    }, 1000);
  }
}

export default DevAuthHelper;