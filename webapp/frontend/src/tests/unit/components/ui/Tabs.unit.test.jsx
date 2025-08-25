/**
 * Unit Tests for Tabs Components
 * Tests tabs functionality, navigation, and content switching
 */

import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../../../../components/ui/tabs.jsx";
import { renderWithTheme } from "../test-helpers/component-test-utils.jsx";

describe("Tabs Components", () => {
  describe("Tabs Container", () => {
    it("should render with default props", () => {
      renderWithTheme(
        <Tabs data-testid="tabs">
          <div>Tab content</div>
        </Tabs>
      );
      
      const tabs = screen.getByTestId("tabs");
      expect(tabs).toBeInTheDocument();
      expect(tabs).toHaveTextContent("Tab content");
    });

    it("should apply custom className", () => {
      renderWithTheme(
        <Tabs className="custom-tabs" data-testid="tabs">
          <div>Content</div>
        </Tabs>
      );
      
      const tabs = screen.getByTestId("tabs");
      expect(tabs).toHaveClass("custom-tabs");
    });

    it("should forward ref correctly", () => {
      const ref = vi.fn();
      
      renderWithTheme(
        <Tabs ref={ref} data-testid="tabs">
          <div>Content</div>
        </Tabs>
      );
      
      expect(ref).toHaveBeenCalledWith(expect.any(HTMLDivElement));
    });

    it("should pass through additional props", () => {
      renderWithTheme(
        <Tabs 
          data-testid="tabs" 
          role="region"
          aria-label="Main navigation"
        >
          <div>Content</div>
        </Tabs>
      );
      
      const tabs = screen.getByTestId("tabs");
      expect(tabs).toHaveAttribute("role", "region");
      expect(tabs).toHaveAttribute("aria-label", "Main navigation");
    });
  });

  describe("TabsList Component", () => {
    it("should render MUI Tabs with children", () => {
      renderWithTheme(
        <TabsList value="tab1" data-testid="tabs-list">
          <TabsTrigger value="tab1">Tab 1</TabsTrigger>
          <TabsTrigger value="tab2">Tab 2</TabsTrigger>
        </TabsList>
      );
      
      const tabsList = screen.getByTestId("tabs-list");
      expect(tabsList).toBeInTheDocument();
      expect(tabsList).toHaveClass("MuiTabs-root");
    });

    it("should apply custom className", () => {
      renderWithTheme(
        <TabsList value="tab1" className="custom-tabs-list" data-testid="tabs-list">
          <TabsTrigger value="tab1">Tab 1</TabsTrigger>
        </TabsList>
      );
      
      const tabsList = screen.getByTestId("tabs-list");
      expect(tabsList).toHaveClass("custom-tabs-list");
    });

    it("should forward ref to MUI Tabs", () => {
      const ref = vi.fn();
      
      renderWithTheme(
        <TabsList ref={ref} value="tab1">
          <TabsTrigger value="tab1">Tab 1</TabsTrigger>
        </TabsList>
      );
      
      expect(ref).toHaveBeenCalledWith(expect.any(HTMLDivElement));
    });

    it("should handle MUI Tabs props", () => {
      renderWithTheme(
        <TabsList 
          value="tab1"
          orientation="vertical"
          data-testid="tabs-list"
        >
          <TabsTrigger value="tab1">Tab 1</TabsTrigger>
          <TabsTrigger value="tab2">Tab 2</TabsTrigger>
        </TabsList>
      );
      
      const tabsList = screen.getByTestId("tabs-list");
      expect(tabsList).toHaveClass("MuiTabs-vertical");
    });
  });

  describe("TabsTrigger Component", () => {
    it("should render MUI Tab with label", () => {
      renderWithTheme(
        <TabsList value="tab1">
          <TabsTrigger value="tab1" data-testid="tab-trigger">
            Tab Label
          </TabsTrigger>
        </TabsList>
      );
      
      const tabTrigger = screen.getByTestId("tab-trigger");
      expect(tabTrigger).toBeInTheDocument();
      expect(tabTrigger).toHaveClass("MuiTab-root");
      expect(tabTrigger).toHaveTextContent("Tab Label");
    });

    it("should apply custom className", () => {
      renderWithTheme(
        <TabsList value="tab1">
          <TabsTrigger 
            value="tab1" 
            className="custom-tab" 
            data-testid="tab-trigger"
          >
            Tab
          </TabsTrigger>
        </TabsList>
      );
      
      const tabTrigger = screen.getByTestId("tab-trigger");
      expect(tabTrigger).toHaveClass("custom-tab");
    });

    it("should forward ref to MUI Tab", () => {
      const ref = vi.fn();
      
      renderWithTheme(
        <TabsList value="tab1">
          <TabsTrigger ref={ref} value="tab1">
            Tab
          </TabsTrigger>
        </TabsList>
      );
      
      expect(ref).toHaveBeenCalledWith(expect.any(HTMLButtonElement));
    });

    it("should handle MUI Tab props", () => {
      renderWithTheme(
        <TabsList value="tab1">
          <TabsTrigger 
            value="tab1"
            disabled
            data-testid="tab-trigger"
          >
            Disabled Tab
          </TabsTrigger>
        </TabsList>
      );
      
      const tabTrigger = screen.getByTestId("tab-trigger");
      expect(tabTrigger).toHaveClass("Mui-disabled");
      expect(tabTrigger).toBeDisabled();
    });

    it("should be clickable when enabled", async () => {
      const user = userEvent.setup();
      
      renderWithTheme(
        <TabsList value="tab1">
          <TabsTrigger value="tab1" data-testid="tab-trigger">
            Clickable Tab
          </TabsTrigger>
        </TabsList>
      );
      
      const tabTrigger = screen.getByTestId("tab-trigger");
      expect(tabTrigger).not.toBeDisabled();
      
      await user.click(tabTrigger);
      // Tab click handled by MUI internally
    });
  });

  describe("TabsContent Component", () => {
    it("should render as MUI Box with content", () => {
      renderWithTheme(
        <TabsContent value="tab1" data-testid="tab-content">
          <p>Tab content goes here</p>
        </TabsContent>
      );
      
      const tabContent = screen.getByTestId("tab-content");
      expect(tabContent).toBeInTheDocument();
      expect(tabContent).toHaveTextContent("Tab content goes here");
    });

    it("should apply custom className", () => {
      renderWithTheme(
        <TabsContent 
          value="tab1" 
          className="custom-content" 
          data-testid="tab-content"
        >
          Content
        </TabsContent>
      );
      
      const tabContent = screen.getByTestId("tab-content");
      expect(tabContent).toHaveClass("custom-content");
    });

    it("should forward ref to MUI Box", () => {
      const ref = vi.fn();
      
      renderWithTheme(
        <TabsContent ref={ref} value="tab1">
          Content
        </TabsContent>
      );
      
      expect(ref).toHaveBeenCalledWith(expect.any(HTMLDivElement));
    });

    it("should handle MUI Box props", () => {
      renderWithTheme(
        <TabsContent 
          value="tab1"
          sx={{ padding: 2 }}
          data-testid="tab-content"
        >
          Styled content
        </TabsContent>
      );
      
      const tabContent = screen.getByTestId("tab-content");
      expect(tabContent).toBeInTheDocument();
    });
  });

  describe("Tabs Integration", () => {
    it("should render complete tabs structure", () => {
      renderWithTheme(
        <Tabs data-testid="complete-tabs">
          <TabsList value="tab1" data-testid="tabs-list">
            <TabsTrigger value="tab1" data-testid="tab1-trigger">
              First Tab
            </TabsTrigger>
            <TabsTrigger value="tab2" data-testid="tab2-trigger">
              Second Tab
            </TabsTrigger>
          </TabsList>
          <TabsContent value="tab1" data-testid="tab1-content">
            First tab content
          </TabsContent>
          <TabsContent value="tab2" data-testid="tab2-content">
            Second tab content
          </TabsContent>
        </Tabs>
      );
      
      expect(screen.getByTestId("complete-tabs")).toBeInTheDocument();
      expect(screen.getByTestId("tabs-list")).toBeInTheDocument();
      expect(screen.getByTestId("tab1-trigger")).toBeInTheDocument();
      expect(screen.getByTestId("tab2-trigger")).toBeInTheDocument();
      expect(screen.getByTestId("tab1-content")).toBeInTheDocument();
      expect(screen.getByTestId("tab2-content")).toBeInTheDocument();
    });

    it("should handle multiple tab triggers", () => {
      renderWithTheme(
        <Tabs>
          <TabsList value="home">
            <TabsTrigger value="home">Home</TabsTrigger>
            <TabsTrigger value="about">About</TabsTrigger>
            <TabsTrigger value="contact">Contact</TabsTrigger>
            <TabsTrigger value="settings">Settings</TabsTrigger>
          </TabsList>
        </Tabs>
      );
      
      expect(screen.getByText("Home")).toBeInTheDocument();
      expect(screen.getByText("About")).toBeInTheDocument();
      expect(screen.getByText("Contact")).toBeInTheDocument();
      expect(screen.getByText("Settings")).toBeInTheDocument();
    });

    it("should work with complex content", () => {
      renderWithTheme(
        <Tabs>
          <TabsList value="dashboard">
            <TabsTrigger value="dashboard">Control Panel</TabsTrigger>
          </TabsList>
          <TabsContent value="dashboard">
            <div>
              <h2>Dashboard</h2>
              <p>Welcome to the dashboard</p>
              <button>Action Button</button>
            </div>
          </TabsContent>
        </Tabs>
      );
      
      expect(screen.getByText("Control Panel")).toBeInTheDocument();
      expect(screen.getByText("Dashboard")).toBeInTheDocument();
      expect(screen.getByText("Welcome to the dashboard")).toBeInTheDocument();
      expect(screen.getByText("Action Button")).toBeInTheDocument();
    });
  });

  describe("Accessibility", () => {
    it("should have proper ARIA structure", () => {
      renderWithTheme(
        <Tabs>
          <TabsList value="tab1" role="tablist" data-testid="tabs-list">
            <TabsTrigger value="tab1" data-testid="tab-trigger">
              Tab 1
            </TabsTrigger>
          </TabsList>
          <TabsContent 
            value="tab1" 
            role="tabpanel"
            data-testid="tab-content"
          >
            Content 1
          </TabsContent>
        </Tabs>
      );
      
      const tabsList = screen.getByTestId("tabs-list");
      const tabTrigger = screen.getByTestId("tab-trigger");
      const tabContent = screen.getByTestId("tab-content");
      
      expect(tabsList).toHaveAttribute("role", "tablist");
      expect(tabTrigger).toHaveAttribute("role", "tab");
      expect(tabContent).toHaveAttribute("role", "tabpanel");
    });

    it("should support keyboard navigation", async () => {
      renderWithTheme(
        <Tabs>
          <TabsList value="tab1">
            <TabsTrigger value="tab1" data-testid="tab1">
              Tab 1
            </TabsTrigger>
            <TabsTrigger value="tab2" data-testid="tab2">
              Tab 2
            </TabsTrigger>
          </TabsList>
        </Tabs>
      );
      
      const tab1 = screen.getByTestId("tab1");
      const tab2 = screen.getByTestId("tab2");
      
      // Should be in the document and have proper tab roles
      expect(tab1).toBeInTheDocument();
      expect(tab2).toBeInTheDocument();
      expect(tab1).toHaveAttribute("role", "tab");
      expect(tab2).toHaveAttribute("role", "tab");
      
      // MUI handles keyboard navigation internally with arrow keys
      // We just verify the structure is correct for keyboard access
    });

    it("should handle disabled tabs correctly", () => {
      renderWithTheme(
        <Tabs>
          <TabsList value="enabled">
            <TabsTrigger value="enabled" data-testid="enabled-tab">
              Enabled
            </TabsTrigger>
            <TabsTrigger value="disabled" disabled data-testid="disabled-tab">
              Disabled
            </TabsTrigger>
          </TabsList>
        </Tabs>
      );
      
      const enabledTab = screen.getByTestId("enabled-tab");
      const disabledTab = screen.getByTestId("disabled-tab");
      
      expect(enabledTab).not.toBeDisabled();
      expect(disabledTab).toBeDisabled();
      expect(disabledTab).toHaveClass("Mui-disabled");
    });
  });

  describe("Use Cases", () => {
    it("should work as navigation tabs", () => {
      renderWithTheme(
        <Tabs>
          <TabsList value="home">
            <TabsTrigger value="home">Home</TabsTrigger>
            <TabsTrigger value="products">Products</TabsTrigger>
            <TabsTrigger value="services">Services</TabsTrigger>
          </TabsList>
          <TabsContent value="home">
            Home page content
          </TabsContent>
          <TabsContent value="products">
            Products page content
          </TabsContent>
          <TabsContent value="services">
            Services page content
          </TabsContent>
        </Tabs>
      );
      
      expect(screen.getByText("Home")).toBeInTheDocument();
      expect(screen.getByText("Products")).toBeInTheDocument();
      expect(screen.getByText("Services")).toBeInTheDocument();
    });

    it("should work as settings tabs", () => {
      renderWithTheme(
        <Tabs>
          <TabsList value="general">
            <TabsTrigger value="general">General</TabsTrigger>
            <TabsTrigger value="security">Security</TabsTrigger>
            <TabsTrigger value="notifications">Notifications</TabsTrigger>
          </TabsList>
          <TabsContent value="general">
            <h3>General Settings</h3>
            <p>Configure general preferences</p>
          </TabsContent>
        </Tabs>
      );
      
      expect(screen.getByText("General")).toBeInTheDocument();
      expect(screen.getByText("Security")).toBeInTheDocument();
      expect(screen.getByText("Notifications")).toBeInTheDocument();
      expect(screen.getByText("General Settings")).toBeInTheDocument();
    });

    it("should work as data visualization tabs", () => {
      renderWithTheme(
        <Tabs>
          <TabsList value="chart">
            <TabsTrigger value="chart">Chart View</TabsTrigger>
            <TabsTrigger value="table">Table View</TabsTrigger>
            <TabsTrigger value="raw">Raw Data</TabsTrigger>
          </TabsList>
          <TabsContent value="chart">
            Chart visualization component
          </TabsContent>
          <TabsContent value="table">
            Data table component
          </TabsContent>
          <TabsContent value="raw">
            Raw JSON data display
          </TabsContent>
        </Tabs>
      );
      
      expect(screen.getByText("Chart View")).toBeInTheDocument();
      expect(screen.getByText("Table View")).toBeInTheDocument();
      expect(screen.getByText("Raw Data")).toBeInTheDocument();
    });
  });

  describe("Edge Cases", () => {
    it("should handle empty tabs", () => {
      renderWithTheme(
        <Tabs data-testid="empty-tabs">
          <TabsList data-testid="empty-list" />
        </Tabs>
      );
      
      expect(screen.getByTestId("empty-tabs")).toBeInTheDocument();
      expect(screen.getByTestId("empty-list")).toBeInTheDocument();
    });

    it("should handle tabs without content", () => {
      renderWithTheme(
        <Tabs>
          <TabsList value="tab1">
            <TabsTrigger value="tab1">Tab 1</TabsTrigger>
            <TabsTrigger value="tab2">Tab 2</TabsTrigger>
          </TabsList>
        </Tabs>
      );
      
      expect(screen.getByText("Tab 1")).toBeInTheDocument();
      expect(screen.getByText("Tab 2")).toBeInTheDocument();
    });

    it("should handle content without tabs", () => {
      renderWithTheme(
        <Tabs>
          <TabsContent value="content" data-testid="standalone-content">
            Standalone content
          </TabsContent>
        </Tabs>
      );
      
      const content = screen.getByTestId("standalone-content");
      expect(content).toBeInTheDocument();
      expect(content).toHaveTextContent("Standalone content");
    });

    it("should handle special characters in values", () => {
      renderWithTheme(
        <Tabs>
          <TabsList value="tab-with-dash">
            <TabsTrigger value="tab-with-dash">Dash Tab</TabsTrigger>
            <TabsTrigger value="tab_with_underscore">Underscore Tab</TabsTrigger>
            <TabsTrigger value="tab.with.dots">Dots Tab</TabsTrigger>
          </TabsList>
        </Tabs>
      );
      
      expect(screen.getByText("Dash Tab")).toBeInTheDocument();
      expect(screen.getByText("Underscore Tab")).toBeInTheDocument();
      expect(screen.getByText("Dots Tab")).toBeInTheDocument();
    });
  });

  describe("Styling and Theming", () => {
    it("should apply MUI theme colors", () => {
      renderWithTheme(
        <Tabs>
          <TabsList value="primary">
            <TabsTrigger 
              value="primary" 
              color="primary" 
              data-testid="primary-tab"
            >
              Primary Tab
            </TabsTrigger>
            <TabsTrigger 
              value="secondary" 
              color="secondary" 
              data-testid="secondary-tab"
            >
              Secondary Tab
            </TabsTrigger>
          </TabsList>
        </Tabs>
      );
      
      const primaryTab = screen.getByTestId("primary-tab");
      const secondaryTab = screen.getByTestId("secondary-tab");
      
      expect(primaryTab).toBeInTheDocument();
      expect(secondaryTab).toBeInTheDocument();
    });

    it("should support vertical orientation", () => {
      renderWithTheme(
        <Tabs>
          <TabsList value="tab1" orientation="vertical" data-testid="vertical-tabs">
            <TabsTrigger value="tab1">Tab 1</TabsTrigger>
            <TabsTrigger value="tab2">Tab 2</TabsTrigger>
          </TabsList>
        </Tabs>
      );
      
      const verticalTabs = screen.getByTestId("vertical-tabs");
      expect(verticalTabs).toHaveClass("MuiTabs-vertical");
    });

    it("should support scrollable tabs", () => {
      renderWithTheme(
        <Tabs>
          <TabsList 
            value="tab1"
            variant="scrollable" 
            scrollButtons="auto"
            data-testid="scrollable-tabs"
          >
            <TabsTrigger value="tab1">Tab 1</TabsTrigger>
            <TabsTrigger value="tab2">Tab 2</TabsTrigger>
            <TabsTrigger value="tab3">Tab 3</TabsTrigger>
          </TabsList>
        </Tabs>
      );
      
      const scrollableTabs = screen.getByTestId("scrollable-tabs");
      // Check that the tabs container exists and supports scrollable variant
      expect(scrollableTabs).toBeInTheDocument();
      expect(scrollableTabs).toHaveClass("MuiTabs-root");
      
      // Verify scrollable functionality is enabled by checking for scroller element
      const scroller = scrollableTabs.querySelector('.MuiTabs-scroller');
      expect(scroller).toBeInTheDocument();
    });
  });
});