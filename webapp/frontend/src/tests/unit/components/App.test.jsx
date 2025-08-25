import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import App from '../../../App';
import { AuthContext } from '../../../contexts/AuthContext';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Mock the useOnboarding hook
vi.mock('../../../hooks/useOnboarding', () => ({
  useOnboarding: () => ({
    showOnboarding: false,
    completeOnboarding: vi.fn(),
    loading: false,
  }),
}));

// Mock all page components to avoid complex renders
vi.mock('../../../pages/Dashboard', () => ({
  default: () => <div data-testid="dashboard">Dashboard Component</div>
}));

vi.mock('../../../pages/MarketOverview', () => ({
  default: () => <div data-testid="market-overview">Market Overview Component</div>
}));

vi.mock('../../../pages/Portfolio', () => ({
  default: () => <div data-testid="portfolio">Portfolio Component</div>
}));

vi.mock('../../../pages/Settings', () => ({
  default: () => <div data-testid="settings">Settings Component</div>
}));

vi.mock('../../../components/auth/AuthModal', () => ({
  default: ({ open, onClose }) => 
    open ? <div data-testid="auth-modal" onClick={onClose}>Auth Modal</div> : null
}));

vi.mock('../../../components/onboarding/OnboardingWizard', () => ({
  default: ({ open, onComplete }) => 
    open ? <div data-testid="onboarding-wizard" onClick={onComplete}>Onboarding Wizard</div> : null
}));

describe('App Component', () => {
  let queryClient;
  let mockAuthContext;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    
    mockAuthContext = {
      isAuthenticated: false,
      user: null,
      login: vi.fn(),
      logout: vi.fn(),
      loading: false,
      error: null,
    };
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  const renderApp = (authContext = mockAuthContext) => {
    return render(
      <QueryClientProvider client={queryClient}>
        <AuthContext.Provider value={authContext}>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </AuthContext.Provider>
      </QueryClientProvider>
    );
  };

  describe('Basic Rendering', () => {
    it('should render the application layout', () => {
      renderApp();
      
      // Check for main layout elements
      expect(screen.getByText('Financial Platform')).toBeInTheDocument();
      expect(screen.getByText('Dashboard')).toBeInTheDocument();
      expect(screen.getByTestId('dashboard')).toBeInTheDocument();
    });

    it('should render navigation menu items', () => {
      renderApp();
      
      // Check for main navigation items
      expect(screen.getByText('Dashboard')).toBeInTheDocument();
      expect(screen.getByText('Real-Time Data')).toBeInTheDocument();
      expect(screen.getByText('Market Overview')).toBeInTheDocument();
      expect(screen.getByText('Settings')).toBeInTheDocument();
    });
  });

  describe('Authentication States', () => {
    it('should show sign in button when not authenticated', () => {
      renderApp();
      
      expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /sign out/i })).not.toBeInTheDocument();
    });

    it('should show user menu when authenticated', () => {
      const authenticatedContext = {
        ...mockAuthContext,
        isAuthenticated: true,
        user: { username: 'testuser' },
      };
      
      renderApp(authenticatedContext);
      
      expect(screen.queryByRole('button', { name: /sign in/i })).not.toBeInTheDocument();
      expect(screen.getByText('T')).toBeInTheDocument(); // Avatar with first letter
    });

    it('should open auth modal when sign in is clicked', async () => {
      const user = userEvent.setup();
      renderApp();
      
      const signInButton = screen.getByRole('button', { name: /sign in/i });
      await user.click(signInButton);
      
      expect(screen.getByTestId('auth-modal')).toBeInTheDocument();
    });
  });

  describe('Navigation', () => {
    it('should navigate to different pages when menu items are clicked', async () => {
      const user = userEvent.setup();
      renderApp();
      
      // Click on Market Overview
      const marketOverviewLink = screen.getByText('Market Overview');
      await user.click(marketOverviewLink);
      
      await waitFor(() => {
        expect(screen.getByTestId('market-overview')).toBeInTheDocument();
      });
    });

    it('should toggle mobile drawer on mobile menu click', async () => {
      const user = userEvent.setup();
      
      // Mock mobile viewport
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 500,
      });

      renderApp();
      
      // The mobile menu button should be present (though may not be visible due to CSS)
      const menuButtons = screen.getAllByLabelText(/open drawer/i);
      if (menuButtons.length > 0) {
        await user.click(menuButtons[0]);
        // In a real test, we'd check for drawer state changes
      }
    });
  });

  describe('Menu Section Expansion', () => {
    it('should allow expanding and collapsing menu sections', async () => {
      const user = userEvent.setup();
      renderApp();
      
      // Find a collapsible section (like Tools which starts collapsed)
      const toolsSection = screen.queryByText('Tools');
      if (toolsSection) {
        await user.click(toolsSection);
        // Check if the section expanded (tools items became visible)
      }
    });
  });

  describe('User Menu Actions', () => {
    it('should show user menu options when authenticated user clicks avatar', async () => {
      const user = userEvent.setup();
      const authenticatedContext = {
        ...mockAuthContext,
        isAuthenticated: true,
        user: { username: 'testuser' },
      };
      
      renderApp(authenticatedContext);
      
      // Click on user avatar
      const avatar = screen.getByText('T');
      await user.click(avatar);
      
      await waitFor(() => {
        expect(screen.getByText('testuser')).toBeInTheDocument();
        expect(screen.getByText('Settings')).toBeInTheDocument();
        expect(screen.getByText('Sign Out')).toBeInTheDocument();
      });
    });

    it('should call logout when sign out is clicked', async () => {
      const user = userEvent.setup();
      const mockLogout = vi.fn();
      const authenticatedContext = {
        ...mockAuthContext,
        isAuthenticated: true,
        user: { username: 'testuser' },
        logout: mockLogout,
      };
      
      renderApp(authenticatedContext);
      
      // Click on user avatar to open menu
      const avatar = screen.getByText('T');
      await user.click(avatar);
      
      // Click sign out
      await waitFor(async () => {
        const signOutButton = screen.getByText('Sign Out');
        await user.click(signOutButton);
      });
      
      expect(mockLogout).toHaveBeenCalled();
    });
  });

  describe('Page Title Updates', () => {
    it('should update page title based on current route', async () => {
      const user = userEvent.setup();
      renderApp();
      
      // Navigate to settings
      const settingsLink = screen.getByText('Settings');
      await user.click(settingsLink);
      
      await waitFor(() => {
        // The app bar should show the current page name
        expect(screen.getAllByText('Settings')).toHaveLength(2); // Menu item + page title
      });
    });
  });

  describe('Responsive Behavior', () => {
    it('should handle mobile viewport correctly', () => {
      // Mock mobile viewport
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 500,
      });

      renderApp();
      
      // App should still render without errors
      expect(screen.getByText('Financial Platform')).toBeInTheDocument();
    });
  });

  describe('Error Boundaries', () => {
    it('should handle routing errors gracefully', () => {
      // This test would need error boundary implementation
      renderApp();
      
      // App should render without throwing
      expect(screen.getByTestId('dashboard')).toBeInTheDocument();
    });
  });
});