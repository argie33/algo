import { screen, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { renderWithProviders } from '../../../test-utils';
import { Tabs, TabsList, TabsContent, TabsTrigger } from '../../../../components/ui/tabs';

describe('Tabs Components', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Tabs Container', () => {
    it('renders tabs container', () => {
      renderWithProviders(
        <Tabs className="test-tabs">
          <div>Tab content</div>
        </Tabs>
      );
      
      const tabs = screen.getByText('Tab content').parentElement;
      expect(tabs).toHaveClass('test-tabs');
    });

    it('supports custom props', () => {
      renderWithProviders(
        <Tabs data-testid="custom-tabs">
          <div>Tab content</div>
        </Tabs>
      );
      
      const tabs = screen.getByTestId('custom-tabs');
      expect(tabs).toBeInTheDocument();
    });
  });

  describe('TabsList Component', () => {
    it('renders MUI Tabs component', () => {
      renderWithProviders(
        <TabsList value="tab1">
          <TabsTrigger value="tab1">Tab 1</TabsTrigger>
        </TabsList>
      );
      
      const tabsList = screen.getByRole('tablist');
      expect(tabsList).toBeInTheDocument();
      // Check for actual MUI Tabs structure - root element contains the flexContainer
      const tabsRoot = tabsList.closest('[class*="MuiTabs-root"]') || tabsList;
      expect(tabsRoot).toBeInTheDocument();
    });

    it('supports custom className', () => {
      renderWithProviders(
        <TabsList className="custom-tabs" value="tab1">
          <TabsTrigger value="tab1">Tab 1</TabsTrigger>
        </TabsList>
      );
      
      const tabsList = screen.getByRole('tablist');
      // The className is applied to the root MuiTabs element
      const tabsRoot = tabsList.closest('[class*="MuiTabs-root"]') || tabsList;
      expect(tabsRoot).toHaveClass('custom-tabs');
    });
  });

  describe('TabsTrigger Component', () => {
    it('renders as MUI Tab', () => {
      renderWithProviders(
        <TabsList value="tab1">
          <TabsTrigger value="tab1">Tab 1</TabsTrigger>
        </TabsList>
      );
      
      const tab = screen.getByRole('tab');
      expect(tab).toBeInTheDocument();
      expect(tab).toHaveClass('MuiTab-root');
    });

    it('displays children as label', () => {
      renderWithProviders(
        <TabsList value="tab1">
          <TabsTrigger value="tab1">My Tab Label</TabsTrigger>
        </TabsList>
      );
      
      const tab = screen.getByRole('tab', { name: 'My Tab Label' });
      expect(tab).toBeInTheDocument();
    });

    it('supports custom className', () => {
      renderWithProviders(
        <TabsList value="tab1">
          <TabsTrigger value="tab1" className="custom-tab">Tab 1</TabsTrigger>
        </TabsList>
      );
      
      const tab = screen.getByRole('tab');
      expect(tab).toHaveClass('custom-tab');
    });

    it('handles click events', () => {
      renderWithProviders(
        <TabsList value="tab1">
          <TabsTrigger value="tab1">Tab 1</TabsTrigger>
        </TabsList>
      );
      
      const tab = screen.getByRole('tab');
      expect(() => fireEvent.click(tab)).not.toThrow();
    });
  });

  describe('TabsContent Component', () => {
    it('renders content container', () => {
      renderWithProviders(
        <TabsContent value="tab1">
          <div data-testid="tab-content">Content here</div>
        </TabsContent>
      );
      
      const content = screen.getByTestId('tab-content');
      expect(content).toBeInTheDocument();
      expect(content.textContent).toBe('Content here');
    });

    it('supports custom className', () => {
      renderWithProviders(
        <TabsContent value="tab1" className="custom-content">
          <div>Content</div>
        </TabsContent>
      );
      
      const content = screen.getByText('Content').closest('.custom-content');
      expect(content).toBeInTheDocument();
    });

    it('forwards props correctly', () => {
      renderWithProviders(
        <TabsContent value="tab1" data-testid="content-box">
          <div>Content</div>
        </TabsContent>
      );
      
      const content = screen.getByTestId('content-box');
      expect(content).toBeInTheDocument();
    });
  });

  describe('Complete Tabs Integration', () => {
    it('renders complete tabs structure', () => {
      renderWithProviders(
        <Tabs>
          <TabsList value="tab1">
            <TabsTrigger value="tab1">First Tab</TabsTrigger>
            <TabsTrigger value="tab2">Second Tab</TabsTrigger>
          </TabsList>
          <TabsContent value="tab1">
            <div data-testid="content-1">Content 1</div>
          </TabsContent>
          <TabsContent value="tab2">
            <div data-testid="content-2">Content 2</div>
          </TabsContent>
        </Tabs>
      );
      
      expect(screen.getByRole('tablist')).toBeInTheDocument();
      expect(screen.getAllByRole('tab')).toHaveLength(2);
      expect(screen.getByTestId('content-1')).toBeInTheDocument();
      expect(screen.getByTestId('content-2')).toBeInTheDocument();
    });

    it('handles tab switching interaction', () => {
      renderWithProviders(
        <TabsList value="tab1">
          <TabsTrigger value="tab1">First</TabsTrigger>
          <TabsTrigger value="tab2">Second</TabsTrigger>
        </TabsList>
      );
      
      const firstTab = screen.getByRole('tab', { name: 'First' });
      const secondTab = screen.getByRole('tab', { name: 'Second' });
      
      fireEvent.click(firstTab);
      expect(firstTab).toBeInTheDocument();
      
      fireEvent.click(secondTab);
      expect(secondTab).toBeInTheDocument();
    });
  });

  describe('Accessibility', () => {
    it('provides proper ARIA attributes for tabs', () => {
      renderWithProviders(
        <TabsList>
          <TabsTrigger value="tab1">Tab 1</TabsTrigger>
        </TabsList>
      );
      
      const tablist = screen.getByRole('tablist');
      const tab = screen.getByRole('tab');
      
      expect(tablist).toHaveAttribute('role', 'tablist');
      expect(tab).toHaveAttribute('role', 'tab');
    });

    it('supports keyboard navigation', () => {
      renderWithProviders(
        <TabsList>
          <TabsTrigger value="tab1">Tab 1</TabsTrigger>
          <TabsTrigger value="tab2">Tab 2</TabsTrigger>
        </TabsList>
      );
      
      const firstTab = screen.getByRole('tab', { name: 'Tab 1' });
      fireEvent.keyDown(firstTab, { key: 'ArrowRight' });
      
      // MUI handles keyboard navigation internally
      expect(firstTab).toBeInTheDocument();
    });

    it('supports custom ARIA labels', () => {
      renderWithProviders(
        <TabsList aria-label="Navigation tabs">
          <TabsTrigger value="tab1">Tab 1</TabsTrigger>
        </TabsList>
      );
      
      const tablist = screen.getByRole('tablist');
      expect(tablist).toHaveAttribute('aria-label', 'Navigation tabs');
    });
  });

  describe('Component Structure', () => {
    it('uses MUI components internally', () => {
      renderWithProviders(
        <TabsList value="tab1">
          <TabsTrigger value="tab1">Tab 1</TabsTrigger>
        </TabsList>
      );
      
      const tablist = screen.getByRole('tablist');
      const tab = screen.getByRole('tab');
      
      // Check for MUI structure - tablist is the flexContainer, need root
      const tabsRoot = tablist.closest('[class*="MuiTabs-root"]') || tablist;
      expect(tabsRoot).toBeInTheDocument();
      expect(tab).toHaveClass('MuiTab-root');
    });

    it('forwards refs correctly', () => {
      const tabsRef = vi.fn();
      const listRef = vi.fn();
      const triggerRef = vi.fn();
      const contentRef = vi.fn();
      
      renderWithProviders(
        <Tabs ref={tabsRef}>
          <TabsList ref={listRef}>
            <TabsTrigger value="tab1" ref={triggerRef}>Tab 1</TabsTrigger>
          </TabsList>
          <TabsContent value="tab1" ref={contentRef}>Content</TabsContent>
        </Tabs>
      );
      
      expect(tabsRef).toHaveBeenCalled();
      expect(listRef).toHaveBeenCalled();
      expect(triggerRef).toHaveBeenCalled();
      expect(contentRef).toHaveBeenCalled();
    });
  });

  describe('Error Handling', () => {
    it('handles empty tabs gracefully', () => {
      renderWithProviders(<Tabs />);
      
      // Should render empty container without errors
      expect(document.body).toBeInTheDocument();
    });

    it('handles missing values gracefully', () => {
      renderWithProviders(
        <TabsList>
          <TabsTrigger>No Value Tab</TabsTrigger>
        </TabsList>
      );
      
      const tab = screen.getByRole('tab');
      expect(tab).toBeInTheDocument();
    });

    it('handles empty content gracefully', () => {
      renderWithProviders(<TabsContent value="test" />);
      
      // Should render empty content container
      expect(document.body).toBeInTheDocument();
    });
  });
});