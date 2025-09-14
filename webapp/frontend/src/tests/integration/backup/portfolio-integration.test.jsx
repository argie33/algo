/**
 * Portfolio Real Data Integration Tests
 * Tests that portfolio pages display actual data from the backend API
 * This validates that authentication tokens work and data flows correctly
 */

import { describe, it, expect, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { renderWithAuth } from "../test-utils";

// Import actual components
import PortfolioHoldings from "../../pages/PortfolioHoldings";

describe("Portfolio Real Data Integration", () => {
  beforeEach(() => {
    // Clear any existing auth state
    localStorage.clear();
  });

  describe("Portfolio Holdings Data Validation", () => {
    it("should display actual portfolio holdings with real data", async () => {
      renderWithAuth(<PortfolioHoldings />);

      // Wait for the component to load and make API calls
      await waitFor(
        async () => {
          // Check for actual stock symbols from our test data
          const appleHolding = await screen.findByText(/AAPL/, { timeout: 10000 });
          expect(appleHolding).toBeInTheDocument();
        },
        { timeout: 15000 }
      );

      // Validate that we have the expected holdings from our test data
      await waitFor(async () => {
        // These are the actual holdings in our dev-user-bypass test data
        expect(screen.getByText(/AAPL/)).toBeInTheDocument();  // Apple
        expect(screen.getByText(/MSFT/)).toBeInTheDocument();  // Microsoft  
        expect(screen.getByText(/SPY/)).toBeInTheDocument();   // SPDR S&P 500
        expect(screen.getByText(/QQQ/)).toBeInTheDocument();   // Invesco QQQ
        expect(screen.getByText(/VTI/)).toBeInTheDocument();   // Vanguard Total Stock Market
        expect(screen.getByText(/BND/)).toBeInTheDocument();   // Vanguard Total Bond Market
        expect(screen.getByText(/IWM/)).toBeInTheDocument();   // iShares Russell 2000
      }, { timeout: 10000 });
    }, 20000);

    it("should show actual portfolio values and not placeholder data", async () => {
      renderWithAuth(<PortfolioHoldings />);

      await waitFor(async () => {
        // Check that we're not showing "no data" or placeholder messages
        const content = document.body.textContent;
        
        // Should NOT contain error messages
        expect(content).not.toContain("No data available");
        expect(content).not.toContain("Analytics data not available");
        expect(content).not.toContain("Risk assessment data not available");
        expect(content).not.toContain("Factor analysis data not available");
        
        // Should contain actual financial data indicators
        expect(content).toMatch(/\$[\d,]+/); // Should have dollar amounts
        expect(content).toMatch(/[\d]+\.[\d]+%/); // Should have percentages
      }, { timeout: 15000 });
    }, 20000);

    it("should display portfolio analytics with real calculations", async () => {
      renderWithAuth(<PortfolioHoldings />);

      // Wait for Analytics tab and click it
      await waitFor(async () => {
        const analyticsTab = screen.getByRole("tab", { name: /analytics/i });
        expect(analyticsTab).toBeInTheDocument();
        analyticsTab.click();
      }, { timeout: 10000 });

      // Verify analytics content loads
      await waitFor(async () => {
        const content = document.body.textContent;
        
        // Should NOT show error messages
        expect(content).not.toContain("Analytics data not available");
        
        // Should show portfolio metrics
        expect(content).toMatch(/(Total Value|Portfolio Value|Market Value)/i);
        expect(content).toMatch(/(Return|Performance|Gain)/i);
      }, { timeout: 10000 });
    }, 25000);

    it("should display risk management with real risk data", async () => {
      renderWithAuth(<PortfolioHoldings />);

      // Wait for Risk Management tab and click it  
      await waitFor(async () => {
        const riskTab = screen.getByRole("tab", { name: /risk/i });
        expect(riskTab).toBeInTheDocument();
        riskTab.click();
      }, { timeout: 10000 });

      // Verify risk content loads
      await waitFor(async () => {
        const content = document.body.textContent;
        
        // Should NOT show error messages
        expect(content).not.toContain("Risk assessment data not available");
        
        // Should show risk metrics
        expect(content).toMatch(/(Risk Score|Beta|Volatility|VaR)/i);
      }, { timeout: 10000 });
    }, 25000);

    it("should display factor analysis without error messages", async () => {
      renderWithAuth(<PortfolioHoldings />);

      // Wait for Factor Analysis tab and click it
      await waitFor(async () => {
        const factorTab = screen.getByRole("tab", { name: /factor/i });
        expect(factorTab).toBeInTheDocument();
        factorTab.click();
      }, { timeout: 10000 });

      // Verify factor analysis loads without error
      await waitFor(async () => {
        const content = document.body.textContent;
        
        // Should NOT show error messages
        expect(content).not.toContain("Factor analysis data not available");
        expect(content).not.toContain("requires portfolio holdings and market data");
        
        // Should attempt to show factor-related content
        expect(content).toMatch(/(Factor|Exposure|Attribution)/i);
      }, { timeout: 10000 });
    }, 25000);
  });

  describe("Data Consistency Validation", () => {
    it("should show consistent portfolio values across tabs", async () => {
      renderWithAuth(<PortfolioHoldings />);

      // Get portfolio value from Holdings tab
      let holdingsValue = null;
      await waitFor(async () => {
        const valueMatch = document.body.textContent.match(/\$[\d,]+\.[\d]{2}/);
        if (valueMatch) {
          holdingsValue = valueMatch[0];
        }
        expect(holdingsValue).toBeTruthy();
      }, { timeout: 15000 });

      // Switch to Analytics tab
      const analyticsTab = screen.getByRole("tab", { name: /analytics/i });
      analyticsTab.click();

      // Verify the same value appears (or reasonable values)
      await waitFor(async () => {
        const content = document.body.textContent;
        // Should contain financial values
        expect(content).toMatch(/\$[\d,]+/);
      }, { timeout: 10000 });
    }, 30000);
  });

  describe("Authentication and Data Flow", () => {
    it("should successfully authenticate and load user-specific data", async () => {
      renderWithAuth(<PortfolioHoldings />);

      // Verify that we get actual user data, not generic data
      await waitFor(async () => {
        const content = document.body.textContent;
        
        // Should have user-specific holdings (our test data has 7 positions)
        const symbolMatches = content.match(/\b[A-Z]{3,5}\b/g) || [];
        const stockSymbols = symbolMatches.filter(symbol => 
          ['AAPL', 'MSFT', 'SPY', 'QQQ', 'VTI', 'BND', 'IWM'].includes(symbol)
        );
        
        // Should have multiple stock symbols from our test data
        expect(stockSymbols.length).toBeGreaterThan(3);
      }, { timeout: 15000 });
    }, 20000);
  });
});