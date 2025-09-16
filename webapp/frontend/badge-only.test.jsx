import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { Badge } from "./src/components/ui/badge.jsx";
import { ThemeProvider, createTheme } from "@mui/material/styles";

const theme = createTheme();

describe("Badge Component Only", () => {
  it("should render badge text", () => {
    render(
      <ThemeProvider theme={theme}>
        <Badge>Test Badge</Badge>
      </ThemeProvider>
    );
    
    expect(screen.getByText("Test Badge")).toBeInTheDocument();
  });

  it("should render destructive variant", () => {
    render(
      <ThemeProvider theme={theme}>
        <Badge variant="destructive">Error Badge</Badge>
      </ThemeProvider>
    );
    
    const badge = screen.getByText("Error Badge").closest('.MuiChip-root');
    expect(badge).toHaveClass("MuiChip-colorError");
  });
});