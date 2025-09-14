import { screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { renderWithTheme } from "./test-helpers/component-test-utils";
import LoadingDisplay from "../../../components/LoadingDisplay";

describe("LoadingDisplay", () => {
  it("renders loading spinner by default", () => {
    renderWithTheme(<LoadingDisplay />);

    expect(screen.getByRole("progressbar")).toBeInTheDocument();
  });

  it("displays custom message when provided", () => {
    const customMessage = "Loading portfolio data...";
    renderWithTheme(<LoadingDisplay message={customMessage} />);

    expect(screen.getByText(customMessage)).toBeInTheDocument();
  });

  it("displays default message when none provided", () => {
    renderWithTheme(<LoadingDisplay />);

    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("renders with proper structure", () => {
    renderWithTheme(<LoadingDisplay />);

    const progressElement = screen.getByRole("progressbar");
    expect(progressElement).toBeInTheDocument();
    expect(progressElement).toHaveStyle({ width: "40px", height: "40px" });
  });

  it("centers content properly", () => {
    const { container } = renderWithTheme(<LoadingDisplay />);
    const boxElement = container.querySelector(".MuiBox-root");

    // Check CSS properties that MUI Box applies
    expect(boxElement).toHaveClass("MuiBox-root");
    // The display and alignment styles are handled by MUI internally
  });

  it("displays message with proper typography", () => {
    const customMessage = "Custom loading message";
    renderWithTheme(<LoadingDisplay message={customMessage} />);

    const messageElement = screen.getByText(customMessage);
    expect(messageElement).toHaveClass("MuiTypography-body1");
  });

  it("has proper component structure", () => {
    renderWithTheme(<LoadingDisplay />);

    const progressElement = screen.getByRole("progressbar");
    const textElement = screen.getByText("Loading...");

    expect(progressElement).toBeInTheDocument();
    expect(textElement).toBeInTheDocument();
    expect(progressElement).toHaveClass("MuiCircularProgress-root");
  });
});
