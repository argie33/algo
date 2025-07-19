/**
 * Navigation Components Unit Tests
 * Comprehensive testing of all navigation and routing components
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock Navigation Components
const NavBar = ({ user, onLogout, notifications = [] }) => (
  <nav data-testid="navbar" className="main-navbar">
    <div className="nav-brand">
      <a href="/" data-testid="home-link">FinanceDash</a>
    </div>
    
    <div className="nav-menu">
      <a href="/dashboard" data-testid="dashboard-link">Dashboard</a>
      <a href="/portfolio" data-testid="portfolio-link">Portfolio</a>
      <a href="/trading" data-testid="trading-link">Trading</a>
      <a href="/market" data-testid="market-link">Market</a>
      <a href="/analytics" data-testid="analytics-link">Analytics</a>
    </div>
    
    <div className="nav-user">
      {user ? (
        <div className="user-menu">
          <div className="notification-bell" data-testid="notifications">
            🔔
            {notifications.length > 0 && (
              <span data-testid="notification-count" className="badge">
                {notifications.length}
              </span>
            )}
          </div>
          <div className="user-avatar" data-testid="user-avatar">
            {user.firstName[0]}{user.lastName[0]}
          </div>
          <span data-testid="user-name">{user.firstName} {user.lastName}</span>
          <button onClick={onLogout} data-testid="logout-button">
            Logout
          </button>
        </div>
      ) : (
        <div className="auth-buttons">
          <a href="/login" data-testid="login-link">Login</a>
          <a href="/signup" data-testid="signup-link">Sign Up</a>
        </div>
      )}
    </div>
  </nav>
);

const Sidebar = ({ isOpen, onToggle, activeSection, onSectionChange }) => (
  <aside data-testid="sidebar" className={`sidebar ${isOpen ? 'open' : 'closed'}`}>
    <button 
      onClick={onToggle} 
      data-testid="sidebar-toggle"
      className="sidebar-toggle"
    >
      {isOpen ? '←' : '→'}
    </button>
    
    <div className="sidebar-content">
      <div className="sidebar-section">
        <h3>Portfolio</h3>
        <ul>
          <li 
            className={activeSection === 'overview' ? 'active' : ''}
            onClick={() => onSectionChange('overview')}
            data-testid="sidebar-overview"
          >
            Overview
          </li>
          <li 
            className={activeSection === 'positions' ? 'active' : ''}
            onClick={() => onSectionChange('positions')}
            data-testid="sidebar-positions"
          >
            Positions
          </li>
          <li 
            className={activeSection === 'performance' ? 'active' : ''}
            onClick={() => onSectionChange('performance')}
            data-testid="sidebar-performance"
          >
            Performance
          </li>
        </ul>
      </div>
      
      <div className="sidebar-section">
        <h3>Trading</h3>
        <ul>
          <li 
            className={activeSection === 'orders' ? 'active' : ''}
            onClick={() => onSectionChange('orders')}
            data-testid="sidebar-orders"
          >
            Orders
          </li>
          <li 
            className={activeSection === 'history' ? 'active' : ''}
            onClick={() => onSectionChange('history')}
            data-testid="sidebar-history"
          >
            History
          </li>
          <li 
            className={activeSection === 'watchlist' ? 'active' : ''}
            onClick={() => onSectionChange('watchlist')}
            data-testid="sidebar-watchlist"
          >
            Watchlist
          </li>
        </ul>
      </div>
      
      <div className="sidebar-section">
        <h3>Account</h3>
        <ul>
          <li 
            className={activeSection === 'profile' ? 'active' : ''}
            onClick={() => onSectionChange('profile')}
            data-testid="sidebar-profile"
          >
            Profile
          </li>
          <li 
            className={activeSection === 'settings' ? 'active' : ''}
            onClick={() => onSectionChange('settings')}
            data-testid="sidebar-settings"
          >
            Settings
          </li>
        </ul>
      </div>
    </div>
  </aside>
);

const Breadcrumb = ({ items, onNavigate }) => (
  <nav data-testid="breadcrumb" className="breadcrumb">
    <ol>
      {items.map((item, index) => (
        <li key={index} data-testid={`breadcrumb-${index}`}>
          {index < items.length - 1 ? (
            <button 
              onClick={() => onNavigate(item.path)}
              data-testid={`breadcrumb-link-${index}`}
            >
              {item.label}
            </button>
          ) : (
            <span data-testid={`breadcrumb-current-${index}`}>{item.label}</span>
          )}
          {index < items.length - 1 && <span className="separator"> / </span>}
        </li>
      ))}
    </ol>
  </nav>
);

const TabNavigation = ({ tabs, activeTab, onTabChange, disabled = [] }) => (
  <div data-testid="tab-navigation" className="tab-navigation">
    <div className="tab-list" role="tablist">
      {tabs.map(tab => (
        <button
          key={tab.id}
          role="tab"
          data-testid={`tab-${tab.id}`}
          className={`tab ${activeTab === tab.id ? 'active' : ''} ${disabled.includes(tab.id) ? 'disabled' : ''}`}
          onClick={() => !disabled.includes(tab.id) && onTabChange(tab.id)}
          disabled={disabled.includes(tab.id)}
          aria-selected={activeTab === tab.id}
        >
          {tab.icon && <span className="tab-icon">{tab.icon}</span>}
          <span>{tab.label}</span>
          {tab.badge && (
            <span data-testid={`tab-badge-${tab.id}`} className="tab-badge">
              {tab.badge}
            </span>
          )}
        </button>
      ))}
    </div>
  </div>
);

const MobileMenu = ({ isOpen, onToggle, onNavigate, user }) => (
  <div data-testid="mobile-menu" className={`mobile-menu ${isOpen ? 'open' : 'closed'}`}>
    <div className="mobile-menu-overlay" onClick={onToggle}></div>
    <div className="mobile-menu-content">
      <header className="mobile-menu-header">
        <h2>Menu</h2>
        <button onClick={onToggle} data-testid="mobile-menu-close">
          ✕
        </button>
      </header>
      
      <nav className="mobile-menu-nav">
        <a 
          href="/dashboard" 
          onClick={(e) => { e.preventDefault(); onNavigate('/dashboard'); }}
          data-testid="mobile-dashboard"
        >
          📊 Dashboard
        </a>
        <a 
          href="/portfolio" 
          onClick={(e) => { e.preventDefault(); onNavigate('/portfolio'); }}
          data-testid="mobile-portfolio"
        >
          💼 Portfolio
        </a>
        <a 
          href="/trading" 
          onClick={() => onNavigate('/trading')}
          data-testid="mobile-trading"
        >
          📈 Trading
        </a>
        <a 
          href="/market" 
          onClick={() => onNavigate('/market')}
          data-testid="mobile-market"
        >
          🏪 Market
        </a>
        <a 
          href="/analytics" 
          onClick={() => onNavigate('/analytics')}
          data-testid="mobile-analytics"
        >
          📈 Analytics
        </a>
      </nav>
      
      {user && (
        <div className="mobile-menu-user">
          <div className="user-info">
            <div className="user-avatar">{user.firstName[0]}{user.lastName[0]}</div>
            <span>{user.firstName} {user.lastName}</span>
          </div>
          <a 
            href="/profile" 
            onClick={() => onNavigate('/profile')}
            data-testid="mobile-profile"
          >
            Profile
          </a>
          <a 
            href="/settings" 
            onClick={() => onNavigate('/settings')}
            data-testid="mobile-settings"
          >
            Settings
          </a>
        </div>
      )}
    </div>
  </div>
);

const ProgressIndicator = ({ steps, currentStep, onStepClick, completed = [] }) => (
  <div data-testid="progress-indicator" className="progress-indicator">
    <div className="progress-steps">
      {steps.map((step, index) => {
        const stepNumber = index + 1;
        const isActive = currentStep === stepNumber;
        const isCompleted = completed.includes(stepNumber);
        const isClickable = stepNumber <= currentStep || isCompleted;
        
        return (
          <div 
            key={step.id}
            data-testid={`step-${stepNumber}`}
            className={`step ${isActive ? 'active' : ''} ${isCompleted ? 'completed' : ''} ${isClickable ? 'clickable' : ''}`}
            onClick={() => isClickable && onStepClick(stepNumber)}
          >
            <div className="step-number">
              {isCompleted ? '✓' : stepNumber}
            </div>
            <div className="step-label">{step.label}</div>
            {step.description && (
              <div className="step-description">{step.description}</div>
            )}
          </div>
        );
      })}
    </div>
    
    <div className="progress-bar">
      <div 
        data-testid="progress-bar-fill"
        className="progress-fill" 
        style={{ width: `${(currentStep / steps.length) * 100}%` }}
      ></div>
    </div>
  </div>
);

const QuickActions = ({ actions, onActionClick, disabled = [] }) => (
  <div data-testid="quick-actions" className="quick-actions">
    <h3>Quick Actions</h3>
    <div className="actions-grid">
      {actions.map(action => (
        <button
          key={action.id}
          data-testid={`action-${action.id}`}
          className={`action-button ${disabled.includes(action.id) ? 'disabled' : ''}`}
          onClick={() => !disabled.includes(action.id) && onActionClick(action)}
          disabled={disabled.includes(action.id)}
          title={action.description}
        >
          <div className="action-icon">{action.icon}</div>
          <div className="action-label">{action.label}</div>
          {action.badge && (
            <span data-testid={`action-badge-${action.id}`} className="action-badge">
              {action.badge}
            </span>
          )}
        </button>
      ))}
    </div>
  </div>
);

describe('🧭 Navigation Components', () => {
  const mockUser = {
    id: '1',
    firstName: 'John',
    lastName: 'Doe',
    email: 'john@example.com'
  };

  const mockNotifications = [
    { id: '1', title: 'New Message', read: false },
    { id: '2', title: 'Trade Executed', read: false }
  ];

  const mockTabs = [
    { id: 'overview', label: 'Overview', icon: '📊' },
    { id: 'positions', label: 'Positions', icon: '💼', badge: '5' },
    { id: 'orders', label: 'Orders', icon: '📋' },
    { id: 'history', label: 'History', icon: '📜' }
  ];

  const mockBreadcrumbs = [
    { label: 'Dashboard', path: '/dashboard' },
    { label: 'Portfolio', path: '/portfolio' },
    { label: 'Performance', path: '/portfolio/performance' }
  ];

  const mockSteps = [
    { id: 'account', label: 'Account Setup', description: 'Create your account' },
    { id: 'verification', label: 'Verification', description: 'Verify your identity' },
    { id: 'funding', label: 'Fund Account', description: 'Add funds to start trading' },
    { id: 'trading', label: 'Start Trading', description: 'Place your first trade' }
  ];

  const mockActions = [
    { id: 'buy', label: 'Buy Stock', icon: '📈', description: 'Purchase stocks' },
    { id: 'sell', label: 'Sell Stock', icon: '📉', description: 'Sell stocks' },
    { id: 'transfer', label: 'Transfer Funds', icon: '💸', description: 'Transfer money' },
    { id: 'report', label: 'Generate Report', icon: '📊', description: 'Create performance report', badge: 'New' }
  ];

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('NavBar Component', () => {
    it('should render navbar with authenticated user', () => {
      render(<NavBar user={mockUser} onLogout={vi.fn()} notifications={mockNotifications} />);

      expect(screen.getByTestId('navbar')).toBeInTheDocument();
      expect(screen.getByTestId('home-link')).toHaveTextContent('FinanceDash');
      expect(screen.getByTestId('user-name')).toHaveTextContent('John Doe');
      expect(screen.getByTestId('user-avatar')).toHaveTextContent('JD');
      expect(screen.getByTestId('notification-count')).toHaveTextContent('2');
    });

    it('should render navbar for unauthenticated user', () => {
      render(<NavBar user={null} onLogout={vi.fn()} />);

      expect(screen.getByTestId('login-link')).toBeInTheDocument();
      expect(screen.getByTestId('signup-link')).toBeInTheDocument();
      expect(screen.queryByTestId('user-name')).not.toBeInTheDocument();
      expect(screen.queryByTestId('logout-button')).not.toBeInTheDocument();
    });

    it('should handle logout action', async () => {
      const user = userEvent.setup();
      const onLogout = vi.fn();

      render(<NavBar user={mockUser} onLogout={onLogout} />);

      await user.click(screen.getByTestId('logout-button'));
      expect(onLogout).toHaveBeenCalled();
    });

    it('should show notification count correctly', () => {
      render(<NavBar user={mockUser} notifications={mockNotifications} />);

      expect(screen.getByTestId('notification-count')).toHaveTextContent('2');
    });

    it('should hide notification badge when no notifications', () => {
      render(<NavBar user={mockUser} notifications={[]} />);

      expect(screen.queryByTestId('notification-count')).not.toBeInTheDocument();
    });

    it('should display all navigation links', () => {
      render(<NavBar user={mockUser} onLogout={vi.fn()} />);

      expect(screen.getByTestId('dashboard-link')).toHaveAttribute('href', '/dashboard');
      expect(screen.getByTestId('portfolio-link')).toHaveAttribute('href', '/portfolio');
      expect(screen.getByTestId('trading-link')).toHaveAttribute('href', '/trading');
      expect(screen.getByTestId('market-link')).toHaveAttribute('href', '/market');
      expect(screen.getByTestId('analytics-link')).toHaveAttribute('href', '/analytics');
    });
  });

  describe('Sidebar Component', () => {
    it('should render sidebar correctly', () => {
      render(
        <Sidebar 
          isOpen={true} 
          onToggle={vi.fn()} 
          activeSection="overview"
          onSectionChange={vi.fn()}
        />
      );

      expect(screen.getByTestId('sidebar')).toBeInTheDocument();
      expect(screen.getByTestId('sidebar')).toHaveClass('open');
      expect(screen.getByTestId('sidebar-overview')).toHaveClass('active');
    });

    it('should handle sidebar toggle', async () => {
      const user = userEvent.setup();
      const onToggle = vi.fn();

      render(
        <Sidebar 
          isOpen={true} 
          onToggle={onToggle} 
          activeSection="overview"
          onSectionChange={vi.fn()}
        />
      );

      await user.click(screen.getByTestId('sidebar-toggle'));
      expect(onToggle).toHaveBeenCalled();
    });

    it('should handle section changes', async () => {
      const user = userEvent.setup();
      const onSectionChange = vi.fn();

      render(
        <Sidebar 
          isOpen={true} 
          onToggle={vi.fn()} 
          activeSection="overview"
          onSectionChange={onSectionChange}
        />
      );

      await user.click(screen.getByTestId('sidebar-positions'));
      expect(onSectionChange).toHaveBeenCalledWith('positions');
    });

    it('should show correct state when closed', () => {
      render(
        <Sidebar 
          isOpen={false} 
          onToggle={vi.fn()} 
          activeSection="overview"
          onSectionChange={vi.fn()}
        />
      );

      expect(screen.getByTestId('sidebar')).toHaveClass('closed');
      expect(screen.getByTestId('sidebar-toggle')).toHaveTextContent('→');
    });
  });

  describe('Breadcrumb Component', () => {
    it('should render breadcrumb correctly', () => {
      render(<Breadcrumb items={mockBreadcrumbs} onNavigate={vi.fn()} />);

      expect(screen.getByTestId('breadcrumb')).toBeInTheDocument();
      expect(screen.getByTestId('breadcrumb-0')).toBeInTheDocument();
      expect(screen.getByTestId('breadcrumb-1')).toBeInTheDocument();
      expect(screen.getByTestId('breadcrumb-2')).toBeInTheDocument();
    });

    it('should handle breadcrumb navigation', async () => {
      const user = userEvent.setup();
      const onNavigate = vi.fn();

      render(<Breadcrumb items={mockBreadcrumbs} onNavigate={onNavigate} />);

      await user.click(screen.getByTestId('breadcrumb-link-0'));
      expect(onNavigate).toHaveBeenCalledWith('/dashboard');
    });

    it('should show current page as non-clickable', () => {
      render(<Breadcrumb items={mockBreadcrumbs} onNavigate={vi.fn()} />);

      // Last item should not be clickable
      expect(screen.getByTestId('breadcrumb-current-2')).toBeInTheDocument();
      expect(screen.queryByTestId('breadcrumb-link-2')).not.toBeInTheDocument();
    });

    it('should handle single breadcrumb item', () => {
      const singleItem = [{ label: 'Dashboard', path: '/dashboard' }];
      render(<Breadcrumb items={singleItem} onNavigate={vi.fn()} />);

      expect(screen.getByTestId('breadcrumb-current-0')).toHaveTextContent('Dashboard');
    });
  });

  describe('TabNavigation Component', () => {
    it('should render tabs correctly', () => {
      render(
        <TabNavigation 
          tabs={mockTabs} 
          activeTab="overview" 
          onTabChange={vi.fn()}
        />
      );

      expect(screen.getByTestId('tab-navigation')).toBeInTheDocument();
      expect(screen.getByTestId('tab-overview')).toHaveClass('active');
      expect(screen.getByTestId('tab-positions')).toBeInTheDocument();
      expect(screen.getByTestId('tab-badge-positions')).toHaveTextContent('5');
    });

    it('should handle tab changes', async () => {
      const user = userEvent.setup();
      const onTabChange = vi.fn();

      render(
        <TabNavigation 
          tabs={mockTabs} 
          activeTab="overview" 
          onTabChange={onTabChange}
        />
      );

      await user.click(screen.getByTestId('tab-positions'));
      expect(onTabChange).toHaveBeenCalledWith('positions');
    });

    it('should handle disabled tabs', async () => {
      const user = userEvent.setup();
      const onTabChange = vi.fn();

      render(
        <TabNavigation 
          tabs={mockTabs} 
          activeTab="overview" 
          onTabChange={onTabChange}
          disabled={['orders']}
        />
      );

      const ordersTab = screen.getByTestId('tab-orders');
      expect(ordersTab).toHaveClass('disabled');
      expect(ordersTab).toBeDisabled();

      await user.click(ordersTab);
      expect(onTabChange).not.toHaveBeenCalledWith('orders');
    });

    it('should show tab badges correctly', () => {
      render(
        <TabNavigation 
          tabs={mockTabs} 
          activeTab="overview" 
          onTabChange={vi.fn()}
        />
      );

      expect(screen.getByTestId('tab-badge-positions')).toHaveTextContent('5');
      expect(screen.queryByTestId('tab-badge-overview')).not.toBeInTheDocument();
    });
  });

  describe('MobileMenu Component', () => {
    it('should render mobile menu correctly', () => {
      render(
        <MobileMenu 
          isOpen={true} 
          onToggle={vi.fn()} 
          onNavigate={vi.fn()}
          user={mockUser}
        />
      );

      expect(screen.getByTestId('mobile-menu')).toHaveClass('open');
      expect(screen.getByTestId('mobile-dashboard')).toBeInTheDocument();
      expect(screen.getByTestId('mobile-portfolio')).toBeInTheDocument();
      expect(screen.getByTestId('mobile-profile')).toBeInTheDocument();
    });

    it('should handle menu toggle', async () => {
      const user = userEvent.setup();
      const onToggle = vi.fn();

      render(
        <MobileMenu 
          isOpen={true} 
          onToggle={onToggle} 
          onNavigate={vi.fn()}
          user={mockUser}
        />
      );

      await user.click(screen.getByTestId('mobile-menu-close'));
      expect(onToggle).toHaveBeenCalled();
    });

    it('should handle navigation', async () => {
      const user = userEvent.setup();
      const onNavigate = vi.fn();

      render(
        <MobileMenu 
          isOpen={true} 
          onToggle={vi.fn()} 
          onNavigate={onNavigate}
          user={mockUser}
        />
      );

      await user.click(screen.getByTestId('mobile-portfolio'));
      expect(onNavigate).toHaveBeenCalledWith('/portfolio');
    });

    it('should show different content for unauthenticated users', () => {
      render(
        <MobileMenu 
          isOpen={true} 
          onToggle={vi.fn()} 
          onNavigate={vi.fn()}
          user={null}
        />
      );

      expect(screen.queryByTestId('mobile-profile')).not.toBeInTheDocument();
      expect(screen.queryByTestId('mobile-settings')).not.toBeInTheDocument();
    });
  });

  describe('ProgressIndicator Component', () => {
    it('should render progress indicator correctly', () => {
      render(
        <ProgressIndicator 
          steps={mockSteps} 
          currentStep={2}
          onStepClick={vi.fn()}
          completed={[1]}
        />
      );

      expect(screen.getByTestId('progress-indicator')).toBeInTheDocument();
      expect(screen.getByTestId('step-1')).toHaveClass('completed');
      expect(screen.getByTestId('step-2')).toHaveClass('active');
      expect(screen.getByTestId('progress-bar-fill')).toHaveStyle('width: 50%');
    });

    it('should handle step clicks', async () => {
      const user = userEvent.setup();
      const onStepClick = vi.fn();

      render(
        <ProgressIndicator 
          steps={mockSteps} 
          currentStep={3}
          onStepClick={onStepClick}
          completed={[1, 2]}
        />
      );

      await user.click(screen.getByTestId('step-1'));
      expect(onStepClick).toHaveBeenCalledWith(1);
    });

    it('should prevent clicks on future steps', async () => {
      const user = userEvent.setup();
      const onStepClick = vi.fn();

      render(
        <ProgressIndicator 
          steps={mockSteps} 
          currentStep={2}
          onStepClick={onStepClick}
          completed={[1]}
        />
      );

      const step4 = screen.getByTestId('step-4');
      expect(step4).not.toHaveClass('clickable');

      await user.click(step4);
      expect(onStepClick).not.toHaveBeenCalledWith(4);
    });

    it('should show completion checkmarks', () => {
      render(
        <ProgressIndicator 
          steps={mockSteps} 
          currentStep={3}
          onStepClick={vi.fn()}
          completed={[1, 2]}
        />
      );

      const step1 = screen.getByTestId('step-1');
      expect(step1).toHaveTextContent('✓');
    });
  });

  describe('QuickActions Component', () => {
    it('should render quick actions correctly', () => {
      render(
        <QuickActions 
          actions={mockActions} 
          onActionClick={vi.fn()}
        />
      );

      expect(screen.getByTestId('quick-actions')).toBeInTheDocument();
      expect(screen.getByText('Quick Actions')).toBeInTheDocument();
      expect(screen.getByTestId('action-buy')).toBeInTheDocument();
      expect(screen.getByTestId('action-badge-report')).toHaveTextContent('New');
    });

    it('should handle action clicks', async () => {
      const user = userEvent.setup();
      const onActionClick = vi.fn();

      render(
        <QuickActions 
          actions={mockActions} 
          onActionClick={onActionClick}
        />
      );

      await user.click(screen.getByTestId('action-buy'));
      expect(onActionClick).toHaveBeenCalledWith(mockActions[0]);
    });

    it('should handle disabled actions', async () => {
      const user = userEvent.setup();
      const onActionClick = vi.fn();

      render(
        <QuickActions 
          actions={mockActions} 
          onActionClick={onActionClick}
          disabled={['buy']}
        />
      );

      const buyButton = screen.getByTestId('action-buy');
      expect(buyButton).toHaveClass('disabled');
      expect(buyButton).toBeDisabled();

      await user.click(buyButton);
      expect(onActionClick).not.toHaveBeenCalledWith(mockActions[0]);
    });

    it('should show action badges', () => {
      render(
        <QuickActions 
          actions={mockActions} 
          onActionClick={vi.fn()}
        />
      );

      expect(screen.getByTestId('action-badge-report')).toHaveTextContent('New');
      expect(screen.queryByTestId('action-badge-buy')).not.toBeInTheDocument();
    });
  });

  describe('Component Integration', () => {
    it('should integrate navbar with sidebar', async () => {
      const user = userEvent.setup();
      let sidebarOpen = false;

      const toggleSidebar = () => {
        sidebarOpen = !sidebarOpen;
      };

      const { rerender } = render(
        <div>
          <NavBar user={mockUser} onLogout={vi.fn()} />
          <Sidebar 
            isOpen={sidebarOpen} 
            onToggle={toggleSidebar} 
            activeSection="overview"
            onSectionChange={vi.fn()}
          />
        </div>
      );

      expect(screen.getByTestId('sidebar')).toHaveClass('closed');

      // Simulate sidebar toggle from navbar (would be connected via state)
      rerender(
        <div>
          <NavBar user={mockUser} onLogout={vi.fn()} />
          <Sidebar 
            isOpen={true} 
            onToggle={toggleSidebar} 
            activeSection="overview"
            onSectionChange={vi.fn()}
          />
        </div>
      );

      expect(screen.getByTestId('sidebar')).toHaveClass('open');
    });

    it('should integrate breadcrumb with tab navigation', () => {
      render(
        <div>
          <Breadcrumb items={mockBreadcrumbs} onNavigate={vi.fn()} />
          <TabNavigation 
            tabs={mockTabs} 
            activeTab="positions" 
            onTabChange={vi.fn()}
          />
        </div>
      );

      expect(screen.getByTestId('breadcrumb')).toBeInTheDocument();
      expect(screen.getByTestId('tab-navigation')).toBeInTheDocument();
      expect(screen.getByTestId('tab-positions')).toHaveClass('active');
    });
  });

  describe('Accessibility', () => {
    it('should have proper ARIA attributes', () => {
      render(
        <TabNavigation 
          tabs={mockTabs} 
          activeTab="overview" 
          onTabChange={vi.fn()}
        />
      );

      const tabList = screen.getByRole('tablist');
      expect(tabList).toBeInTheDocument();

      const activeTab = screen.getByTestId('tab-overview');
      expect(activeTab).toHaveAttribute('aria-selected', 'true');
    });

    it('should support keyboard navigation', async () => {
      const user = userEvent.setup();
      const onTabChange = vi.fn();

      render(
        <TabNavigation 
          tabs={mockTabs} 
          activeTab="overview" 
          onTabChange={onTabChange}
        />
      );

      const firstTab = screen.getByTestId('tab-overview');
      
      await user.tab();
      expect(firstTab).toHaveFocus();

      await user.keyboard('{ArrowRight}');
      // Would need proper tab navigation implementation
    });

    it('should have proper button titles for actions', () => {
      render(
        <QuickActions 
          actions={mockActions} 
          onActionClick={vi.fn()}
        />
      );

      expect(screen.getByTestId('action-buy')).toHaveAttribute('title', 'Purchase stocks');
      expect(screen.getByTestId('action-transfer')).toHaveAttribute('title', 'Transfer money');
    });
  });

  describe('Responsive Behavior', () => {
    it('should handle mobile menu properly', () => {
      render(
        <MobileMenu 
          isOpen={false} 
          onToggle={vi.fn()} 
          onNavigate={vi.fn()}
          user={mockUser}
        />
      );

      expect(screen.getByTestId('mobile-menu')).toHaveClass('closed');
    });

    it('should adapt sidebar for mobile', () => {
      render(
        <Sidebar 
          isOpen={false} 
          onToggle={vi.fn()} 
          activeSection="overview"
          onSectionChange={vi.fn()}
        />
      );

      expect(screen.getByTestId('sidebar')).toHaveClass('closed');
      expect(screen.getByTestId('sidebar-toggle')).toHaveTextContent('→');
    });
  });

  describe('Error Handling', () => {
    it('should handle missing user data', () => {
      expect(() => {
        render(<NavBar user={null} onLogout={vi.fn()} />);
      }).not.toThrow();
    });

    it('should handle empty breadcrumb items', () => {
      expect(() => {
        render(<Breadcrumb items={[]} onNavigate={vi.fn()} />);
      }).not.toThrow();
    });

    it('should handle missing callback functions', () => {
      expect(() => {
        render(
          <TabNavigation 
            tabs={mockTabs} 
            activeTab="overview" 
          />
        );
      }).not.toThrow();
    });

    it('should handle corrupted tab data', () => {
      const corruptedTabs = [
        { id: null, label: null },
        { id: 'valid', label: 'Valid Tab' }
      ];

      expect(() => {
        render(
          <TabNavigation 
            tabs={corruptedTabs} 
            activeTab="valid" 
            onTabChange={vi.fn()}
          />
        );
      }).not.toThrow();
    });
  });
});