import { renderHook, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { vi } from 'vitest';
import usePostLoginFlow from '../../../hooks/usePostLoginFlow';
import { useAuth } from '../../../contexts/AuthContext';

// Mock the auth context
vi.mock('../../../contexts/AuthContext');

// Mock react-router-dom
const mockNavigate = vi.fn();
vi.mock('react-router-dom', () => ({
  ...vi.importActual('react-router-dom'),
  useNavigate: () => mockNavigate,
  useLocation: () => ({ pathname: '/' })
}));

// Mock localStorage
const localStorageMock = {
  getItem: vi.fn(),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn(),
};
global.localStorage = localStorageMock;

// Mock sessionStorage
const sessionStorageMock = {
  getItem: vi.fn(),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn(),
};
global.sessionStorage = sessionStorageMock;

const wrapper = ({ children }) => <BrowserRouter>{children}</BrowserRouter>;

describe('usePostLoginFlow Hook', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    localStorageMock.getItem.mockReturnValue(null);
    sessionStorageMock.getItem.mockReturnValue(null);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('First-time User Detection', () => {
    it('detects first-time user when no lastLogin exists', () => {
      useAuth.mockReturnValue({
        isAuthenticated: true,
        user: { userId: 'user123', username: 'testuser' }
      });

      localStorageMock.getItem.mockReturnValue(null); // No previous login

      const { result } = renderHook(() => usePostLoginFlow(), { wrapper });

      expect(result.current.isFirstTimeUser).toBe(true);
      expect(result.current.showWelcomeMessage).toBe(true);
    });

    it('detects returning user when lastLogin exists', () => {
      useAuth.mockReturnValue({
        isAuthenticated: true,
        user: { userId: 'user123', username: 'testuser' }
      });

      localStorageMock.getItem.mockReturnValue('2023-12-01T10:00:00.000Z');

      const { result } = renderHook(() => usePostLoginFlow(), { wrapper });

      expect(result.current.isFirstTimeUser).toBe(false);
      expect(result.current.showWelcomeMessage).toBe(true);
    });

    it('stores login timestamp on authentication', () => {
      useAuth.mockReturnValue({
        isAuthenticated: true,
        user: { userId: 'user123', username: 'testuser' }
      });

      renderHook(() => usePostLoginFlow(), { wrapper });

      expect(localStorageMock.setItem).toHaveBeenCalledWith(
        'lastLogin_user123',
        expect.any(String)
      );
    });
  });

  describe('Welcome Message Management', () => {
    it('shows welcome message for authenticated users', () => {
      useAuth.mockReturnValue({
        isAuthenticated: true,
        user: { userId: 'user123', username: 'testuser' }
      });

      const { result } = renderHook(() => usePostLoginFlow(), { wrapper });

      expect(result.current.showWelcomeMessage).toBe(true);
    });

    it('does not show welcome message for unauthenticated users', () => {
      useAuth.mockReturnValue({
        isAuthenticated: false,
        user: null
      });

      const { result } = renderHook(() => usePostLoginFlow(), { wrapper });

      expect(result.current.showWelcomeMessage).toBe(false);
    });

    it('allows dismissing welcome message', () => {
      useAuth.mockReturnValue({
        isAuthenticated: true,
        user: { userId: 'user123', username: 'testuser' }
      });

      const { result } = renderHook(() => usePostLoginFlow(), { wrapper });

      expect(result.current.showWelcomeMessage).toBe(true);

      act(() => {
        result.current.dismissWelcomeMessage();
      });

      expect(result.current.showWelcomeMessage).toBe(false);
    });
  });

  describe('Navigation and Redirects', () => {
    it('redirects to intended path when available', () => {
      sessionStorageMock.getItem.mockReturnValue('/portfolio');
      
      useAuth.mockReturnValue({
        isAuthenticated: true,
        user: { userId: 'user123', username: 'testuser' }
      });

      renderHook(() => usePostLoginFlow(), { wrapper });

      act(() => {
        vi.advanceTimersByTime(2000);
      });

      expect(mockNavigate).toHaveBeenCalledWith('/portfolio', { replace: true });
      expect(sessionStorageMock.removeItem).toHaveBeenCalledWith('intendedPath');
    });

    it('redirects to dashboard when no intended path', () => {
      sessionStorageMock.getItem.mockReturnValue(null);
      
      useAuth.mockReturnValue({
        isAuthenticated: true,
        user: { userId: 'user123', username: 'testuser' }
      });

      // Mock location to be root or market path
      vi.doMock('react-router-dom', () => ({
        ...vi.importActual('react-router-dom'),
        useNavigate: () => mockNavigate,
        useLocation: () => ({ pathname: '/' })
      }));

      renderHook(() => usePostLoginFlow(), { wrapper });

      act(() => {
        vi.advanceTimersByTime(1500);
      });

      expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true });
    });

    it('does not redirect when on other paths', () => {
      sessionStorageMock.getItem.mockReturnValue(null);
      
      useAuth.mockReturnValue({
        isAuthenticated: true,
        user: { userId: 'user123', username: 'testuser' }
      });

      // Mock location to be different path
      vi.doMock('react-router-dom', () => ({
        ...vi.importActual('react-router-dom'),
        useNavigate: () => mockNavigate,
        useLocation: () => ({ pathname: '/settings' })
      }));

      renderHook(() => usePostLoginFlow(), { wrapper });

      act(() => {
        vi.advanceTimersByTime(2000);
      });

      // Should not navigate if already on a different path
      expect(mockNavigate).not.toHaveBeenCalled();
    });

    it('cleans up timers on unmount', () => {
      useAuth.mockReturnValue({
        isAuthenticated: true,
        user: { userId: 'user123', username: 'testuser' }
      });

      const { unmount } = renderHook(() => usePostLoginFlow(), { wrapper });

      // Start the timers
      act(() => {
        vi.advanceTimersByTime(1000);
      });

      unmount();

      // Advance past the timer duration
      act(() => {
        vi.advanceTimersByTime(2000);
      });

      // Should not navigate after unmount
      expect(mockNavigate).not.toHaveBeenCalled();
    });
  });

  describe('User Data Management', () => {
    it('returns user data correctly', () => {
      const mockUser = { 
        userId: 'user123', 
        username: 'testuser',
        email: 'test@example.com',
        firstName: 'Test'
      };
      
      useAuth.mockReturnValue({
        isAuthenticated: true,
        user: mockUser
      });

      const { result } = renderHook(() => usePostLoginFlow(), { wrapper });

      expect(result.current.user).toEqual(mockUser);
    });

    it('handles null user gracefully', () => {
      useAuth.mockReturnValue({
        isAuthenticated: false,
        user: null
      });

      const { result } = renderHook(() => usePostLoginFlow(), { wrapper });

      expect(result.current.user).toBeNull();
      expect(result.current.showWelcomeMessage).toBe(false);
      expect(result.current.isFirstTimeUser).toBe(false);
    });
  });

  describe('State Updates', () => {
    it('updates state when authentication changes', () => {
      const { result, rerender } = renderHook(() => usePostLoginFlow(), { wrapper });

      // Start unauthenticated
      useAuth.mockReturnValue({
        isAuthenticated: false,
        user: null
      });

      rerender();

      expect(result.current.showWelcomeMessage).toBe(false);

      // Become authenticated
      useAuth.mockReturnValue({
        isAuthenticated: true,
        user: { userId: 'user123', username: 'testuser' }
      });

      rerender();

      expect(result.current.showWelcomeMessage).toBe(true);
    });

    it('handles user changes correctly', () => {
      const { result, rerender } = renderHook(() => usePostLoginFlow(), { wrapper });

      // Start with first user
      useAuth.mockReturnValue({
        isAuthenticated: true,
        user: { userId: 'user123', username: 'testuser1' }
      });

      rerender();

      expect(localStorageMock.setItem).toHaveBeenCalledWith(
        'lastLogin_user123',
        expect.any(String)
      );

      // Change to different user
      useAuth.mockReturnValue({
        isAuthenticated: true,
        user: { userId: 'user456', username: 'testuser2' }
      });

      rerender();

      expect(localStorageMock.setItem).toHaveBeenCalledWith(
        'lastLogin_user456',
        expect.any(String)
      );
    });
  });

  describe('Timer Management', () => {
    it('sets correct timer delays for intended path redirect', () => {
      sessionStorageMock.getItem.mockReturnValue('/settings');
      
      useAuth.mockReturnValue({
        isAuthenticated: true,
        user: { userId: 'user123', username: 'testuser' }
      });

      renderHook(() => usePostLoginFlow(), { wrapper });

      // Should redirect after 2000ms for intended path
      act(() => {
        vi.advanceTimersByTime(1999);
      });
      expect(mockNavigate).not.toHaveBeenCalled();

      act(() => {
        vi.advanceTimersByTime(1);
      });
      expect(mockNavigate).toHaveBeenCalled();
    });

    it('sets correct timer delays for default redirect', () => {
      sessionStorageMock.getItem.mockReturnValue(null);
      
      useAuth.mockReturnValue({
        isAuthenticated: true,
        user: { userId: 'user123', username: 'testuser' }
      });

      // Mock location to be root path
      vi.doMock('react-router-dom', () => ({
        ...vi.importActual('react-router-dom'),
        useNavigate: () => mockNavigate,
        useLocation: () => ({ pathname: '/' })
      }));

      renderHook(() => usePostLoginFlow(), { wrapper });

      // Should redirect after 1500ms for default
      act(() => {
        vi.advanceTimersByTime(1499);
      });
      expect(mockNavigate).not.toHaveBeenCalled();

      act(() => {
        vi.advanceTimersByTime(1);
      });
      expect(mockNavigate).toHaveBeenCalled();
    });
  });
});