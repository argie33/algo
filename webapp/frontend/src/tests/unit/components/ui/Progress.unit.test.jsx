/**
 * Unit Tests for Progress Component
 * Tests progress variants, value handling, and indeterminate state
 */

import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import { Progress } from "../../../../components/ui/progress.jsx";
import { renderWithTheme } from "../test-helpers/component-test-utils.jsx";

describe("Progress Component", () => {
  describe("Rendering", () => {
    it("should render with default indeterminate variant", () => {
      renderWithTheme(<Progress data-testid="progress" />);
      
      const progress = screen.getByTestId("progress");
      expect(progress).toBeInTheDocument();
      expect(progress).toHaveClass("MuiLinearProgress-indeterminate");
    });

    it("should render with determinate variant when value is provided", () => {
      renderWithTheme(<Progress value={50} data-testid="progress" />);
      
      const progress = screen.getByTestId("progress");
      expect(progress).toHaveClass("MuiLinearProgress-determinate");
    });

    it("should apply custom className", () => {
      renderWithTheme(<Progress className="custom-progress" data-testid="progress" />);
      
      const progress = screen.getByTestId("progress");
      expect(progress).toHaveClass("custom-progress");
    });
  });

  describe("Value Handling", () => {
    it("should display correct progress value", () => {
      renderWithTheme(<Progress value={75} data-testid="progress" />);
      
      const progress = screen.getByTestId("progress");
      expect(progress).toHaveAttribute("aria-valuenow", "75");
    });

    it("should handle 0% progress", () => {
      renderWithTheme(<Progress value={0} data-testid="progress" />);
      
      const progress = screen.getByTestId("progress");
      expect(progress).toHaveAttribute("aria-valuenow", "0");
      expect(progress).toHaveClass("MuiLinearProgress-determinate");
    });

    it("should handle 100% progress", () => {
      renderWithTheme(<Progress value={100} data-testid="progress" />);
      
      const progress = screen.getByTestId("progress");
      expect(progress).toHaveAttribute("aria-valuenow", "100");
    });

    it("should handle partial progress values", () => {
      const testValues = [25, 33, 67, 90];
      
      testValues.forEach(value => {
        const { unmount } = renderWithTheme(
          <Progress value={value} data-testid={`progress-${value}`} />
        );
        
        const progress = screen.getByTestId(`progress-${value}`);
        expect(progress).toHaveAttribute("aria-valuenow", value.toString());
        
        unmount();
      });
    });
  });

  describe("Variant Behavior", () => {
    it("should be indeterminate when no value provided", () => {
      renderWithTheme(<Progress data-testid="progress" />);
      
      const progress = screen.getByTestId("progress");
      expect(progress).toHaveClass("MuiLinearProgress-indeterminate");
      expect(progress).not.toHaveAttribute("aria-valuenow");
    });

    it("should be determinate when value is provided", () => {
      renderWithTheme(<Progress value={42} data-testid="progress" />);
      
      const progress = screen.getByTestId("progress");
      expect(progress).toHaveClass("MuiLinearProgress-determinate");
      expect(progress).toHaveAttribute("aria-valuenow");
    });

    it("should switch variants based on value presence", () => {
      const { rerender } = renderWithTheme(<Progress data-testid="progress" />);
      
      let progress = screen.getByTestId("progress");
      expect(progress).toHaveClass("MuiLinearProgress-indeterminate");
      
      rerender(<Progress value={60} data-testid="progress" />);
      
      progress = screen.getByTestId("progress");
      expect(progress).toHaveClass("MuiLinearProgress-determinate");
    });
  });

  describe("Props Forwarding", () => {
    it("should forward ref to LinearProgress element", () => {
      const ref = vi.fn();
      
      renderWithTheme(<Progress ref={ref} />);
      
      expect(ref).toHaveBeenCalledWith(expect.any(HTMLSpanElement));
    });

    it("should pass through additional props", () => {
      renderWithTheme(
        <Progress 
          color="secondary" 
          data-testid="progress"
          aria-label="File upload progress"
        />
      );
      
      const progress = screen.getByTestId("progress");
      expect(progress).toHaveAttribute("aria-label", "File upload progress");
    });

    it("should support color variants", () => {
      renderWithTheme(
        <Progress color="secondary" value={50} data-testid="progress" />
      );
      
      const progress = screen.getByTestId("progress");
      expect(progress).toHaveClass("MuiLinearProgress-colorSecondary");
    });
  });

  describe("Accessibility", () => {
    it("should have proper ARIA attributes for determinate progress", () => {
      renderWithTheme(<Progress value={65} data-testid="progress" />);
      
      const progress = screen.getByTestId("progress");
      expect(progress).toHaveAttribute("role", "progressbar");
      expect(progress).toHaveAttribute("aria-valuenow", "65");
      expect(progress).toHaveAttribute("aria-valuemin", "0");
      expect(progress).toHaveAttribute("aria-valuemax", "100");
    });

    it("should have proper ARIA attributes for indeterminate progress", () => {
      renderWithTheme(<Progress data-testid="progress" />);
      
      const progress = screen.getByTestId("progress");
      expect(progress).toHaveAttribute("role", "progressbar");
      expect(progress).not.toHaveAttribute("aria-valuenow");
    });

    it("should support custom aria-label", () => {
      renderWithTheme(
        <Progress 
          value={30} 
          aria-label="Loading data" 
          data-testid="progress" 
        />
      );
      
      const progress = screen.getByTestId("progress");
      expect(progress).toHaveAttribute("aria-label", "Loading data");
    });

    it("should be accessible to screen readers", () => {
      renderWithTheme(
        <Progress 
          value={80} 
          aria-label="Download progress: 80%" 
          data-testid="progress" 
        />
      );
      
      const progress = screen.getByLabelText("Download progress: 80%");
      expect(progress).toBeInTheDocument();
    });
  });

  describe("Use Cases", () => {
    it("should work as loading indicator (indeterminate)", () => {
      renderWithTheme(<Progress data-testid="loading" />);
      
      const loading = screen.getByTestId("loading");
      expect(loading).toBeInTheDocument();
      expect(loading).toHaveClass("MuiLinearProgress-indeterminate");
    });

    it("should work as file upload progress (determinate)", () => {
      renderWithTheme(
        <Progress 
          value={45} 
          aria-label="Upload progress: 45%" 
          data-testid="upload-progress" 
        />
      );
      
      const uploadProgress = screen.getByTestId("upload-progress");
      expect(uploadProgress).toHaveAttribute("aria-valuenow", "45");
    });

    it("should work as form completion progress", () => {
      renderWithTheme(
        <Progress 
          value={33} 
          aria-label="Form completion: 1 of 3 steps" 
          data-testid="form-progress" 
        />
      );
      
      const formProgress = screen.getByTestId("form-progress");
      expect(formProgress).toHaveAttribute("aria-valuenow", "33");
    });

    it("should indicate completed state", () => {
      renderWithTheme(
        <Progress 
          value={100} 
          color="success" 
          aria-label="Task completed" 
          data-testid="completed" 
        />
      );
      
      const completed = screen.getByTestId("completed");
      expect(completed).toHaveAttribute("aria-valuenow", "100");
    });
  });

  describe("Edge Cases", () => {
    it("should handle undefined value gracefully", () => {
      renderWithTheme(<Progress value={undefined} data-testid="progress" />);
      
      const progress = screen.getByTestId("progress");
      expect(progress).toHaveClass("MuiLinearProgress-indeterminate");
    });

    it("should handle null value gracefully", () => {
      renderWithTheme(<Progress value={null} data-testid="progress" />);
      
      const progress = screen.getByTestId("progress");
      // MUI treats null as 0, so it becomes determinate
      expect(progress).toHaveClass("MuiLinearProgress-determinate");
      expect(progress).toHaveAttribute("aria-valuenow", "0");
    });

    it("should handle edge values correctly", () => {
      const { rerender } = renderWithTheme(
        <Progress value={-5} data-testid="progress" />
      );
      
      let progress = screen.getByTestId("progress");
      expect(progress).toHaveAttribute("aria-valuenow", "-5");
      
      rerender(<Progress value={150} data-testid="progress" />);
      
      progress = screen.getByTestId("progress");
      expect(progress).toHaveAttribute("aria-valuenow", "150");
    });
  });
});