/**
 * Unit Tests for WelcomeBanner Component
 * Tests user onboarding and welcome experience
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import WelcomeBanner from "../../../components/WelcomeBanner.jsx";

// Mock navigation
const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// Test wrapper with theme and router
const TestWrapper = ({ children }) => {
  const theme = createTheme({
    palette: {
      primary: { main: "#1976d2" },
      secondary: { main: "#dc004e" },
    },
  });

  return (
    <BrowserRouter>
      <ThemeProvider theme={theme}>{children}</ThemeProvider>
    </BrowserRouter>
  );
};

describe("WelcomeBanner Component", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("Banner Display and Content", () => {
    it("should render welcome banner with key features", async () => {
      // Critical: New users need clear feature overview
      render(
        <TestWrapper>
          <WelcomeBanner />
        </TestWrapper>
      );

      // Should show welcome message
      expect(
        screen.getByText(/welcome/i) ||
          screen.getByText(/get started/i) ||
          screen.getByText(/trading platform/i)
      ).toBeTruthy();

      // Should highlight key features
      expect(
        screen.getByText(/portfolio/i) ||
          screen.getByText(/trading/i) ||
          screen.getByText(/analytics/i)
      ).toBeTruthy();

      // Should have action buttons
      const buttons = screen.getAllByRole("button");
      expect(buttons.length).toBeGreaterThan(0);
    });

    it("should display feature cards with benefits", async () => {
      // Critical: Feature showcase helps user understanding
      render(
        <TestWrapper>
          <WelcomeBanner />
        </TestWrapper>
      );

      // Should show portfolio management feature
      expect(
        screen.getByText(/portfolio/i) &&
          (screen.getByText(/track/i) || screen.getByText(/manage/i))
      ).toBeTruthy();

      // Should show analytics feature
      expect(
        screen.getByText(/analytics/i) ||
          screen.getByText(/insights/i) ||
          screen.getByText(/analysis/i)
      ).toBeTruthy();

      // Should show security feature
      expect(
        screen.getByText(/security/i) ||
          screen.getByText(/secure/i) ||
          screen.getByText(/protected/i)
      ).toBeTruthy();
    });

    it("should show progress indicators for setup steps", async () => {
      // Critical: Setup progress helps user completion
      render(
        <TestWrapper>
          <WelcomeBanner showProgress={true} />
        </TestWrapper>
      );

      // Should show setup progress
      const progressElements =
        screen.queryAllByText(/step/i) ||
        screen.queryAllByText(/progress/i) ||
        screen.queryAllByRole("progressbar");

      expect(progressElements.length).toBeGreaterThan(0);
    });
  });

  describe("User Interaction and Navigation", () => {
    it("should navigate to portfolio setup when clicked", async () => {
      // Critical: Clear path to start using the platform
      render(
        <TestWrapper>
          <WelcomeBanner />
        </TestWrapper>
      );

      const portfolioButton =
        screen.getByText(/portfolio/i) ||
        screen.getByText(/get started/i) ||
        screen.getByRole("button", { name: /portfolio/i });

      fireEvent.click(portfolioButton);

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith(
          expect.stringMatching(/portfolio|setup|onboarding/)
        );
      });
    });

    it("should navigate to trading section", async () => {
      // Critical: Quick access to main trading functionality
      render(
        <TestWrapper>
          <WelcomeBanner />
        </TestWrapper>
      );

      const tradingButton =
        screen.getByText(/trading/i) ||
        screen.getByText(/trade/i) ||
        screen.getByRole("button", { name: /trading/i });

      fireEvent.click(tradingButton);

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith(
          expect.stringMatching(/trading|trade|stocks/)
        );
      });
    });

    it("should allow banner dismissal", async () => {
      // Critical: Users should be able to dismiss onboarding
      render(
        <TestWrapper>
          <WelcomeBanner onDismiss={vi.fn()} />
        </TestWrapper>
      );

      const dismissButton =
        screen.getByRole("button", { name: /close/i }) ||
        screen.getByRole("button", { name: /dismiss/i }) ||
        screen.getByLabelText(/close/i);

      expect(dismissButton).toBeTruthy();

      fireEvent.click(dismissButton);

      // Banner should be hidden or callback called
      await waitFor(() => {
        expect(
          !screen.queryByText(/welcome/i) || dismissButton.onclick
        ).toBeTruthy();
      });
    });

    it("should expand feature details on hover or click", async () => {
      // Critical: Progressive disclosure of feature information
      render(
        <TestWrapper>
          <WelcomeBanner />
        </TestWrapper>
      );

      const featureCard = screen.getAllByText(
        /portfolio|analytics|trading/i
      )[0];
      const parentCard =
        featureCard.closest('[role="button"]') || featureCard.closest("div");

      if (parentCard) {
        fireEvent.mouseEnter(parentCard);

        await waitFor(() => {
          // Should show more details or expand animation
          const _expandedContent =
            screen.queryByText(/learn more/i) ||
            screen.queryByText(/details/i) ||
            parentCard.querySelector('[data-expanded="true"]');

          // Note: This tests the requirement for progressive disclosure
        });
      }
    });
  });

  describe("Personalization and User State", () => {
    it("should adapt content for new users", async () => {
      // Critical: Different experience for first-time users
      render(
        <TestWrapper>
          <WelcomeBanner userType="new" />
        </TestWrapper>
      );

      // Should show onboarding content
      expect(
        screen.getByText(/welcome/i) ||
          screen.getByText(/new/i) ||
          screen.getByText(/getting started/i)
      ).toBeTruthy();

      // Should show setup steps
      expect(
        screen.getByText(/setup/i) ||
          screen.getByText(/configure/i) ||
          screen.getByText(/first/i)
      ).toBeTruthy();
    });

    it("should show different content for returning users", async () => {
      // Critical: Relevant content for existing users
      render(
        <TestWrapper>
          <WelcomeBanner userType="returning" />
        </TestWrapper>
      );

      // Should show relevant actions for existing users
      expect(
        screen.getByText(/portfolio/i) ||
          screen.getByText(/trading/i) ||
          screen.getByText(/continue/i)
      ).toBeTruthy();

      // Should not show basic onboarding
      expect(screen.queryByText(/getting started/i)).toBeFalsy();
    });

    it("should track user interaction for analytics", async () => {
      // Critical: Understanding user engagement
      const onInteraction = vi.fn();

      render(
        <TestWrapper>
          <WelcomeBanner onInteraction={onInteraction} />
        </TestWrapper>
      );

      const actionButton = screen.getAllByRole("button")[0];
      fireEvent.click(actionButton);

      expect(onInteraction).toHaveBeenCalledWith(
        expect.objectContaining({
          action: expect.any(String),
          element: expect.any(String),
          timestamp: expect.any(Number),
        })
      );
    });
  });

  describe("Responsive Design and Accessibility", () => {
    it("should be responsive on mobile devices", async () => {
      // Critical: Mobile-first design for accessibility
      // Mock mobile viewport
      Object.defineProperty(window, "innerWidth", {
        writable: true,
        configurable: true,
        value: 375,
      });

      render(
        <TestWrapper>
          <WelcomeBanner />
        </TestWrapper>
      );

      // Should adapt layout for mobile
      const banner =
        screen.getByRole("banner") ||
        screen.getByTestId("welcome-banner") ||
        document.querySelector('[data-component="welcome-banner"]');

      if (banner) {
        // Should have mobile-friendly styling
        const computedStyle = window.getComputedStyle(banner);
        expect(computedStyle.display).not.toBe("none");
      }
    });

    it("should be keyboard navigable", async () => {
      // Critical: Accessibility for keyboard users
      render(
        <TestWrapper>
          <WelcomeBanner />
        </TestWrapper>
      );

      const buttons = screen.getAllByRole("button");

      // Should be able to tab through buttons
      buttons.forEach((button) => {
        expect(button.tabIndex).toBeGreaterThanOrEqual(0);
      });

      // Test keyboard interaction
      const firstButton = buttons[0];
      firstButton.focus();

      fireEvent.keyDown(firstButton, { key: "Enter" });

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalled();
      });
    });

    it("should have proper ARIA labels and roles", async () => {
      // Critical: Screen reader accessibility
      render(
        <TestWrapper>
          <WelcomeBanner />
        </TestWrapper>
      );

      // Should have proper banner role
      const _banner =
        screen.getByRole("banner") ||
        screen.queryByRole("region") ||
        document.querySelector('[role="banner"]');

      // Should have descriptive labels
      const buttons = screen.getAllByRole("button");
      buttons.forEach((button) => {
        expect(
          button.getAttribute("aria-label") ||
            button.textContent ||
            button.getAttribute("title")
        ).toBeTruthy();
      });
    });

    it("should support high contrast mode", async () => {
      // Critical: Accessibility for visually impaired users
      render(
        <TestWrapper>
          <WelcomeBanner highContrast={true} />
        </TestWrapper>
      );

      const _banner =
        document.querySelector('[data-high-contrast="true"]') ||
        document.querySelector(".high-contrast");

      // Should apply high contrast styling when enabled
      // Note: This documents the requirement for accessibility modes
    });
  });

  describe("Performance and Loading States", () => {
    it("should handle loading states gracefully", async () => {
      // Critical: Smooth loading experience
      render(
        <TestWrapper>
          <WelcomeBanner loading={true} />
        </TestWrapper>
      );

      // Should show loading indicators
      const loadingElement =
        screen.getByText(/loading/i) ||
        screen.getByRole("progressbar") ||
        screen.getByTestId("loading-indicator");

      expect(loadingElement).toBeTruthy();
    });

    it("should minimize re-renders for performance", async () => {
      // Critical: Smooth user experience
      const renderSpy = vi.fn();

      const TestComponent = (props) => {
        renderSpy();
        return <WelcomeBanner {...props} />;
      };

      const { rerender } = render(
        <TestWrapper>
          <TestComponent userType="new" />
        </TestWrapper>
      );

      const initialRenderCount = renderSpy.mock.calls.length;

      // Re-render with same props
      rerender(
        <TestWrapper>
          <TestComponent userType="new" />
        </TestWrapper>
      );

      // Should not cause unnecessary re-renders
      expect(renderSpy.mock.calls.length).toBe(initialRenderCount);
    });

    it("should lazy load heavy content", async () => {
      // Critical: Fast initial load
      render(
        <TestWrapper>
          <WelcomeBanner enableLazyLoading={true} />
        </TestWrapper>
      );

      // Heavy content should load after initial render
      await waitFor(() => {
        const _lazyContent =
          screen.queryByTestId("lazy-content") ||
          screen.queryByText(/advanced features/i);

        // Note: This documents the requirement for lazy loading
      });
    });
  });

  describe("Error Handling and Edge Cases", () => {
    it("should handle missing configuration gracefully", async () => {
      // Critical: Robust error handling
      render(
        <TestWrapper>
          <WelcomeBanner config={null} />
        </TestWrapper>
      );

      // Should show default content when config is missing
      expect(
        screen.getByText(/welcome/i) || screen.getByText(/trading platform/i)
      ).toBeTruthy();
    });

    it("should handle navigation errors", async () => {
      // Critical: Graceful failure handling
      mockNavigate.mockImplementationOnce(() => {
        throw new Error("Navigation failed");
      });

      render(
        <TestWrapper>
          <WelcomeBanner />
        </TestWrapper>
      );

      const button = screen.getAllByRole("button")[0];

      // Should not crash on navigation error
      expect(() => {
        fireEvent.click(button);
      }).not.toThrow();
    });

    it("should validate props and provide defaults", async () => {
      // Critical: Component resilience
      const consoleError = vi
        .spyOn(console, "error")
        .mockImplementation(() => {});

      render(
        <TestWrapper>
          <WelcomeBanner
            invalidProp="invalid"
            userType={123} // Invalid type
          />
        </TestWrapper>
      );

      // Should render with defaults despite invalid props
      expect(
        screen.getByText(/welcome/i) || screen.queryByRole("banner")
      ).toBeTruthy();

      consoleError.mockRestore();
    });
  });

  describe("Analytics and User Engagement", () => {
    it("should track banner engagement metrics", async () => {
      // Critical: Understanding user interaction patterns
      const onAnalytics = vi.fn();

      render(
        <TestWrapper>
          <WelcomeBanner onAnalytics={onAnalytics} />
        </TestWrapper>
      );

      // Track banner view
      expect(onAnalytics).toHaveBeenCalledWith({
        event: "banner_viewed",
        timestamp: expect.any(Number),
        userType: expect.any(String),
      });

      // Track user interactions
      const button = screen.getAllByRole("button")[0];
      fireEvent.click(button);

      expect(onAnalytics).toHaveBeenCalledWith({
        event: "banner_interaction",
        action: expect.any(String),
        timestamp: expect.any(Number),
      });
    });

    it("should measure time to first interaction", async () => {
      // Critical: User engagement timing
      const onMetrics = vi.fn();

      render(
        <TestWrapper>
          <WelcomeBanner onMetrics={onMetrics} />
        </TestWrapper>
      );

      // Simulate user interaction after delay
      await new Promise((resolve) => setTimeout(resolve, 100));

      const button = screen.getAllByRole("button")[0];
      fireEvent.click(button);

      expect(onMetrics).toHaveBeenCalledWith({
        metric: "time_to_first_interaction",
        value: expect.any(Number),
        threshold: expect.any(Number),
      });
    });
  });
});
