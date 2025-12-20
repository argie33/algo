import React from 'react';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { vi, describe, test, expect, beforeEach } from 'vitest';
import RootRedirect from '../../../components/RootRedirect';

// Mock the AuthContext
const mockUseAuth = vi.fn();
vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

// Mock MarketOverview component
vi.mock('../../../pages/MarketOverview', () => ({
  default: function MockMarketOverview() {
    return <div data-testid="market-overview">Market Overview Component</div>;
  }
}));

describe('RootRedirect Component', () => {
  const renderWithRouter = (component) => {
    return render(
      <BrowserRouter>
        {component}
      </BrowserRouter>
    );
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render MarketOverview for authenticated users', () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      user: { username: 'testuser' }
    });

    renderWithRouter(<RootRedirect />);

    expect(screen.getByTestId('market-overview')).toBeInTheDocument();
  });

  it('should render MarketOverview for unauthenticated users', () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      user: null
    });

    renderWithRouter(<RootRedirect />);

    expect(screen.getByTestId('market-overview')).toBeInTheDocument();
  });
});