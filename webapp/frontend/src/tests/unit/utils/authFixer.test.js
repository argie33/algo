/**
 * AuthFixer Utility Unit Tests
 * Tests the development authentication helper
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { DevAuthHelper } from "../../../utils/authFixer.js";

// Mock localStorage
const localStorageMock = {
  getItem: vi.fn(),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn(),
};

// Mock window object
const windowMock = {
  location: {
    hostname: 'localhost'
  },
  DevAuthHelper: undefined
};

global.localStorage = localStorageMock;
global.window = windowMock;

describe("AuthFixer Utility", () => {
  let originalDateNow;
  
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Use fake timers to handle setTimeout in the authFixer
    vi.useFakeTimers();
    
    localStorageMock.getItem.mockReturnValue('{}');
    localStorageMock.setItem.mockImplementation(() => {});
    windowMock.location.hostname = 'localhost';
    
    // Mock Date.now for consistent testing
    originalDateNow = Date.now;
    Date.now = vi.fn(() => 1640995200000); // Fixed timestamp
    
    // Mock import.meta.env
    vi.stubGlobal('import.meta', {
      env: {
        VITE_FORCE_DEV_AUTH: 'false'
      }
    });
  });

  afterEach(() => {
    // Restore original Date.now
    if (originalDateNow) {
      Date.now = originalDateNow;
    }
    
    // Clear all timers and restore real timers
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  describe("DevAuthHelper", () => {
    describe("createTestUser", () => {
      it("creates a test user with correct properties", () => {
        const user = DevAuthHelper.createTestUser();

        expect(user).toBeDefined();
        expect(user.username).toBe('testuser');
        expect(user.email).toBe('test@example.com');
        expect(user.firstName).toBe('Test');
        expect(user.lastName).toBe('User');
        expect(user.password).toBe('password123');
        expect(user.confirmed).toBe(true);
        expect(user.createdAt).toBe(1640995200000); // Fixed timestamp
      });

      it("stores user in localStorage", () => {
        DevAuthHelper.createTestUser();

        expect(localStorageMock.getItem).toHaveBeenCalledWith('dev_users');
        expect(localStorageMock.setItem).toHaveBeenCalledWith(
          'dev_users',
          expect.stringContaining('testuser')
        );
      });

      it("handles existing users in localStorage", () => {
        localStorageMock.getItem.mockReturnValue('{"existinguser": {"username": "existinguser"}}');

        DevAuthHelper.createTestUser();

        expect(localStorageMock.setItem).toHaveBeenCalledWith(
          'dev_users',
          expect.stringContaining('existinguser')
        );
        expect(localStorageMock.setItem).toHaveBeenCalledWith(
          'dev_users',
          expect.stringContaining('testuser')
        );
      });

      it("handles invalid JSON in localStorage", () => {
        localStorageMock.getItem.mockReturnValue('invalid json');

        // Should throw error since implementation doesn't handle invalid JSON
        expect(() => DevAuthHelper.createTestUser()).toThrow('Unexpected token');
      });
    });

    describe("createSession", () => {
      it("creates a session for a user with correct structure", () => {
        const testUser = { 
          username: 'testuser', 
          email: 'test@example.com',
          firstName: 'Test',
          lastName: 'User'
        };
        
        const session = DevAuthHelper.createSession(testUser);

        expect(session).toBeDefined();
        expect(session.user).toBeDefined();
        expect(session.user.username).toBe('testuser');
        expect(session.user.userId).toBe('dev-testuser');
        expect(session.user.email).toBe('test@example.com');
        expect(session.user.firstName).toBe('Test');
        expect(session.user.lastName).toBe('User');
        expect(session.tokens).toBeDefined();
        expect(session.tokens.accessToken).toContain('dev-access-testuser');
        expect(session.tokens.idToken).toContain('dev-id-testuser');
        expect(session.tokens.refreshToken).toContain('dev-refresh-testuser');
        expect(session.expiresAt).toBe(1640995200000 + 3600000); // Fixed timestamp + 1 hour
      });

      it("stores session in localStorage", () => {
        const testUser = { username: 'testuser', email: 'test@example.com' };
        
        DevAuthHelper.createSession(testUser);

        expect(localStorageMock.setItem).toHaveBeenCalledWith(
          'dev_session',
          expect.stringContaining('testuser')
        );
      });
    });

    describe("setupDevAuth", () => {
      it("returns false for non-localhost environments", () => {
        windowMock.location.hostname = 'production.com';
        
        const result = DevAuthHelper.setupDevAuth();
        
        expect(result).toBe(false);
      });

      it("returns true when setting up dev auth on localhost", () => {
        windowMock.location.hostname = 'localhost';
        
        const result = DevAuthHelper.setupDevAuth();
        
        expect(result).toBe(true);
        expect(localStorageMock.setItem).toHaveBeenCalled();
      });

      it("returns true when setting up dev auth on 127.0.0.1", () => {
        windowMock.location.hostname = '127.0.0.1';
        
        const result = DevAuthHelper.setupDevAuth();
        
        expect(result).toBe(true);
      });

      it("returns true if valid existing session exists", () => {
        const validSession = {
          user: { username: 'testuser' },
          expiresAt: Date.now() + 1000000 // Future timestamp
        };
        localStorageMock.getItem.mockReturnValue(JSON.stringify(validSession));
        
        const result = DevAuthHelper.setupDevAuth();
        
        expect(result).toBe(true);
        // Should not create new session if existing one is valid
        expect(localStorageMock.setItem).not.toHaveBeenCalledWith('dev_session', expect.anything());
      });

      it("creates new session if existing session is expired", () => {
        const expiredSession = {
          user: { username: 'testuser' },
          expiresAt: Date.now() - 1000000 // Past timestamp
        };
        localStorageMock.getItem.mockReturnValue(JSON.stringify(expiredSession));
        
        const result = DevAuthHelper.setupDevAuth();
        
        expect(result).toBe(true);
        // Should create new session if existing one is expired
        expect(localStorageMock.setItem).toHaveBeenCalledWith('dev_session', expect.anything());
      });

      it("handles invalid JSON in existing session", () => {
        // First call for dev_session returns invalid JSON
        // Second call for dev_users in createTestUser should return valid JSON
        localStorageMock.getItem
          .mockReturnValueOnce('invalid json') // First call for dev_session
          .mockReturnValueOnce('{}'); // Second call for dev_users
        
        const result = DevAuthHelper.setupDevAuth();
        
        expect(result).toBe(true);
        // Should create new session if existing one is invalid
        expect(localStorageMock.setItem).toHaveBeenCalledWith('dev_session', expect.anything());
      });
    });

    describe("getDevUser", () => {
      it("returns user from valid session", () => {
        const validSession = {
          user: { username: 'testuser', email: 'test@example.com' },
          expiresAt: Date.now() + 1000000
        };
        localStorageMock.getItem.mockReturnValue(JSON.stringify(validSession));
        
        const user = DevAuthHelper.getDevUser();
        
        expect(user).toEqual({ username: 'testuser', email: 'test@example.com' });
      });

      it("returns null if no session exists", () => {
        localStorageMock.getItem.mockReturnValue(null);
        
        const user = DevAuthHelper.getDevUser();
        
        expect(user).toBe(null);
      });

      it("returns null if session is expired", () => {
        const expiredSession = {
          user: { username: 'testuser' },
          expiresAt: Date.now() - 1000000
        };
        localStorageMock.getItem.mockReturnValue(JSON.stringify(expiredSession));
        
        const user = DevAuthHelper.getDevUser();
        
        expect(user).toBe(null);
      });

      it("returns null if session JSON is invalid", () => {
        localStorageMock.getItem.mockReturnValue('invalid json');
        
        const user = DevAuthHelper.getDevUser();
        
        expect(user).toBe(null);
      });
    });

    describe("isDevAuthenticated", () => {
      it("returns true when user is authenticated", () => {
        const validSession = {
          user: { username: 'testuser' },
          expiresAt: Date.now() + 1000000
        };
        localStorageMock.getItem.mockReturnValue(JSON.stringify(validSession));
        
        const isAuth = DevAuthHelper.isDevAuthenticated();
        
        expect(isAuth).toBe(true);
      });

      it("returns false when user is not authenticated", () => {
        localStorageMock.getItem.mockReturnValue(null);
        
        const isAuth = DevAuthHelper.isDevAuthenticated();
        
        expect(isAuth).toBe(false);
      });
    });

    describe("clearDevAuth", () => {
      it("clears development authentication data", () => {
        DevAuthHelper.clearDevAuth();

        expect(localStorageMock.removeItem).toHaveBeenCalledWith('dev_session');
        expect(localStorageMock.removeItem).toHaveBeenCalledWith('dev_users');
      });
    });
  });
});