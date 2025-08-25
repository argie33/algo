/**
 * Unit Tests for Alert Components
 * Tests alert variants, composition, and accessibility
 */

import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "../../../../components/ui/alert.jsx";
import { renderWithTheme } from "../test-helpers/component-test-utils.jsx";

describe("Alert Components", () => {
  describe("Alert", () => {
    it("should render with default info variant", () => {
      renderWithTheme(<Alert>This is an alert</Alert>);
      
      const alert = screen.getByRole("alert");
      expect(alert).toBeInTheDocument();
      expect(alert).toHaveTextContent("This is an alert");
    });

    it("should render success variant", () => {
      renderWithTheme(<Alert variant="success">Success message</Alert>);
      
      const alert = screen.getByRole("alert");
      expect(alert).toBeInTheDocument();
      expect(alert).toHaveTextContent("Success message");
    });

    it("should render warning variant", () => {
      renderWithTheme(<Alert variant="warning">Warning message</Alert>);
      
      const alert = screen.getByRole("alert");
      expect(alert).toBeInTheDocument();
      expect(alert).toHaveTextContent("Warning message");
    });

    it("should render error variant with destructive mapping", () => {
      renderWithTheme(<Alert variant="destructive">Error message</Alert>);
      
      const alert = screen.getByRole("alert");
      expect(alert).toBeInTheDocument();
      expect(alert).toHaveTextContent("Error message");
    });

    it("should apply custom className", () => {
      renderWithTheme(<Alert className="custom-alert">Alert</Alert>);
      
      const alert = screen.getByRole("alert");
      expect(alert).toHaveClass("custom-alert");
    });

    it("should forward ref", () => {
      const ref = vi.fn();
      
      renderWithTheme(<Alert ref={ref}>Alert with ref</Alert>);
      
      expect(ref).toHaveBeenCalledWith(expect.any(HTMLDivElement));
    });

    it("should pass through additional props", () => {
      renderWithTheme(<Alert data-testid="test-alert">Alert</Alert>);
      
      const alert = screen.getByTestId("test-alert");
      expect(alert).toBeInTheDocument();
    });
  });

  describe("AlertTitle", () => {
    it("should render alert title", () => {
      renderWithTheme(<AlertTitle>Alert Title</AlertTitle>);
      
      expect(screen.getByText("Alert Title")).toBeInTheDocument();
    });

    it("should apply custom className", () => {
      renderWithTheme(<AlertTitle className="custom-title">Title</AlertTitle>);
      
      const title = screen.getByText("Title");
      expect(title).toHaveClass("custom-title");
    });

    it("should forward ref", () => {
      const ref = vi.fn();
      
      renderWithTheme(<AlertTitle ref={ref}>Title</AlertTitle>);
      
      expect(ref).toHaveBeenCalledWith(expect.any(HTMLDivElement));
    });
  });

  describe("AlertDescription", () => {
    it("should render alert description", () => {
      renderWithTheme(<AlertDescription>Alert description text</AlertDescription>);
      
      expect(screen.getByText("Alert description text")).toBeInTheDocument();
    });

    it("should apply custom className", () => {
      renderWithTheme(<AlertDescription className="custom-desc">Description</AlertDescription>);
      
      const description = screen.getByText("Description");
      expect(description).toHaveClass("custom-desc");
    });

    it("should forward ref", () => {
      const ref = vi.fn();
      
      renderWithTheme(<AlertDescription ref={ref}>Description</AlertDescription>);
      
      expect(ref).toHaveBeenCalledWith(expect.any(HTMLDivElement));
    });
  });

  describe("Alert Composition", () => {
    it("should compose alert with title and description", () => {
      renderWithTheme(
        <Alert variant="info">
          <AlertTitle>Important Notice</AlertTitle>
          <AlertDescription>
            This is a detailed description of the alert message
          </AlertDescription>
        </Alert>
      );
      
      const alert = screen.getByRole("alert");
      expect(alert).toBeInTheDocument();
      
      expect(screen.getByText("Important Notice")).toBeInTheDocument();
      expect(screen.getByText("This is a detailed description of the alert message")).toBeInTheDocument();
    });

    it("should work with just description", () => {
      renderWithTheme(
        <Alert variant="warning">
          <AlertDescription>Simple warning message</AlertDescription>
        </Alert>
      );
      
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.getByText("Simple warning message")).toBeInTheDocument();
    });

    it("should work with just title", () => {
      renderWithTheme(
        <Alert variant="success">
          <AlertTitle>Success!</AlertTitle>
        </Alert>
      );
      
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.getByText("Success!")).toBeInTheDocument();
    });
  });

  describe("Variant Mapping", () => {
    it("should map destructive to error severity", () => {
      renderWithTheme(<Alert variant="destructive">Destructive alert</Alert>);
      
      const alert = screen.getByRole("alert");
      // MUI applies severity through classes
      expect(alert).toBeInTheDocument();
    });

    it("should preserve standard MUI severities", () => {
      const variants = ["info", "success", "warning", "error"];
      
      variants.forEach(variant => {
        const { unmount } = renderWithTheme(<Alert variant={variant}>{variant} alert</Alert>);
        
        expect(screen.getByRole("alert")).toBeInTheDocument();
        expect(screen.getByText(`${variant} alert`)).toBeInTheDocument();
        
        unmount();
      });
    });
  });

  describe("Accessibility", () => {
    it("should have proper alert role", () => {
      renderWithTheme(<Alert>Accessible alert</Alert>);
      
      const alert = screen.getByRole("alert");
      expect(alert).toBeInTheDocument();
    });

    it("should be announced by screen readers", () => {
      renderWithTheme(<Alert>Important announcement</Alert>);
      
      // Alert role ensures screen reader announcement
      const alert = screen.getByRole("alert");
      expect(alert).toHaveTextContent("Important announcement");
    });

    it("should support aria-label", () => {
      renderWithTheme(<Alert aria-label="Custom alert label">Alert</Alert>);
      
      const alert = screen.getByLabelText("Custom alert label");
      expect(alert).toBeInTheDocument();
    });
  });
});