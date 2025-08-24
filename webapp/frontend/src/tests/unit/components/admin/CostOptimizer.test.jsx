/**
 * Unit Tests for CostOptimizer Component
 * Tests admin cost optimization functionality, recommendations, and user interactions
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import CostOptimizer from "../../../../components/admin/CostOptimizer.jsx";

// Create a theme for testing
const theme = createTheme();

// Mock wrapper component
const renderWithTheme = (component) => {
  return render(
    <ThemeProvider theme={theme}>
      {component}
    </ThemeProvider>
  );
};

describe("CostOptimizer Component", () => {
  const mockOnOptimize = vi.fn();
  const mockOnApplyRecommendation = vi.fn();
  
  const defaultProps = {
    onOptimize: mockOnOptimize,
    onApplyRecommendation: mockOnApplyRecommendation,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("Basic Rendering", () => {
    it("should render component title", () => {
      renderWithTheme(<CostOptimizer {...defaultProps} />);
      expect(screen.getByText("Cost Optimization Center")).toBeInTheDocument();
    });

    it("should render current cost overview", () => {
      renderWithTheme(<CostOptimizer {...defaultProps} />);
      expect(screen.getByText("Current Daily Cost")).toBeInTheDocument();
      expect(screen.getByText("$39.45")).toBeInTheDocument();
    });

    it("should render budget controls", () => {
      renderWithTheme(<CostOptimizer {...defaultProps} />);
      expect(screen.getByText("Budget Controls")).toBeInTheDocument();
      expect(screen.getByText("Daily Budget Limit")).toBeInTheDocument();
    });

    it("should render optimization recommendations", () => {
      renderWithTheme(<CostOptimizer {...defaultProps} />);
      expect(screen.getByText("Optimization Recommendations")).toBeInTheDocument();
    });
  });

  describe("Cost Overview Display", () => {
    it("should display cost metrics", () => {
      renderWithTheme(<CostOptimizer {...defaultProps} />);
      
      // Check for cost metrics
      expect(screen.getByText("$39.45")).toBeInTheDocument(); // Current daily cost
      expect(screen.getByText("$30.10")).toBeInTheDocument(); // Optimized cost
      expect(screen.getByText("$9.35")).toBeInTheDocument(); // Potential savings
      expect(screen.getByText("24%")).toBeInTheDocument(); // Cost reduction
    });

    it("should display provider cost analysis", () => {
      renderWithTheme(<CostOptimizer {...defaultProps} />);
      
      // Check for provider names
      expect(screen.getByText("Polygon")).toBeInTheDocument();
      expect(screen.getByText("Alpaca")).toBeInTheDocument();
      expect(screen.getByText("Finnhub")).toBeInTheDocument();
    });

    it("should display provider cost breakdown", () => {
      renderWithTheme(<CostOptimizer {...defaultProps} />);
      
      // Provider costs should be visible in the table
      expect(screen.getByText("$18.75")).toBeInTheDocument();
      expect(screen.getByText("$12.50")).toBeInTheDocument();
      expect(screen.getByText("$8.20")).toBeInTheDocument();
    });
  });

  describe("User Interactions", () => {
    it("should have interactive optimization mode selector", () => {
      renderWithTheme(<CostOptimizer {...defaultProps} />);
      
      // Should have the default balanced mode selected
      const modeSelector = screen.getByDisplayValue("balanced");
      expect(modeSelector).toBeInTheDocument();
    });

    it("should have auto-optimize toggle", () => {
      renderWithTheme(<CostOptimizer {...defaultProps} />);
      
      const autoOptimizeSwitch = screen.getByRole("checkbox");
      expect(autoOptimizeSwitch).toBeInTheDocument();
      expect(autoOptimizeSwitch).not.toBeChecked();
    });

    it("should have budget limit slider", () => {
      renderWithTheme(<CostOptimizer {...defaultProps} />);
      
      const budgetSlider = screen.getByRole("slider");
      expect(budgetSlider).toBeInTheDocument();
    });

    it("should call onOptimize when optimize button clicked", () => {
      renderWithTheme(<CostOptimizer {...defaultProps} />);
      
      const optimizeButton = screen.getByText("Optimize Now");
      fireEvent.click(optimizeButton);
      
      expect(mockOnOptimize).toHaveBeenCalledOnce();
    });
  });

  describe("Optimization Recommendations", () => {
    it("should display recommendation titles", () => {
      renderWithTheme(<CostOptimizer {...defaultProps} />);
      
      // Check for recommendation titles
      expect(screen.getByText("Reduce Polygon Usage During Off-Hours")).toBeInTheDocument();
      expect(screen.getByText("Optimize Symbol Distribution")).toBeInTheDocument();
      expect(screen.getByText("Implement Smart Caching")).toBeInTheDocument();
    });

    it("should display recommendation savings", () => {
      renderWithTheme(<CostOptimizer {...defaultProps} />);
      
      // Check for savings amounts
      expect(screen.getByText("$4.55/day")).toBeInTheDocument();
      expect(screen.getByText("$2.30/day")).toBeInTheDocument();
      expect(screen.getByText("$1.85/day")).toBeInTheDocument();
    });

    it("should have preview and apply buttons", () => {
      renderWithTheme(<CostOptimizer {...defaultProps} />);
      
      // Should have preview buttons
      const previewButtons = screen.getAllByText("Preview");
      expect(previewButtons.length).toBeGreaterThan(0);
      
      // Should have apply buttons
      const applyButtons = screen.getAllByText("Apply");
      expect(applyButtons.length).toBeGreaterThan(0);
    });

    it("should call onApplyRecommendation when apply button clicked", async () => {
      renderWithTheme(<CostOptimizer {...defaultProps} />);
      
      const applyButtons = screen.getAllByText("Apply");
      fireEvent.click(applyButtons[0]);
      
      // The first Apply button corresponds to the second optimization (id: 2) 
      // because the first optimization has autoApply: true and shows "Auto-Apply"
      expect(mockOnApplyRecommendation).toHaveBeenCalledWith(2);
    });
  });

  describe("Preview Dialog", () => {
    it("should open preview dialog when preview button clicked", async () => {
      renderWithTheme(<CostOptimizer {...defaultProps} />);
      
      const previewButtons = screen.getAllByText("Preview");
      fireEvent.click(previewButtons[0]);
      
      await waitFor(() => {
        expect(screen.getByText(/Optimization Preview:/)).toBeInTheDocument();
      });
    });

    it("should close preview dialog when cancel clicked", async () => {
      renderWithTheme(<CostOptimizer {...defaultProps} />);
      
      const previewButtons = screen.getAllByText("Preview");
      fireEvent.click(previewButtons[0]);
      
      await waitFor(() => {
        const cancelButton = screen.getByText("Cancel");
        fireEvent.click(cancelButton);
      });
      
      await waitFor(() => {
        expect(screen.queryByText(/Optimization Preview:/)).not.toBeInTheDocument();
      });
    });
  });

  describe("Monthly Savings Display", () => {
    it("should display potential monthly savings", () => {
      renderWithTheme(<CostOptimizer {...defaultProps} />);
      
      // Should show potential monthly savings in alert
      expect(screen.getByText(/Potential Monthly Savings:/)).toBeInTheDocument();
      // Use regex to find the dollar amount
      expect(screen.getByText(/\$289\.50/)).toBeInTheDocument();
    });

    it("should calculate daily savings correctly", () => {
      renderWithTheme(<CostOptimizer {...defaultProps} />);
      
      // Should show calculated daily savings in the alert text
      expect(screen.getByText(/\$9\.65 per day/)).toBeInTheDocument();
    });
  });

  describe("Accessibility", () => {
    it("should have proper button accessibility", () => {
      renderWithTheme(<CostOptimizer {...defaultProps} />);
      
      const optimizeButton = screen.getByRole("button", { name: /optimize now/i });
      expect(optimizeButton).toBeInTheDocument();
    });

    it("should support keyboard navigation", () => {
      renderWithTheme(<CostOptimizer {...defaultProps} />);
      
      const optimizeButton = screen.getByText("Optimize Now");
      optimizeButton.focus();
      
      expect(document.activeElement).toBe(optimizeButton);
    });

    it("should have proper form controls", () => {
      renderWithTheme(<CostOptimizer {...defaultProps} />);
      
      const slider = screen.getByRole("slider");
      const checkbox = screen.getByRole("checkbox");
      
      expect(slider).toBeInTheDocument();
      expect(checkbox).toBeInTheDocument();
    });
  });

  describe("Edge Cases", () => {
    it("should render without props", () => {
      expect(() => {
        renderWithTheme(<CostOptimizer />);
      }).not.toThrow();
      
      expect(screen.getByText("Cost Optimization Center")).toBeInTheDocument();
    });

    it("should handle missing callback functions", () => {
      expect(() => {
        renderWithTheme(<CostOptimizer />);
      }).not.toThrow();
    });
  });

  describe("Performance", () => {
    it("should render efficiently", () => {
      const startTime = performance.now();
      
      renderWithTheme(<CostOptimizer {...defaultProps} />);
      
      const endTime = performance.now();
      const renderTime = endTime - startTime;
      
      // Should render in reasonable time (less than 1000ms)
      expect(renderTime).toBeLessThan(1000);
      expect(screen.getByText("Cost Optimization Center")).toBeInTheDocument();
    });
  });
});