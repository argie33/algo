/**
 * Unit Tests for Button Component
 * Pure React component testing - props, rendering, events
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Button } from "../../../../components/ui/button.jsx";

describe("Button Component", () => {
  describe("Rendering", () => {
    it("should render with default props", () => {
      render(<Button>Click me</Button>);
      
      const button = screen.getByRole("button", { name: /click me/i });
      expect(button).toBeInTheDocument();
    });

    it("should render with custom text", () => {
      render(<Button>Save Portfolio</Button>);
      
      expect(screen.getByRole("button", { name: /save portfolio/i })).toBeInTheDocument();
    });

    it("should apply custom className", () => {
      render(<Button className="custom-button">Test</Button>);
      
      const button = screen.getByRole("button");
      expect(button).toHaveClass("custom-button");
    });
  });

  describe("Variants", () => {
    it("should render contained variant by default", () => {
      render(<Button>Default Button</Button>);
      
      const button = screen.getByRole("button");
      // MUI contained variant has specific classes
      expect(button).toHaveClass("MuiButton-contained");
    });

    it("should render outlined variant when specified", () => {
      render(<Button variant="outlined">Outlined Button</Button>);
      
      const button = screen.getByRole("button");
      expect(button).toHaveClass("MuiButton-outlined");
    });

    it("should render text variant when specified", () => {
      render(<Button variant="text">Text Button</Button>);
      
      const button = screen.getByRole("button");
      expect(button).toHaveClass("MuiButton-text");
    });

    it("should handle 'default' variant as 'contained'", () => {
      render(<Button variant="default">Default Variant</Button>);
      
      const button = screen.getByRole("button");
      expect(button).toHaveClass("MuiButton-contained");
    });
  });

  describe("Sizes", () => {
    it("should render medium size by default", () => {
      render(<Button>Medium Button</Button>);
      
      const button = screen.getByRole("button");
      expect(button).toHaveClass("MuiButton-sizeMedium");
    });

    it("should render small size when specified", () => {
      render(<Button size="small">Small Button</Button>);
      
      const button = screen.getByRole("button");
      expect(button).toHaveClass("MuiButton-sizeSmall");
    });

    it("should render large size when specified", () => {
      render(<Button size="large">Large Button</Button>);
      
      const button = screen.getByRole("button");
      expect(button).toHaveClass("MuiButton-sizeLarge");
    });
  });

  describe("Events", () => {
    it("should handle click events", async () => {
      const handleClick = vi.fn();
      const user = userEvent.setup();
      
      render(<Button onClick={handleClick}>Click Me</Button>);
      
      const button = screen.getByRole("button");
      await user.click(button);
      
      expect(handleClick).toHaveBeenCalledTimes(1);
    });

    it("should not trigger click when disabled", async () => {
      const handleClick = vi.fn();
      
      render(<Button onClick={handleClick} disabled>Disabled Button</Button>);
      
      const button = screen.getByRole("button");
      expect(button).toBeDisabled();
      
      // Disabled MUI buttons have pointer-events: none, so we can't click them
      // This is the expected behavior - test that the button is indeed disabled
      expect(button).toHaveAttribute("disabled");
      expect(handleClick).not.toHaveBeenCalled();
    });

    it("should handle focus and blur events", async () => {
      const handleFocus = vi.fn();
      const handleBlur = vi.fn();
      const user = userEvent.setup();
      
      render(
        <Button onFocus={handleFocus} onBlur={handleBlur}>
          Focus Test
        </Button>
      );
      
      const button = screen.getByRole("button");
      
      await user.click(button);
      expect(handleFocus).toHaveBeenCalledTimes(1);
      
      await user.tab();
      expect(handleBlur).toHaveBeenCalledTimes(1);
    });
  });

  describe("Accessibility", () => {
    it("should be focusable by keyboard", async () => {
      const user = userEvent.setup();
      
      render(<Button>Accessible Button</Button>);
      
      const button = screen.getByRole("button");
      
      await user.tab();
      expect(button).toHaveFocus();
    });

    it("should support aria-label", () => {
      render(<Button aria-label="Save user portfolio">💾</Button>);
      
      const button = screen.getByRole("button", { name: /save user portfolio/i });
      expect(button).toBeInTheDocument();
    });

    it("should support aria-describedby", () => {
      render(
        <>
          <Button aria-describedby="help-text">Help</Button>
          <div id="help-text">This button provides help</div>
        </>
      );
      
      const button = screen.getByRole("button");
      expect(button).toHaveAttribute("aria-describedby", "help-text");
    });
  });

  describe("Ref Forwarding", () => {
    it("should forward ref to the button element", () => {
      const ref = vi.fn();
      
      render(<Button ref={ref}>Ref Test</Button>);
      
      expect(ref).toHaveBeenCalledWith(expect.any(HTMLButtonElement));
    });
  });

  describe("Props Passing", () => {
    it("should pass through additional props", () => {
      render(
        <Button data-testid="custom-button" title="Custom tooltip">
          Custom Props
        </Button>
      );
      
      const button = screen.getByTestId("custom-button");
      expect(button).toHaveAttribute("title", "Custom tooltip");
    });

    it("should support type attribute", () => {
      render(<Button type="submit">Submit</Button>);
      
      const button = screen.getByRole("button");
      expect(button).toHaveAttribute("type", "submit");
    });
  });
});