/**
 * Unit Tests for Badge Component
 * Tests badge variants, styling, and MUI Chip integration
 */

import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import { Badge } from "../../../../components/ui/badge.jsx";
import { renderWithTheme } from "../test-helpers/component-test-utils.jsx";

describe("Badge Component", () => {
  describe("Rendering", () => {
    it("should render with default props", () => {
      renderWithTheme(<Badge>Default Badge</Badge>);
      
      const badge = screen.getByText("Default Badge");
      expect(badge).toBeInTheDocument();
    });

    it("should render children as label text", () => {
      renderWithTheme(<Badge>Custom Label</Badge>);
      
      expect(screen.getByText("Custom Label")).toBeInTheDocument();
    });

    it("should apply custom className", () => {
      renderWithTheme(<Badge className="custom-badge">Test Badge</Badge>);
      
      const badge = screen.getByText("Test Badge").closest('.MuiChip-root');
      expect(badge).toHaveClass("custom-badge");
    });
  });

  describe("Variants", () => {
    it("should render default variant as outlined", () => {
      renderWithTheme(<Badge variant="default">Default</Badge>);
      
      const badge = screen.getByText("Default").closest('.MuiChip-root');
      expect(badge).toHaveClass("MuiChip-outlined");
    });

    it("should render destructive variant as filled with error color", () => {
      renderWithTheme(<Badge variant="destructive">Error Badge</Badge>);
      
      const badge = screen.getByText("Error Badge").closest('.MuiChip-root');
      expect(badge).toHaveClass("MuiChip-filled");
      expect(badge).toHaveClass("MuiChip-colorError");
    });

    it("should handle custom variant as default", () => {
      renderWithTheme(<Badge variant="custom">Custom Badge</Badge>);
      
      const badge = screen.getByText("Custom Badge").closest('.MuiChip-root');
      expect(badge).toHaveClass("MuiChip-outlined");
    });
  });

  describe("Size", () => {
    it("should render with small size by default", () => {
      renderWithTheme(<Badge>Small Badge</Badge>);
      
      const badge = screen.getByText("Small Badge").closest('.MuiChip-root');
      expect(badge).toHaveClass("MuiChip-sizeSmall");
    });

    it("should support custom size props", () => {
      renderWithTheme(<Badge size="medium">Medium Badge</Badge>);
      
      const badge = screen.getByText("Medium Badge").closest('.MuiChip-root');
      expect(badge).toHaveClass("MuiChip-sizeMedium");
    });
  });

  describe("Props Forwarding", () => {
    it("should forward ref to Chip element", () => {
      const ref = vi.fn();
      
      renderWithTheme(<Badge ref={ref}>Ref Badge</Badge>);
      
      expect(ref).toHaveBeenCalledWith(expect.any(HTMLDivElement));
    });

    it("should pass through additional props", () => {
      renderWithTheme(
        <Badge data-testid="test-badge" title="Badge tooltip">
          Props Badge
        </Badge>
      );
      
      const badge = screen.getByTestId("test-badge");
      expect(badge).toHaveAttribute("title", "Badge tooltip");
    });

    it("should support onClick handlers", () => {
      const handleClick = vi.fn();
      
      renderWithTheme(<Badge onClick={handleClick}>Clickable Badge</Badge>);
      
      const badge = screen.getByText("Clickable Badge");
      badge.click();
      
      expect(handleClick).toHaveBeenCalledTimes(1);
    });
  });

  describe("Color Mapping", () => {
    it("should map destructive variant to error color", () => {
      renderWithTheme(<Badge variant="destructive">Error</Badge>);
      
      const badge = screen.getByText("Error").closest('.MuiChip-root');
      expect(badge).toHaveClass("MuiChip-colorError");
    });

    it("should use default color for other variants", () => {
      renderWithTheme(<Badge variant="default">Default</Badge>);
      
      const badge = screen.getByText("Default").closest('.MuiChip-root');
      expect(badge).toHaveClass("MuiChip-colorDefault");
    });
  });

  describe("Composition", () => {
    it("should work with icon and text", () => {
      const TestIcon = () => <span data-testid="test-icon">★</span>;
      
      renderWithTheme(
        <Badge icon={<TestIcon />}>
          Badge with Icon
        </Badge>
      );
      
      expect(screen.getByText("Badge with Icon")).toBeInTheDocument();
      expect(screen.getByTestId("test-icon")).toBeInTheDocument();
    });

    it("should handle empty content", () => {
      renderWithTheme(<Badge />);
      
      // Badge should render even with empty content
      const badge = document.querySelector('.MuiChip-root');
      expect(badge).toBeInTheDocument();
    });
  });

  describe("Accessibility", () => {
    it("should support aria-label", () => {
      renderWithTheme(<Badge aria-label="Status indicator">Active</Badge>);
      
      const badge = screen.getByLabelText("Status indicator");
      expect(badge).toBeInTheDocument();
    });

    it("should support role attribute", () => {
      renderWithTheme(<Badge role="status">Status Badge</Badge>);
      
      const badge = screen.getByRole("status");
      expect(badge).toBeInTheDocument();
    });

    it("should be focusable when clickable", () => {
      renderWithTheme(<Badge onClick={() => {}}>Focusable Badge</Badge>);
      
      const badge = screen.getByText("Focusable Badge").closest('.MuiChip-root');
      expect(badge).toHaveAttribute("tabindex", "0");
    });
  });

  describe("Use Cases", () => {
    it("should work as status indicator", () => {
      renderWithTheme(<Badge variant="destructive">Offline</Badge>);
      
      const statusBadge = screen.getByText("Offline").closest('.MuiChip-root');
      expect(statusBadge).toBeInTheDocument();
      expect(statusBadge).toHaveClass("MuiChip-colorError");
    });

    it("should work as count indicator", () => {
      renderWithTheme(<Badge>5</Badge>);
      
      expect(screen.getByText("5")).toBeInTheDocument();
    });

    it("should work as tag/label", () => {
      renderWithTheme(<Badge>Technology</Badge>);
      
      expect(screen.getByText("Technology")).toBeInTheDocument();
    });
  });
});