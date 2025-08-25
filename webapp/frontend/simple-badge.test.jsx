import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { Badge } from "./src/components/ui/badge.jsx";
import { ThemeProvider, createTheme } from "@mui/material/styles";

const theme = createTheme();

describe("Simple Badge Test", () => {
  it("should render badge text", () => {
    render(
      <ThemeProvider theme={theme}>
        <Badge>Test Badge</Badge>
      </ThemeProvider>
    );
    
    const badge = screen.getByText("Test Badge");
    expect(badge).toBeInTheDocument();
  });
});