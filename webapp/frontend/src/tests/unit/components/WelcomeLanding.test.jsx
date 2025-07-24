import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import { vi } from 'vitest';
import WelcomeLanding from '../../../pages/WelcomeLanding';
import { useAuth } from '../../../contexts/AuthContext';

// Mock the auth context
vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: vi.fn()
}));

// Mock react-router-dom
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate
  };
});

const theme = createTheme();

const renderWithProviders = (component) => {
  return render(
    <BrowserRouter>
      <ThemeProvider theme={theme}>
        {component}
      </ThemeProvider>
    </BrowserRouter>
  );
};

describe('WelcomeLanding Component', () => {
  const mockOnSignInClick = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: false,
      user: null
    });
  });

  it('renders welcome landing page with key elements', () => {
    renderWithProviders(<WelcomeLanding onSignInClick={mockOnSignInClick} />);
    
    // Check main heading
    expect(screen.getByText('Welcome to Your Financial Future')).toBeInTheDocument();
    
    // Check subtitle
    expect(screen.getByText(/Advanced analytics, real-time data/)).toBeInTheDocument();
    
    // Check call-to-action buttons
    expect(screen.getByRole('button', { name: /get started/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /explore markets/i })).toBeInTheDocument();
  });

  it('displays live market stats section', () => {
    renderWithProviders(<WelcomeLanding onSignInClick={mockOnSignInClick} />);
    
    expect(screen.getByText('Live Market Overview')).toBeInTheDocument();
    expect(screen.getByText('S&P 500')).toBeInTheDocument();
    expect(screen.getByText('NASDAQ')).toBeInTheDocument();
    expect(screen.getByText('DOW JONES')).toBeInTheDocument();
    expect(screen.getByText('BTC/USD')).toBeInTheDocument();
  });

  it('shows feature cards with descriptions', () => {
    renderWithProviders(<WelcomeLanding onSignInClick={mockOnSignInClick} />);
    
    // Check feature titles
    expect(screen.getByText('Real-Time Market Data')).toBeInTheDocument();
    expect(screen.getByText('Advanced Analytics')).toBeInTheDocument();
    expect(screen.getByText('Portfolio Management')).toBeInTheDocument();
    expect(screen.getByText('Enterprise Security')).toBeInTheDocument();
    expect(screen.getByText('Trading Signals')).toBeInTheDocument();
    expect(screen.getByText('Lightning Fast')).toBeInTheDocument();
    
    // Check feature descriptions
    expect(screen.getByText(/Live market feeds, real-time price updates/)).toBeInTheDocument();
    expect(screen.getByText(/AI-powered insights, technical analysis/)).toBeInTheDocument();
  });

  it('calls onSignInClick when Get Started button is clicked', () => {
    renderWithProviders(<WelcomeLanding onSignInClick={mockOnSignInClick} />);
    
    const getStartedButton = screen.getByRole('button', { name: /get started/i });
    fireEvent.click(getStartedButton);
    
    expect(mockOnSignInClick).toHaveBeenCalledTimes(1);
  });

  it('navigates to market page when Explore Markets button is clicked', () => {
    renderWithProviders(<WelcomeLanding onSignInClick={mockOnSignInClick} />);
    
    const exploreMarketsButton = screen.getByRole('button', { name: /explore markets/i });
    fireEvent.click(exploreMarketsButton);
    
    expect(mockNavigate).toHaveBeenCalledWith('/market');
  });

  it('calls onSignInClick when final CTA button is clicked', () => {
    renderWithProviders(<WelcomeLanding onSignInClick={mockOnSignInClick} />);
    
    const startJourneyButton = screen.getByRole('button', { name: /start your journey/i });
    fireEvent.click(startJourneyButton);
    
    expect(mockOnSignInClick).toHaveBeenCalledTimes(1);
  });

  it('redirects authenticated users', async () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      user: { username: 'testuser' }
    });

    renderWithProviders(<WelcomeLanding onSignInClick={mockOnSignInClick} />);
    
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/');
    });
  });

  it('has proper accessibility attributes', () => {
    renderWithProviders(<WelcomeLanding onSignInClick={mockOnSignInClick} />);
    
    // Check main heading hierarchy
    const mainHeading = screen.getByRole('heading', { level: 1 });
    expect(mainHeading).toHaveTextContent('Welcome to Your Financial Future');
    
    // Check buttons have proper labels
    const getStartedButton = screen.getByRole('button', { name: /get started/i });
    expect(getStartedButton).toBeEnabled();
  });

  it('displays market stats with proper formatting', () => {
    renderWithProviders(<WelcomeLanding onSignInClick={mockOnSignInClick} />);
    
    // Check for percentage changes (positive and negative)
    expect(screen.getByText('+1.2%')).toBeInTheDocument();
    expect(screen.getByText('-0.3%')).toBeInTheDocument();
    expect(screen.getByText('+2.4%')).toBeInTheDocument();
  });

  it('has proper responsive design elements', () => {
    renderWithProviders(<WelcomeLanding onSignInClick={mockOnSignInClick} />);
    
    // Check for grid containers (responsive layout)
    const gridContainers = document.querySelectorAll('.MuiGrid-container');
    expect(gridContainers.length).toBeGreaterThan(0);
    
    // Check for responsive button layout
    const buttonContainer = screen.getByRole('button', { name: /get started/i }).closest('div');
    expect(buttonContainer).toHaveStyle({ display: 'flex' });
  });
});

// Performance and Animation Tests
describe('WelcomeLanding Animations', () => {
  const mockOnSignInClick = vi.fn();

  beforeEach(() => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: false,
      user: null
    });
  });

  it('applies staggered animation timing', async () => {
    renderWithProviders(<WelcomeLanding onSignInClick={mockOnSignInClick} />);
    
    // Wait for animations to initialize
    await waitFor(() => {
      const fadeElements = document.querySelectorAll('[style*="transition-delay"]');
      expect(fadeElements.length).toBeGreaterThan(0);
    }, { timeout: 2000 });
  });

  it('shows feature cards with hover effects', () => {
    renderWithProviders(<WelcomeLanding onSignInClick={mockOnSignInClick} />);
    
    const featureCards = document.querySelectorAll('.MuiCard-root');
    expect(featureCards.length).toBeGreaterThan(5); // 6 feature cards expected
    
    // Check for hover transition styles
    featureCards.forEach(card => {
      expect(card).toHaveStyle({ cursor: 'pointer' });
    });
  });
});