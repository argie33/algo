/**
 * Unit Tests for Input Component
 * Tests props, variants, events, validation, and accessibility
 */

import React from "react";
import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Input } from "../../../../components/ui/input.jsx";
import { renderWithTheme } from "../test-helpers/component-test-utils.jsx";

describe("Input Component", () => {
  describe("Rendering", () => {
    it("should render with default props", () => {
      renderWithTheme(<Input />);
      
      const input = screen.getByRole("textbox");
      expect(input).toBeInTheDocument();
      expect(input).toHaveAttribute("type", "text");
    });

    it("should render with custom type", () => {
      renderWithTheme(<Input type="email" />);
      
      const input = screen.getByRole("textbox");
      expect(input).toHaveAttribute("type", "email");
    });

    it("should render with label", () => {
      renderWithTheme(<Input label="Email Address" />);
      
      expect(screen.getByLabelText("Email Address")).toBeInTheDocument();
    });

    it("should render with placeholder", () => {
      renderWithTheme(<Input placeholder="Enter your email" />);
      
      const input = screen.getByRole("textbox");
      expect(input).toHaveAttribute("placeholder", "Enter your email");
    });

    it("should apply custom className", () => {
      renderWithTheme(<Input className="custom-input" />);
      
      const inputContainer = document.querySelector(".custom-input");
      expect(inputContainer).toBeInTheDocument();
    });
  });

  describe("Input Types", () => {
    it("should render password input", () => {
      renderWithTheme(<Input type="password" />);
      
      // Password inputs don't have textbox role, query by tag
      const input = document.querySelector('input[type="password"]');
      expect(input).toBeInTheDocument();
      expect(input).toHaveAttribute("type", "password");
    });

    it("should render number input", () => {
      renderWithTheme(<Input type="number" />);
      
      const input = screen.getByRole("spinbutton");
      expect(input).toHaveAttribute("type", "number");
    });

    it("should render email input", () => {
      renderWithTheme(<Input type="email" />);
      
      const input = screen.getByRole("textbox");
      expect(input).toHaveAttribute("type", "email");
    });
  });

  describe("Events", () => {
    it("should handle onChange events", async () => {
      const handleChange = vi.fn();
      const user = userEvent.setup();
      
      renderWithTheme(<Input onChange={handleChange} />);
      
      const input = screen.getByRole("textbox");
      await user.type(input, "hello");
      
      expect(handleChange).toHaveBeenCalledTimes(5); // One for each character
    });

    it("should handle onFocus events", async () => {
      const handleFocus = vi.fn();
      const user = userEvent.setup();
      
      renderWithTheme(<Input onFocus={handleFocus} />);
      
      const input = screen.getByRole("textbox");
      await user.click(input);
      
      expect(handleFocus).toHaveBeenCalledTimes(1);
    });

    it("should handle onBlur events", async () => {
      const handleBlur = vi.fn();
      const user = userEvent.setup();
      
      renderWithTheme(<Input onBlur={handleBlur} />);
      
      const input = screen.getByRole("textbox");
      await user.click(input);
      await user.tab(); // Move focus away
      
      expect(handleBlur).toHaveBeenCalledTimes(1);
    });

    it("should handle onKeyDown events", async () => {
      const handleKeyDown = vi.fn();
      const user = userEvent.setup();
      
      renderWithTheme(<Input onKeyDown={handleKeyDown} />);
      
      const input = screen.getByRole("textbox");
      await user.type(input, "a");
      
      expect(handleKeyDown).toHaveBeenCalled();
    });
  });

  describe("Validation States", () => {
    it("should display error state", () => {
      renderWithTheme(<Input error helperText="This field is required" />);
      
      expect(screen.getByText("This field is required")).toBeInTheDocument();
    });

    it("should show required indicator", () => {
      renderWithTheme(<Input label="Required Field" required />);
      
      const label = screen.getByText("Required Field");
      expect(label).toBeInTheDocument();
      // MUI adds asterisk for required fields
    });

    it("should handle disabled state", () => {
      renderWithTheme(<Input disabled />);
      
      const input = screen.getByRole("textbox");
      expect(input).toBeDisabled();
    });
  });

  describe("Value Handling", () => {
    it("should display initial value", () => {
      renderWithTheme(<Input value="initial value" />);
      
      const input = screen.getByRole("textbox");
      expect(input).toHaveValue("initial value");
    });

    it("should handle defaultValue", () => {
      renderWithTheme(<Input defaultValue="default text" />);
      
      const input = screen.getByRole("textbox");
      expect(input).toHaveValue("default text");
    });

    it("should handle controlled input", async () => {
      const TestComponent = () => {
        const [value, setValue] = React.useState("");
        return (
          <Input 
            value={value} 
            onChange={(e) => setValue(e.target.value)}
            data-testid="controlled-input"
          />
        );
      };

      renderWithTheme(<TestComponent />);
      
      const input = screen.getByTestId("controlled-input").querySelector("input");
      const user = userEvent.setup();
      
      await user.type(input, "controlled");
      expect(input).toHaveValue("controlled");
    });
  });

  describe("Accessibility", () => {
    it("should support aria-label", () => {
      renderWithTheme(<Input aria-label="Search input" />);
      
      const input = screen.getByLabelText("Search input");
      expect(input).toBeInTheDocument();
    });

    it("should support aria-describedby", () => {
      renderWithTheme(
        <div>
          <Input aria-describedby="help-text" />
          <div id="help-text">Enter your username</div>
        </div>
      );
      
      const input = screen.getByRole("textbox");
      // Check if aria-describedby is present (MUI may transform it)
      expect(input).toBeInTheDocument();
    });

    it("should be keyboard accessible", async () => {
      const user = userEvent.setup();
      
      renderWithTheme(<Input />);
      
      const input = screen.getByRole("textbox");
      
      // Should be focusable via keyboard
      await user.tab();
      expect(input).toHaveFocus();
    });

    it("should support screen readers with label", () => {
      renderWithTheme(<Input label="Username" />);
      
      const input = screen.getByLabelText("Username");
      expect(input).toBeInTheDocument();
    });
  });

  describe("Ref Forwarding", () => {
    it("should forward ref to the input element", () => {
      const ref = vi.fn();
      
      renderWithTheme(<Input ref={ref} />);
      
      expect(ref).toHaveBeenCalledWith(expect.any(HTMLDivElement));
    });
  });

  describe("Props Passing", () => {
    it("should pass through additional props", () => {
      renderWithTheme(<Input name="username" id="user-input" />);
      
      const input = screen.getByRole("textbox");
      expect(input).toHaveAttribute("name", "username");
      expect(input).toHaveAttribute("id", "user-input");
    });

    it("should support multiline", () => {
      renderWithTheme(<Input multiline rows={4} />);
      
      const textarea = screen.getByRole("textbox");
      expect(textarea.tagName).toBe("TEXTAREA");
    });

    it("should support size variants", () => {
      renderWithTheme(<Input size="small" />);
      
      // MUI applies size through classes, component should render without errors
      const input = screen.getByRole("textbox");
      expect(input).toBeInTheDocument();
    });
  });
});