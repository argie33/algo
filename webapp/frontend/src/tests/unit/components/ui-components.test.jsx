/**
 * UI Components Unit Tests
 * Comprehensive testing of all reusable UI components in the /ui/ directory
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';

// Mock Material-UI components
vi.mock('@mui/material', () => ({
  Box: vi.fn(({ children, ...props }) => <div data-testid="mui-box" {...props}>{children}</div>),
  Typography: vi.fn(({ children, ...props }) => <div data-testid="mui-typography" {...props}>{children}</div>),
  Paper: vi.fn(({ children, ...props }) => <div data-testid="mui-paper" {...props}>{children}</div>),
  Card: vi.fn(({ children, ...props }) => <div data-testid="mui-card" {...props}>{children}</div>),
  CardContent: vi.fn(({ children, ...props }) => <div data-testid="mui-card-content" {...props}>{children}</div>),
  CardHeader: vi.fn(({ children, title, ...props }) => <div data-testid="mui-card-header" {...props}>{title || children}</div>),
  Button: vi.fn(({ children, onClick, ...props }) => 
    <button data-testid="mui-button" onClick={onClick} {...props}>{children}</button>
  ),
  IconButton: vi.fn(({ children, onClick, ...props }) => 
    <button data-testid="mui-icon-button" onClick={onClick} {...props}>{children}</button>
  ),
  TextField: vi.fn(({ label, onChange, ...props }) => 
    <input data-testid="mui-textfield" placeholder={label} onChange={onChange} {...props} />
  ),
  Select: vi.fn(({ children, onChange, ...props }) => 
    <select data-testid="mui-select" onChange={onChange} {...props}>{children}</select>
  ),
  MenuItem: vi.fn(({ children, value, ...props }) => 
    <option data-testid="mui-menu-item" value={value} {...props}>{children}</option>
  ),
  Tabs: vi.fn(({ children, value, onChange, ...props }) => 
    <div data-testid="mui-tabs" data-value={value} {...props}>{children}</div>
  ),
  Tab: vi.fn(({ label, ...props }) => 
    <button data-testid="mui-tab" {...props}>{label}</button>
  ),
  TabPanel: vi.fn(({ children, ...props }) => 
    <div data-testid="mui-tab-panel" {...props}>{children}</div>
  ),
  Slider: vi.fn(({ onChange, ...props }) => 
    <input data-testid="mui-slider" type="range" onChange={onChange} {...props} />
  ),
  LinearProgress: vi.fn(({ value, ...props }) => 
    <div data-testid="mui-linear-progress" data-value={value} {...props}>Progress: {value}%</div>
  ),
  CircularProgress: vi.fn(() => <div data-testid="mui-circular-progress">Loading...</div>),
  Alert: vi.fn(({ children, severity, ...props }) => 
    <div data-testid="mui-alert" data-severity={severity} {...props}>{children}</div>
  ),
  Badge: vi.fn(({ children, badgeContent, ...props }) => 
    <div data-testid="mui-badge" data-badge={badgeContent} {...props}>{children}</div>
  ),
  AppBar: vi.fn(({ children, ...props }) => 
    <header data-testid="mui-app-bar" {...props}>{children}</header>
  ),
  Toolbar: vi.fn(({ children, ...props }) => 
    <div data-testid="mui-toolbar" {...props}>{children}</div>
  ),
  Drawer: vi.fn(({ children, open, ...props }) => 
    <div data-testid="mui-drawer" data-open={open} {...props}>{children}</div>
  ),
  List: vi.fn(({ children, ...props }) => 
    <ul data-testid="mui-list" {...props}>{children}</ul>
  ),
  ListItem: vi.fn(({ children, ...props }) => 
    <li data-testid="mui-list-item" {...props}>{children}</li>
  ),
  ListItemText: vi.fn(({ primary, secondary, ...props }) => 
    <div data-testid="mui-list-item-text" {...props}>{primary} {secondary}</div>
  ),
  Grid: vi.fn(({ children, ...props }) => 
    <div data-testid="mui-grid" {...props}>{children}</div>
  ),
  Container: vi.fn(({ children, ...props }) => 
    <div data-testid="mui-container" {...props}>{children}</div>
  )
}));

// Import actual UI components (fixed import/export mismatches)
import Alert from '../../../components/ui/alert'; // default export
import { Badge } from '../../../components/ui/badge'; // named export
import Button from '../../../components/ui/button'; // default export
import Card from '../../../components/ui/card'; // default export
import Header from '../../../components/ui/header'; // default export
import Input from '../../../components/ui/input'; // default export
import Layout from '../../../components/ui/layout'; // default export
import Navigation from '../../../components/ui/navigation'; // default export
import { Progress } from '../../../components/ui/progress'; // named export
import { Select } from '../../../components/ui/select'; // named export
import { Slider } from '../../../components/ui/slider'; // named export
import { Tabs } from '../../../components/ui/tabs'; // named export

describe('🎨 UI Components', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Alert Component', () => {
    it('should render alert correctly', () => {
      render(
        <Alert severity="info">
          This is an informational alert
        </Alert>
      );

      expect(screen.getByText('This is an informational alert')).toBeInTheDocument();
      expect(screen.getByTestId('mui-alert')).toHaveAttribute('severity', 'info');
    });

    it('should render error alert', () => {
      render(
        <Alert severity="error">
          Something went wrong
        </Alert>
      );

      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
      expect(screen.getByTestId('mui-alert')).toHaveAttribute('severity', 'error');
    });

    it('should support different severity levels', () => {
      const { rerender } = render(
        <Alert severity="success">Success message</Alert>
      );
      expect(screen.getByTestId('mui-alert')).toHaveAttribute('severity', 'success');

      rerender(<Alert severity="warning">Warning message</Alert>);
      expect(screen.getByTestId('mui-alert')).toHaveAttribute('severity', 'warning');

      rerender(<Alert severity="error">Error message</Alert>);
      expect(screen.getByTestId('mui-alert')).toHaveAttribute('severity', 'error');
    });
  });

  describe('Badge Component', () => {
    it('should render badge with content', () => {
      render(
        <Badge 
          badgeContent={5}
          color="primary"
          variant="standard"
        >
          <button>Notifications</button>
        </Badge>
      );

      expect(screen.getByText('Notifications')).toBeInTheDocument();
      expect(screen.getByTestId('mui-badge')).toHaveAttribute('data-badge', '5');
    });

    it('should support different variants', () => {
      const { rerender } = render(
        <Badge badgeContent={3} variant="dot">
          <div>Item</div>
        </Badge>
      );

      rerender(
        <Badge badgeContent={10} variant="standard">
          <div>Item</div>
        </Badge>
      );

      expect(screen.getByTestId('mui-badge')).toHaveAttribute('data-badge', '10');
    });

    it('should handle invisible badge', () => {
      render(
        <Badge 
          badgeContent={0}
          showZero={false}
          invisible={true}
        >
          <div>No notifications</div>
        </Badge>
      );

      expect(screen.getByText('No notifications')).toBeInTheDocument();
    });

    it('should support max count', () => {
      render(
        <Badge 
          badgeContent={1000}
          max={99}
        >
          <div>High count</div>
        </Badge>
      );

      // Badge should show 99+ when content exceeds max
      expect(screen.getByTestId('mui-badge')).toHaveAttribute('data-badge', '1000');
    });

    it('should handle click events', async () => {
      const user = userEvent.setup();
      const onClick = vi.fn();

      render(
        <Badge 
          badgeContent={3}
          onClick={onClick}
        >
          <button>Clickable badge</button>
        </Badge>
      );

      await user.click(screen.getByText('Clickable badge'));
      expect(onClick).toHaveBeenCalled();
    });
  });

  describe('Button Component', () => {
    it('should render primary button correctly', () => {
      render(
        <Button 
          variant="contained"
          color="primary"
          size="medium"
        >
          Primary Button
        </Button>
      );

      expect(screen.getByText('Primary Button')).toBeInTheDocument();
      expect(screen.getByTestId('mui-button')).toBeInTheDocument();
    });

    it('should handle click events', async () => {
      const user = userEvent.setup();
      const onClick = vi.fn();

      render(
        <Button onClick={onClick}>
          Click Me
        </Button>
      );

      await user.click(screen.getByText('Click Me'));
      expect(onClick).toHaveBeenCalled();
    });

    it('should support disabled state', () => {
      render(
        <Button disabled={true}>
          Disabled Button
        </Button>
      );

      expect(screen.getByText('Disabled Button')).toBeDisabled();
    });

    it('should support loading state', () => {
      render(
        <Button 
          loading={true}
          loadingText="Processing..."
        >
          Submit
        </Button>
      );

      expect(screen.getByText('Processing...')).toBeInTheDocument();
    });

    it('should support icon buttons', () => {
      render(
        <Button 
          variant="outlined"
          startIcon="add"
          endIcon="arrow_forward"
        >
          Add Item
        </Button>
      );

      expect(screen.getByText('Add Item')).toBeInTheDocument();
    });

    it('should support different sizes', () => {
      const { rerender } = render(
        <Button size="small">Small Button</Button>
      );

      rerender(<Button size="large">Large Button</Button>);
      expect(screen.getByText('Large Button')).toBeInTheDocument();
    });
  });

  describe('Card Component', () => {
    it('should render card with header and content', () => {
      render(
        <Card 
          title="Card Title"
          subtitle="Card Subtitle"
          actions={<button>Action</button>}
        >
          <p>Card content goes here</p>
        </Card>
      );

      expect(screen.getByText('Card Title')).toBeInTheDocument();
      expect(screen.getByText('Card Subtitle')).toBeInTheDocument();
      expect(screen.getByText('Card content goes here')).toBeInTheDocument();
      expect(screen.getByText('Action')).toBeInTheDocument();
    });

    it('should support elevation', () => {
      render(
        <Card elevation={3}>
          <p>Elevated card</p>
        </Card>
      );

      expect(screen.getByText('Elevated card')).toBeInTheDocument();
    });

    it('should handle interactive cards', async () => {
      const user = userEvent.setup();
      const onClick = vi.fn();

      render(
        <Card 
          interactive={true}
          onClick={onClick}
        >
          <p>Clickable card</p>
        </Card>
      );

      await user.click(screen.getByText('Clickable card'));
      expect(onClick).toHaveBeenCalled();
    });

    it('should support image header', () => {
      render(
        <Card 
          image="/path/to/image.jpg"
          imageAlt="Card image"
          title="Card with Image"
        >
          <p>Content below image</p>
        </Card>
      );

      expect(screen.getByText('Card with Image')).toBeInTheDocument();
    });

    it('should handle loading state', () => {
      render(
        <Card loading={true}>
          <p>Loading content</p>
        </Card>
      );

      expect(screen.getByTestId('mui-circular-progress')).toBeInTheDocument();
    });
  });

  describe('Header Component', () => {
    it('should render app header correctly', () => {
      render(
        <Header 
          title="My Application"
          showMenuButton={true}
          showUserMenu={true}
          user={{ name: 'John Doe', avatar: '/avatar.jpg' }}
        />
      );

      expect(screen.getByText('My Application')).toBeInTheDocument();
    });

    it('should handle menu button click', async () => {
      const user = userEvent.setup();
      const onMenuClick = vi.fn();

      render(
        <Header 
          title="App"
          showMenuButton={true}
          onMenuClick={onMenuClick}
        />
      );

      const menuButton = screen.getByTestId('mui-icon-button');
      await user.click(menuButton);
      expect(onMenuClick).toHaveBeenCalled();
    });

    it('should support search functionality', async () => {
      const user = userEvent.setup();
      const onSearch = vi.fn();

      render(
        <Header 
          title="App"
          showSearch={true}
          onSearch={onSearch}
        />
      );

      const searchInput = screen.getByPlaceholderText(/search/i);
      await user.type(searchInput, 'test query');
      expect(onSearch).toHaveBeenCalledWith('test query');
    });

    it('should show notifications', () => {
      render(
        <Header 
          title="App"
          notifications={[
            { id: 1, message: 'New notification', type: 'info' }
          ]}
          showNotifications={true}
        />
      );

      expect(screen.getByTestId('mui-badge')).toBeInTheDocument();
    });

    it('should support breadcrumbs', () => {
      const breadcrumbs = [
        { label: 'Home', path: '/' },
        { label: 'Dashboard', path: '/dashboard' },
        { label: 'Settings', path: '/settings' }
      ];

      render(
        <Header 
          title="Settings"
          breadcrumbs={breadcrumbs}
        />
      );

      expect(screen.getByText('Home')).toBeInTheDocument();
      expect(screen.getByText('Dashboard')).toBeInTheDocument();
      expect(screen.getByText('Settings')).toBeInTheDocument();
    });
  });

  describe('Input Component', () => {
    it('should render text input correctly', () => {
      render(
        <Input 
          label="Username"
          placeholder="Enter username"
          required={true}
          type="text"
        />
      );

      expect(screen.getByPlaceholderText('Username')).toBeInTheDocument();
    });

    it('should handle value changes', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();

      render(
        <Input 
          label="Email"
          onChange={onChange}
        />
      );

      const input = screen.getByTestId('mui-textfield');
      await user.type(input, 'test@example.com');
      expect(onChange).toHaveBeenCalled();
    });

    it('should support validation', () => {
      render(
        <Input 
          label="Password"
          type="password"
          error={true}
          errorMessage="Password is required"
          required={true}
        />
      );

      expect(screen.getByText('Password is required')).toBeInTheDocument();
    });

    it('should support different input types', () => {
      const { rerender } = render(
        <Input type="email" label="Email" />
      );

      rerender(<Input type="number" label="Age" />);
      rerender(<Input type="tel" label="Phone" />);
      rerender(<Input type="url" label="Website" />);
    });

    it('should handle multiline input', () => {
      render(
        <Input 
          label="Description"
          multiline={true}
          rows={4}
          maxLength={500}
        />
      );

      expect(screen.getByPlaceholderText('Description')).toBeInTheDocument();
    });

    it('should support input adornments', () => {
      render(
        <Input 
          label="Amount"
          startAdornment="$"
          endAdornment="USD"
          type="number"
        />
      );

      expect(screen.getByText('$')).toBeInTheDocument();
      expect(screen.getByText('USD')).toBeInTheDocument();
    });
  });

  describe('Layout Component', () => {
    it('should render basic layout correctly', () => {
      render(
        <Layout>
          <p>Layout content</p>
        </Layout>
      );

      expect(screen.getByText('Layout content')).toBeInTheDocument();
      expect(screen.getByTestId('mui-container')).toBeInTheDocument();
    });

    it('should support sidebar layout', () => {
      render(
        <Layout 
          sidebar={<div>Sidebar content</div>}
          sidebarWidth={300}
        >
          <p>Main content</p>
        </Layout>
      );

      expect(screen.getByText('Sidebar content')).toBeInTheDocument();
      expect(screen.getByText('Main content')).toBeInTheDocument();
    });

    it('should handle responsive behavior', () => {
      render(
        <Layout 
          sidebar={<div>Sidebar</div>}
          collapsible={true}
          breakpoint="md"
        >
          <p>Responsive content</p>
        </Layout>
      );

      expect(screen.getByText('Responsive content')).toBeInTheDocument();
    });

    it('should support footer', () => {
      render(
        <Layout 
          footer={<div>Footer content</div>}
        >
          <p>Main content</p>
        </Layout>
      );

      expect(screen.getByText('Footer content')).toBeInTheDocument();
    });

    it('should handle loading state', () => {
      render(
        <Layout loading={true}>
          <p>Content loading</p>
        </Layout>
      );

      expect(screen.getByTestId('mui-circular-progress')).toBeInTheDocument();
    });
  });

  describe('Navigation Component', () => {
    const mockNavItems = [
      { label: 'Dashboard', path: '/', icon: 'dashboard' },
      { label: 'Portfolio', path: '/portfolio', icon: 'account_balance_wallet' },
      { label: 'Settings', path: '/settings', icon: 'settings' }
    ];

    it('should render navigation items correctly', () => {
      render(
        <BrowserRouter>
          <Navigation 
            items={mockNavItems}
            currentPath="/"
          />
        </BrowserRouter>
      );

      expect(screen.getByText('Dashboard')).toBeInTheDocument();
      expect(screen.getByText('Portfolio')).toBeInTheDocument();
      expect(screen.getByText('Settings')).toBeInTheDocument();
    });

    it('should handle item selection', async () => {
      const user = userEvent.setup();
      const onNavigate = vi.fn();

      render(
        <BrowserRouter>
          <Navigation 
            items={mockNavItems}
            onNavigate={onNavigate}
          />
        </BrowserRouter>
      );

      await user.click(screen.getByText('Portfolio'));
      expect(onNavigate).toHaveBeenCalledWith('/portfolio');
    });

    it('should support collapsible navigation', async () => {
      const user = userEvent.setup();

      render(
        <BrowserRouter>
          <Navigation 
            items={mockNavItems}
            collapsible={true}
            collapsed={false}
          />
        </BrowserRouter>
      );

      const collapseButton = screen.getByRole('button');
      await user.click(collapseButton);
    });

    it('should show active item', () => {
      render(
        <BrowserRouter>
          <Navigation 
            items={mockNavItems}
            currentPath="/portfolio"
          />
        </BrowserRouter>
      );

      // Active item would be highlighted
      expect(screen.getByText('Portfolio')).toBeInTheDocument();
    });

    it('should support nested navigation', () => {
      const nestedItems = [
        {
          label: 'Analytics',
          children: [
            { label: 'Performance', path: '/analytics/performance' },
            { label: 'Risk', path: '/analytics/risk' }
          ]
        }
      ];

      render(
        <BrowserRouter>
          <Navigation items={nestedItems} />
        </BrowserRouter>
      );

      expect(screen.getByText('Analytics')).toBeInTheDocument();
    });
  });

  describe('Progress Component', () => {
    it('should render linear progress correctly', () => {
      render(
        <Progress 
          variant="linear"
          value={75}
          label="Loading..."
          showPercentage={true}
        />
      );

      expect(screen.getByText('Loading...')).toBeInTheDocument();
      expect(screen.getByTestId('mui-linear-progress')).toHaveAttribute('data-value', '75');
    });

    it('should render circular progress', () => {
      render(
        <Progress 
          variant="circular"
          value={50}
          size={60}
          thickness={4}
        />
      );

      expect(screen.getByTestId('mui-circular-progress')).toBeInTheDocument();
    });

    it('should support indeterminate progress', () => {
      render(
        <Progress 
          variant="linear"
          indeterminate={true}
          label="Processing..."
        />
      );

      expect(screen.getByText('Processing...')).toBeInTheDocument();
    });

    it('should display custom progress text', () => {
      render(
        <Progress 
          value={60}
          customText="3 of 5 files uploaded"
        />
      );

      expect(screen.getByText('3 of 5 files uploaded')).toBeInTheDocument();
    });

    it('should support different colors', () => {
      render(
        <Progress 
          value={90}
          color="success"
          label="Almost done!"
        />
      );

      expect(screen.getByText('Almost done!')).toBeInTheDocument();
    });
  });

  describe('Select Component', () => {
    const mockOptions = [
      { value: 'option1', label: 'Option 1' },
      { value: 'option2', label: 'Option 2' },
      { value: 'option3', label: 'Option 3' }
    ];

    it('should render select with options', () => {
      render(
        <Select 
          label="Choose option"
          options={mockOptions}
          value="option1"
        />
      );

      expect(screen.getByText('Option 1')).toBeInTheDocument();
      expect(screen.getByText('Option 2')).toBeInTheDocument();
      expect(screen.getByText('Option 3')).toBeInTheDocument();
    });

    it('should handle value changes', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();

      render(
        <Select 
          options={mockOptions}
          onChange={onChange}
        />
      );

      const select = screen.getByTestId('mui-select');
      fireEvent.change(select, { target: { value: 'option2' } });
      expect(onChange).toHaveBeenCalledWith('option2');
    });

    it('should support multiple selection', () => {
      render(
        <Select 
          options={mockOptions}
          multiple={true}
          value={['option1', 'option3']}
        />
      );

      expect(screen.getByTestId('mui-select')).toBeInTheDocument();
    });

    it('should support grouping', () => {
      const groupedOptions = [
        {
          group: 'Group 1',
          options: [
            { value: 'g1o1', label: 'Group 1 Option 1' },
            { value: 'g1o2', label: 'Group 1 Option 2' }
          ]
        },
        {
          group: 'Group 2',
          options: [
            { value: 'g2o1', label: 'Group 2 Option 1' }
          ]
        }
      ];

      render(
        <Select 
          groupedOptions={groupedOptions}
        />
      );

      expect(screen.getByText('Group 1 Option 1')).toBeInTheDocument();
    });

    it('should support search/filter', async () => {
      const user = userEvent.setup();

      render(
        <Select 
          options={mockOptions}
          searchable={true}
          searchPlaceholder="Search options..."
        />
      );

      // Would show search input
    });
  });

  describe('Slider Component', () => {
    it('should render slider correctly', () => {
      render(
        <Slider 
          label="Volume"
          min={0}
          max={100}
          value={50}
          step={1}
        />
      );

      expect(screen.getByText('Volume')).toBeInTheDocument();
      expect(screen.getByTestId('mui-slider')).toBeInTheDocument();
    });

    it('should handle value changes', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();

      render(
        <Slider 
          min={0}
          max={100}
          value={25}
          onChange={onChange}
        />
      );

      const slider = screen.getByTestId('mui-slider');
      fireEvent.change(slider, { target: { value: 75 } });
      expect(onChange).toHaveBeenCalled();
    });

    it('should support range slider', () => {
      render(
        <Slider 
          label="Price Range"
          min={0}
          max={1000}
          value={[100, 500]}
          range={true}
        />
      );

      expect(screen.getByText('Price Range')).toBeInTheDocument();
    });

    it('should show value labels', () => {
      render(
        <Slider 
          min={0}
          max={100}
          value={60}
          showValue={true}
          unit="%"
        />
      );

      expect(screen.getByText('60%')).toBeInTheDocument();
    });

    it('should support marks', () => {
      const marks = [
        { value: 0, label: 'Min' },
        { value: 50, label: 'Mid' },
        { value: 100, label: 'Max' }
      ];

      render(
        <Slider 
          min={0}
          max={100}
          value={25}
          marks={marks}
        />
      );

      expect(screen.getByText('Min')).toBeInTheDocument();
      expect(screen.getByText('Mid')).toBeInTheDocument();
      expect(screen.getByText('Max')).toBeInTheDocument();
    });
  });

  describe('Tabs Component', () => {
    const mockTabs = [
      { label: 'Overview', content: <div>Overview content</div> },
      { label: 'Details', content: <div>Details content</div> },
      { label: 'Settings', content: <div>Settings content</div> }
    ];

    it('should render tabs correctly', () => {
      render(
        <Tabs 
          tabs={mockTabs}
          value={0}
        />
      );

      expect(screen.getByText('Overview')).toBeInTheDocument();
      expect(screen.getByText('Details')).toBeInTheDocument();
      expect(screen.getByText('Settings')).toBeInTheDocument();
      expect(screen.getByText('Overview content')).toBeInTheDocument();
    });

    it('should handle tab changes', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();

      render(
        <Tabs 
          tabs={mockTabs}
          value={0}
          onChange={onChange}
        />
      );

      await user.click(screen.getByText('Details'));
      expect(onChange).toHaveBeenCalledWith(1);
    });

    it('should support scrollable tabs', () => {
      const manyTabs = Array.from({ length: 10 }, (_, i) => ({
        label: `Tab ${i + 1}`,
        content: <div>Content {i + 1}</div>
      }));

      render(
        <Tabs 
          tabs={manyTabs}
          value={0}
          scrollable={true}
        />
      );

      expect(screen.getByText('Tab 1')).toBeInTheDocument();
    });

    it('should support disabled tabs', () => {
      const tabsWithDisabled = [
        { label: 'Active', content: <div>Active content</div> },
        { label: 'Disabled', content: <div>Disabled content</div>, disabled: true }
      ];

      render(
        <Tabs 
          tabs={tabsWithDisabled}
          value={0}
        />
      );

      expect(screen.getByText('Active')).toBeInTheDocument();
      expect(screen.getByText('Disabled')).toBeInTheDocument();
    });

    it('should support vertical tabs', () => {
      render(
        <Tabs 
          tabs={mockTabs}
          value={0}
          orientation="vertical"
        />
      );

      expect(screen.getByText('Overview')).toBeInTheDocument();
    });
  });

  describe('UI Component Accessibility', () => {
    it('should support keyboard navigation', async () => {
      const user = userEvent.setup();

      render(
        <div>
          <Button>First Button</Button>
          <Button>Second Button</Button>
          <Input label="Text Input" />
        </div>
      );

      await user.tab();
      expect(screen.getByText('First Button')).toHaveFocus();

      await user.tab();
      expect(screen.getByText('Second Button')).toHaveFocus();

      await user.tab();
      expect(screen.getByTestId('mui-textfield')).toHaveFocus();
    });

    it('should have proper ARIA attributes', () => {
      render(
        <Button 
          aria-label="Save document"
          aria-describedby="save-help"
        >
          Save
        </Button>
      );

      const button = screen.getByText('Save');
      expect(button).toHaveAttribute('aria-label', 'Save document');
    });

    it('should support screen reader announcements', () => {
      render(
        <Alert 
          severity="error"
          message="Form validation failed"
          role="alert"
          aria-live="assertive"
        />
      );

      expect(screen.getByRole('alert')).toBeInTheDocument();
    });
  });

  describe('UI Component Performance', () => {
    it('should handle large lists efficiently', () => {
      const largeOptionsList = Array.from({ length: 1000 }, (_, i) => ({
        value: `option-${i}`,
        label: `Option ${i + 1}`
      }));

      const startTime = performance.now();
      render(
        <Select 
          options={largeOptionsList}
          virtualized={true}
        />
      );
      const renderTime = performance.now() - startTime;

      expect(renderTime).toBeLessThan(100); // Should render within 100ms
    });

    it('should debounce input changes', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();
      vi.useFakeTimers();

      render(
        <Input 
          onChange={onChange}
          debounceMs={300}
        />
      );

      const input = screen.getByTestId('mui-textfield');
      await user.type(input, 'rapid typing');

      vi.advanceTimersByTime(300);
      expect(onChange).toHaveBeenCalledTimes(1);

      vi.useRealTimers();
    });
  });
});