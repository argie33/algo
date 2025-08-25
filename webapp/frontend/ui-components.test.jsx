import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { ThemeProvider, createTheme } from "@mui/material/styles";

// Import UI components
import { Badge } from "./src/components/ui/badge.jsx";

const theme = createTheme();

const TestWrapper = ({ children }) => (
  <ThemeProvider theme={theme}>
    {children}
  </ThemeProvider>
);

describe("UI Components Suite", () => {
  describe("Badge Component", () => {
    it("renders with text", () => {
      render(
        <TestWrapper>
          <Badge>Success</Badge>
        </TestWrapper>
      );
      expect(screen.getByText("Success")).toBeInTheDocument();
    });

    it("supports variants", () => {
      render(
        <TestWrapper>
          <Badge variant="destructive">Error</Badge>
        </TestWrapper>
      );
      const badge = screen.getByText("Error").closest('.MuiChip-root');
      expect(badge).toHaveClass("MuiChip-colorError");
    });

    it("forwards props", () => {
      render(
        <TestWrapper>
          <Badge data-testid="test-badge">Testable</Badge>
        </TestWrapper>
      );
      expect(screen.getByTestId("test-badge")).toBeInTheDocument();
    });
  });
});