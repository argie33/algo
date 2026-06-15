/**
 * EconomicModeling Page Unit Tests
 *
 * Component facts (from EconomicModeling.jsx):
 * - Simple placeholder: renders <h1>Economic Modeling</h1> and <p>Economic data and analysis</p>
 * - Wrapped in ErrorBoundary
 * - data-testid="economic-modeling" on outer div
 * - No API calls, no loading state, no tabs
 */

import { describe, it, expect, vi } from "vitest";
import {
  renderWithProviders,
  screen,
  waitFor,
} from "../../test-utils.jsx";
import EconomicModeling from "../../../pages/EconomicModeling.jsx";

vi.mock("../../../contexts/AuthContext.jsx", () => ({
  useAuth: vi.fn(() => ({
    user: { id: "test-user-123", email: "test@example.com", name: "Test User" },
    isAuthenticated: true,
    isLoading: false,
  })),
  AuthProvider: vi.fn(({ children }) => children),
}));

vi.mock("../../../services/api.js", () => ({
  default: { get: vi.fn(), post: vi.fn() },
  api: { get: vi.fn(), post: vi.fn() },
  getApiConfig: vi.fn(() => ({ apiUrl: "http://localhost:3001", environment: "test" })),
}));

describe("EconomicModeling Component", () => {
  it("renders economic modeling page", () => {
    renderWithProviders(<EconomicModeling />);
    expect(screen.getByText(/economic modeling/i)).toBeInTheDocument();
  });

  it("renders the main heading", () => {
    renderWithProviders(<EconomicModeling />);
    expect(screen.getByRole("heading", { name: /economic modeling/i })).toBeInTheDocument();
  });

  it("renders descriptive text", () => {
    renderWithProviders(<EconomicModeling />);
    expect(screen.getByText(/economic data and analysis/i)).toBeInTheDocument();
  });

  it("renders the outer container with data-testid", () => {
    renderWithProviders(<EconomicModeling />);
    expect(screen.getByTestId("economic-modeling")).toBeInTheDocument();
  });

  it("renders without crashing", () => {
    renderWithProviders(<EconomicModeling />);
    expect(document.body).toBeTruthy();
  });

  it("does not crash with no API data", async () => {
    renderWithProviders(<EconomicModeling />);
    await waitFor(() => {
      expect(screen.getByText(/economic modeling/i)).toBeInTheDocument();
    });
  });

  it("is wrapped in an error boundary (renders without throw)", () => {
    expect(() => renderWithProviders(<EconomicModeling />)).not.toThrow();
  });

  it("handles empty economic data gracefully (no API calls needed)", async () => {
    renderWithProviders(<EconomicModeling />);
    await waitFor(() => {
      expect(screen.getByText(/economic modeling/i)).toBeInTheDocument();
    });
  });
});
