/**
 * End-to-End Portfolio Tests with Real API
 * These tests use the actual backend API without mocks
 */

import { describe, it, expect, beforeEach } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider, createTheme } from "@mui/material";

// Import real components without API mocking
import PortfolioHoldings from "../../pages/PortfolioHoldings";
import { AuthProvider } from "../../contexts/AuthContext";

// Real test theme
const testTheme = createTheme({
  palette: {
    mode: "light",
    primary: { main: "#1976d2" },
    secondary: { main: "#dc004e" },
  },
});

// Real API wrapper without mocks
const RealApiWrapper = ({ children }) => {
  const testQueryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: 1,
        gcTime: 0,
      },
    },
  });

  return (
    <BrowserRouter>
      <ThemeProvider theme={testTheme}>
        <QueryClientProvider client={testQueryClient}>
          <AuthProvider>{children}</AuthProvider>
        </QueryClientProvider>
      </ThemeProvider>
    </BrowserRouter>
  );
};

const renderWithRealApi = (ui) => {
  return render(ui, {
    wrapper: RealApiWrapper,
  });
};

describe("Portfolio Real API Integration", () => {
  beforeEach(() => {
    // Clear localStorage to ensure clean state
    localStorage.clear();

    // Set up dev auth session with the correct token
    const devSession = {
      user: {
        username: "devuser",
        userId: "dev-devuser",
        email: "argeropolos@gmail.com",
        firstName: "Dev",
        lastName: "User",
      },
      tokens: {
        accessToken: "dev-bypass-token",
        idToken: "dev-bypass-token",
        refreshToken: "dev-bypass-token",
      },
      expiresAt: Date.now() + 3600000, // 1 hour from now
    };

    localStorage.setItem("dev_session", JSON.stringify(devSession));
  });

  it("should load actual portfolio holdings from backend API", async () => {
    renderWithRealApi(<PortfolioHoldings />);

    // Wait for authentication and API calls to complete
    await waitFor(
      async () => {
        // Look for any stock symbol pattern in the rendered content
        const content = document.body.textContent;
        console.log("Page content sample:", content.substring(0, 500));

        // Check for the presence of stock symbols from our test data
        const hasApple = content.includes("AAPL");
        const hasMicrosoft = content.includes("MSFT");
        const hasSPY = content.includes("SPY");

        // At least one of our test symbols should be present
        expect(hasApple || hasMicrosoft || hasSPY).toBe(true);
      },
      { timeout: 20000 }
    );
  }, 30000);

  it("should display portfolio value greater than zero", async () => {
    renderWithRealApi(<PortfolioHoldings />);

    await waitFor(
      async () => {
        const content = document.body.textContent;

        // Look for dollar amounts (our test portfolio has ~$94K)
        const dollarAmounts = content.match(/\$[\d,]+/g);
        console.log("Found dollar amounts:", dollarAmounts);

        // Should find some dollar amounts
        expect(dollarAmounts).toBeTruthy();
        expect(dollarAmounts.length).toBeGreaterThan(0);

        // At least one amount should be substantial (> $1000)
        const hasSubstantialAmount = dollarAmounts?.some((amount) => {
          const numValue = parseInt(amount.replace(/[$,]/g, ""));
          return numValue > 1000;
        });

        expect(hasSubstantialAmount).toBe(true);
      },
      { timeout: 20000 }
    );
  }, 30000);

  it("should not show 'no data available' error messages", async () => {
    renderWithRealApi(<PortfolioHoldings />);

    await waitFor(
      async () => {
        const content = document.body.textContent;

        // Should NOT contain these error messages if API is working
        expect(content).not.toContain("Analytics data not available");
        expect(content).not.toContain("Risk assessment data not available");
        expect(content).not.toContain("Factor analysis data not available");
        expect(content).not.toContain("No data available");

        console.log("✅ No error messages found - API is working");
      },
      { timeout: 15000 }
    );
  }, 25000);

  it("should successfully authenticate with dev-bypass-token", async () => {
    renderWithRealApi(<PortfolioHoldings />);

    // The component should render without authentication errors
    await waitFor(
      async () => {
        const content = document.body.textContent;

        // Should not show authentication errors
        expect(content).not.toContain("Authentication failed");
        expect(content).not.toContain("Access denied");
        expect(content).not.toContain("Login required");

        // Should show the portfolio interface
        expect(content).toContain("Portfolio Holdings");

        console.log("✅ Authentication successful");
      },
      { timeout: 10000 }
    );
  }, 20000);
});
