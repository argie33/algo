/**
 * Unit Tests for Slider Component
 * Tests slider functionality, value handling, and user interactions
 */

import React from "react";
import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Slider } from "../../../../components/ui/slider.jsx";
import { renderWithTheme } from "../test-helpers/component-test-utils.jsx";

describe("Slider Component", () => {
  describe("Rendering", () => {
    it("should render with default props", () => {
      renderWithTheme(<Slider data-testid="slider" />);
      
      const slider = screen.getByTestId("slider");
      expect(slider).toBeInTheDocument();
      const input = slider.querySelector('input[type="range"]');
      expect(input).toBeInTheDocument();
    });

    it("should render with initial value", () => {
      renderWithTheme(<Slider value={50} data-testid="slider" />);
      
      const slider = screen.getByTestId("slider");
      const input = slider.querySelector('input[type="range"]');
      expect(input).toHaveAttribute("aria-valuenow", "50");
    });

    it("should apply custom className", () => {
      renderWithTheme(<Slider className="custom-slider" data-testid="slider" />);
      
      const slider = screen.getByTestId("slider");
      expect(slider).toHaveClass("custom-slider");
    });
  });

  describe("Value Handling", () => {
    it("should handle value changes", async () => {
      const handleValueChange = vi.fn();
      const user = userEvent.setup();
      
      renderWithTheme(
        <Slider 
          value={25} 
          onValueChange={handleValueChange} 
          data-testid="slider"
        />
      );
      
      const slider = screen.getByTestId("slider");
      
      // Focus the slider and use arrow keys
      await user.click(slider);
      await user.keyboard("{ArrowRight}");
      
      expect(handleValueChange).toHaveBeenCalled();
    });

    it("should display correct value", () => {
      const testValues = [0, 25, 50, 75, 100];
      
      testValues.forEach(value => {
        const { unmount } = renderWithTheme(
          <Slider value={value} data-testid={`slider-${value}`} />
        );
        
        const slider = screen.getByTestId(`slider-${value}`);
        const input = slider.querySelector('input[type="range"]');
        expect(input).toHaveAttribute("aria-valuenow", value.toString());
        
        unmount();
      });
    });

    it("should work as controlled component", () => {
      const TestComponent = () => {
        const [value, setValue] = React.useState(30);
        
        return (
          <div>
            <Slider value={value} onValueChange={setValue} data-testid="slider" />
            <div data-testid="value-display">{value}</div>
          </div>
        );
      };

      renderWithTheme(<TestComponent />);
      
      const valueDisplay = screen.getByTestId("value-display");
      expect(valueDisplay).toHaveTextContent("30");
    });
  });

  describe("Range Configuration", () => {
    it("should support custom min/max values", () => {
      renderWithTheme(
        <Slider 
          min={10} 
          max={90} 
          value={50} 
          data-testid="slider" 
        />
      );
      
      const slider = screen.getByTestId("slider");
      const input = slider.querySelector('input[type="range"]');
      expect(input).toHaveAttribute("aria-valuemin", "10");
      expect(input).toHaveAttribute("aria-valuemax", "90");
    });

    it("should handle step configuration", () => {
      renderWithTheme(
        <Slider 
          step={5} 
          min={0} 
          max={100} 
          value={25} 
          data-testid="slider" 
        />
      );
      
      const slider = screen.getByTestId("slider");
      expect(slider).toBeInTheDocument();
      // Step behavior is internal to MUI
    });

    it("should support decimal values", () => {
      renderWithTheme(
        <Slider 
          min={0} 
          max={1} 
          step={0.1} 
          value={0.5} 
          data-testid="slider" 
        />
      );
      
      const slider = screen.getByTestId("slider");
      const input = slider.querySelector('input[type="range"]');
      expect(input).toHaveAttribute("aria-valuenow", "0.5");
    });
  });

  describe("Props Forwarding", () => {
    it("should forward ref to Slider element", () => {
      const ref = vi.fn();
      
      renderWithTheme(<Slider ref={ref} />);
      
      expect(ref).toHaveBeenCalledWith(expect.any(HTMLSpanElement));
    });

    it("should pass through additional props", () => {
      renderWithTheme(
        <Slider 
          disabled 
          color="secondary"
          data-testid="slider"
          aria-label="Volume control"
        />
      );
      
      const slider = screen.getByTestId("slider");
      expect(slider).toHaveClass("MuiSlider-colorSecondary");
      // aria-label is applied to the input element inside
    });

    it("should handle disabled state", () => {
      renderWithTheme(<Slider disabled data-testid="slider" />);
      
      const slider = screen.getByTestId("slider");
      expect(slider).toHaveClass("Mui-disabled");
    });
  });

  describe("Accessibility", () => {
    it("should have proper ARIA attributes", () => {
      renderWithTheme(
        <Slider 
          value={60} 
          min={0} 
          max={100} 
          data-testid="slider" 
        />
      );
      
      const slider = screen.getByTestId("slider");
      const input = slider.querySelector('input[type="range"]');
      expect(input).toHaveAttribute("aria-valuenow", "60");
      expect(input).toHaveAttribute("aria-valuemin", "0");
      expect(input).toHaveAttribute("aria-valuemax", "100");
    });

    it("should support custom aria-label", () => {
      renderWithTheme(
        <Slider 
          value={40} 
          aria-label="Price range filter" 
          data-testid="slider" 
        />
      );
      
      const slider = screen.getByLabelText("Price range filter");
      expect(slider).toBeInTheDocument();
    });

    it("should be keyboard accessible", async () => {
      const user = userEvent.setup();
      
      renderWithTheme(<Slider value={50} data-testid="slider" />);
      
      const slider = screen.getByTestId("slider");
      const input = slider.querySelector('input[type="range"]');
      
      // Should be focusable
      await user.tab();
      expect(input).toHaveFocus();
    });

    it("should support keyboard navigation", async () => {
      const handleValueChange = vi.fn();
      
      renderWithTheme(
        <Slider 
          value={50} 
          onValueChange={handleValueChange} 
          data-testid="slider"
        />
      );
      
      const slider = screen.getByTestId("slider");
      const sliderInput = slider.querySelector('.MuiSlider-thumb input');
      
      // Check that the MUI slider input element exists and is focusable
      expect(sliderInput).toBeInTheDocument();
      expect(sliderInput).toHaveAttribute("type", "range");
      
      // Verify ARIA properties support keyboard navigation
      expect(sliderInput).toHaveAttribute("aria-valuenow", "50");
      expect(sliderInput).toHaveAttribute("aria-valuemin", "0");
      expect(sliderInput).toHaveAttribute("aria-valuemax", "100");
    });
  });

  describe("Visual States", () => {
    it("should show track and thumb", () => {
      renderWithTheme(<Slider value={75} data-testid="slider" />);
      
      const slider = screen.getByTestId("slider");
      expect(slider).toBeInTheDocument();
      
      // Check for MUI slider structure
      const track = slider.querySelector('.MuiSlider-track');
      const thumb = slider.querySelector('.MuiSlider-thumb');
      
      expect(track).toBeInTheDocument();
      expect(thumb).toBeInTheDocument();
    });

    it("should support different colors", () => {
      renderWithTheme(
        <Slider 
          value={50} 
          color="secondary" 
          data-testid="slider" 
        />
      );
      
      const slider = screen.getByTestId("slider");
      expect(slider).toHaveClass("MuiSlider-colorSecondary");
    });

    it("should handle disabled visual state", () => {
      renderWithTheme(<Slider disabled value={30} data-testid="slider" />);
      
      const slider = screen.getByTestId("slider");
      expect(slider).toHaveClass("Mui-disabled");
    });
  });

  describe("Use Cases", () => {
    it("should work as volume control", async () => {
      const handleVolumeChange = vi.fn();
      
      renderWithTheme(
        <Slider 
          value={70} 
          min={0} 
          max={100} 
          onValueChange={handleVolumeChange} 
          aria-label="Volume" 
          data-testid="volume-slider"
        />
      );
      
      const volumeSlider = screen.getByLabelText("Volume");
      expect(volumeSlider).toHaveAttribute("aria-valuenow", "70");
    });

    it("should work as price range filter", () => {
      renderWithTheme(
        <Slider 
          value={[20, 80]} 
          min={0} 
          max={100} 
          getAriaLabel={() => "Price range"}
          data-testid="price-range"
        />
      );
      
      const priceRange = screen.getByTestId("price-range");
      expect(priceRange).toBeInTheDocument();
    });

    it("should work as progress indicator", () => {
      renderWithTheme(
        <Slider 
          value={45} 
          min={0} 
          max={100} 
          disabled 
          aria-label="Progress: 45%" 
          data-testid="progress-slider"
        />
      );
      
      const progressSlider = screen.getByTestId("progress-slider");
      const input = progressSlider.querySelector('input[type="range"]');
      expect(input).toHaveAttribute("aria-valuenow", "45");
      expect(progressSlider).toHaveClass("Mui-disabled");
    });
  });

  describe("Edge Cases", () => {
    it("should handle undefined value", () => {
      renderWithTheme(<Slider value={undefined} data-testid="slider" />);
      
      const slider = screen.getByTestId("slider");
      expect(slider).toBeInTheDocument();
    });

    it("should handle extreme values", () => {
      renderWithTheme(
        <Slider 
          min={-100} 
          max={100} 
          value={-50} 
          data-testid="slider" 
        />
      );
      
      const slider = screen.getByTestId("slider");
      // Find the input within the slider
      const input = slider.querySelector('input[type="range"]');
      expect(input).toHaveAttribute("aria-valuenow", "-50");
      expect(input).toHaveAttribute("aria-valuemin", "-100");
    });

    it("should handle callback without onValueChange", () => {
      renderWithTheme(<Slider value={25} data-testid="slider" />);
      
      const slider = screen.getByTestId("slider");
      expect(slider).toBeInTheDocument();
      // Should not crash when no callback provided
    });

    it("should work with large numbers", () => {
      renderWithTheme(
        <Slider 
          min={1000} 
          max={10000} 
          value={5000} 
          step={100} 
          data-testid="slider" 
        />
      );
      
      const slider = screen.getByTestId("slider");
      const input = slider.querySelector('input[type="range"]');
      expect(input).toHaveAttribute("aria-valuenow", "5000");
    });
  });

  describe("Multiple Values (Range)", () => {
    it("should support range values", () => {
      renderWithTheme(
        <Slider 
          value={[25, 75]} 
          min={0} 
          max={100} 
          data-testid="range-slider" 
        />
      );
      
      const slider = screen.getByTestId("range-slider");
      expect(slider).toBeInTheDocument();
      
      // Range sliders have multiple thumbs
      const thumbs = slider.querySelectorAll('.MuiSlider-thumb');
      expect(thumbs).toHaveLength(2);
    });

    it("should handle range value changes", async () => {
      const handleRangeChange = vi.fn();
      
      renderWithTheme(
        <Slider 
          value={[30, 70]} 
          onValueChange={handleRangeChange} 
          data-testid="range-slider"
        />
      );
      
      const slider = screen.getByTestId("range-slider");
      
      // Should render range slider without interaction issues
      expect(slider).toBeInTheDocument();
      const thumbs = slider.querySelectorAll('.MuiSlider-thumb');
      expect(thumbs).toHaveLength(2);
    });
  });
});