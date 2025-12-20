/**
 * ComingSoon Page Unit Tests
 * Tests the coming soon placeholder page functionality
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock import.meta.env BEFORE any imports
Object.defineProperty(import.meta, "env", {
  value: {
    VITE_API_URL: "http://localhost:3001",
    MODE: "test",
    DEV: true,
    PROD: false,
    BASE_URL: "/",
  },
  writable: true,
  configurable: true,
});

import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ComingSoon from "../../../pages/ComingSoon.jsx";

// Mock useNavigate
const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// Mock MUI icons
vi.mock("@mui/icons-material", () => ({
  Construction: ({ sx, ...props }) => (
    <div
      data-testid="ConstructionIcon"
      style={{ fontSize: sx?.fontSize || 24 }}
      {...props}
    />
  ),
}));

// Test render helper
function renderComingSoon(props = {}) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ComingSoon {...props} />
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("ComingSoon Component", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders coming soon page with default props", () => {
    renderComingSoon();

    expect(screen.getByText("This Page Coming Soon")).toBeInTheDocument();
    expect(
      screen.getByText("This feature is currently under development.")
    ).toBeInTheDocument();
  });

  it("renders with custom page name", () => {
    renderComingSoon({ pageName: "Portfolio Analytics" });

    expect(
      screen.getByText("Portfolio Analytics Coming Soon")
    ).toBeInTheDocument();
  });

  it("renders with custom description", () => {
    const customDescription =
      "Advanced charting features are being implemented.";
    renderComingSoon({ description: customDescription });

    expect(screen.getByText(customDescription)).toBeInTheDocument();
  });

  it("displays construction icon", () => {
    const { container } = renderComingSoon();

    expect(
      container.querySelector('[data-testid="ConstructionIcon"]')
    ).toBeInTheDocument();
  });

  it("displays encouraging message", () => {
    renderComingSoon();

    expect(
      screen.getByText(/we're working hard to bring you this feature/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/please check back later/i)).toBeInTheDocument();
  });

  it("renders return to dashboard button", () => {
    renderComingSoon();

    expect(
      screen.getByRole("button", { name: /return to dashboard/i })
    ).toBeInTheDocument();
  });

  it("navigates to dashboard when button is clicked", () => {
    renderComingSoon();

    const returnButton = screen.getByRole("button", {
      name: /return to dashboard/i,
    });
    fireEvent.click(returnButton);

    expect(mockNavigate).toHaveBeenCalledWith("/");
  });

  it("has proper material-ui styling", () => {
    const { container } = renderComingSoon();

    expect(
      container.querySelector('[class*="MuiContainer"]')
    ).toBeInTheDocument();
    expect(container.querySelector('[class*="MuiPaper"]')).toBeInTheDocument();
  });

  it("renders all typography elements", () => {
    renderComingSoon();

    // Should have h3 heading
    expect(screen.getByRole("heading", { level: 3 })).toBeInTheDocument();

    // Should have body text
    expect(screen.getByText(/we're working hard/i)).toBeInTheDocument();
  });

  it("handles long page names properly", () => {
    const longPageName = "Very Long Feature Name That Might Wrap";
    renderComingSoon({ pageName: longPageName });

    expect(screen.getByText(`${longPageName} Coming Soon`)).toBeInTheDocument();
  });

  it("handles long descriptions properly", () => {
    const longDescription =
      "This is a very long description that explains in great detail what this feature will do when it is completed and ready for users to enjoy.";
    renderComingSoon({ description: longDescription });

    expect(screen.getByText(longDescription)).toBeInTheDocument();
  });
});
