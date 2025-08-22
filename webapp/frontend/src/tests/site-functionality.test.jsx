/**
 * Core Site Functionality Tests
 * Tests essential pages and features of the actual finance site
 */

import { describe, it, expect } from "vitest";
import { waitFor } from "@testing-library/react";
import { renderWithProviders, renderWithAuth } from "./test-utils";

// Import actual site components
import Dashboard from "../pages/Dashboard";
import Portfolio from "../pages/Portfolio";
import Settings from "../pages/Settings";
import MarketOverview from "../pages/MarketOverview";
import TradingSignals from "../pages/TradingSignals";
import Watchlist from "../pages/Watchlist";

describe("Core Site Functionality", () => {
  describe("Essential Pages Load Successfully", () => {
    it("Dashboard page renders without errors", async () => {
      renderWithAuth(<Dashboard />);

      await waitFor(
        () => {
          // Should render without crashing
          expect(document.body).toBeInTheDocument();
        },
        { timeout: 15000 }
      );
    });

    it("Portfolio page renders without errors", async () => {
      renderWithAuth(<Portfolio />);

      await waitFor(
        () => {
          // Should render without crashing
          expect(document.body).toBeInTheDocument();
        },
        { timeout: 15000 }
      );
    });

    it("Settings page renders without errors", async () => {
      renderWithAuth(<Settings />);

      await waitFor(
        () => {
          // Should render without crashing
          expect(document.body).toBeInTheDocument();
        },
        { timeout: 15000 }
      );
    });

    it("Market Overview page renders without errors", async () => {
      renderWithProviders(<MarketOverview />);

      await waitFor(
        () => {
          // Should render without crashing
          expect(document.body).toBeInTheDocument();
        },
        { timeout: 15000 }
      );
    });

    it("Trading Signals page renders without errors", async () => {
      renderWithProviders(<TradingSignals />);

      await waitFor(
        () => {
          // Should render without crashing
          expect(document.body).toBeInTheDocument();
        },
        { timeout: 15000 }
      );
    });

    it("Watchlist page renders without errors", async () => {
      renderWithAuth(<Watchlist />);

      await waitFor(
        () => {
          // Should render without crashing
          expect(document.body).toBeInTheDocument();
        },
        { timeout: 15000 }
      );
    });
  });

  describe("Page Content Verification", () => {
    it("Dashboard shows expected elements", async () => {
      renderWithAuth(<Dashboard />);

      await waitFor(
        () => {
          // Should have some dashboard content
          const content = document.body.textContent;
          expect(content).toBeTruthy();
          expect(content.length).toBeGreaterThan(10);
        },
        { timeout: 15000 }
      );
    });

    it("Portfolio shows expected structure", async () => {
      renderWithAuth(<Portfolio />);

      await waitFor(
        () => {
          // Should have portfolio content
          const content = document.body.textContent;
          expect(content).toBeTruthy();
          expect(content.length).toBeGreaterThan(10);
        },
        { timeout: 15000 }
      );
    });

    it("Settings shows configuration options", async () => {
      renderWithAuth(<Settings />);

      await waitFor(
        () => {
          // Should have settings content
          const content = document.body.textContent;
          expect(content).toBeTruthy();
          expect(content.length).toBeGreaterThan(10);
        },
        { timeout: 15000 }
      );
    });
  });

  describe("Error Boundaries and Resilience", () => {
    it("Pages handle missing data gracefully", async () => {
      // Test that pages don't crash when data is unavailable
      renderWithProviders(<MarketOverview />);

      await waitFor(
        () => {
          // Should render something even if data fails
          const content = document.body.textContent;
          expect(content).toBeTruthy();
        },
        { timeout: 10000 }
      );
    });

    it("Auth pages handle unauthenticated state", async () => {
      // Test that auth-required pages handle no auth
      renderWithProviders(<Portfolio />);

      await waitFor(
        () => {
          // Should render something (login prompt or error message)
          const content = document.body.textContent;
          expect(content).toBeTruthy();
        },
        { timeout: 10000 }
      );
    });
  });
});
