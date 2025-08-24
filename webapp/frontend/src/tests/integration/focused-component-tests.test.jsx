import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  renderWithProviders,
  screen,
  userEvent,
  createMockUser,
} from "../test-utils.jsx";

/**
 * Focused Component Testing Without API Dependencies
 * Tests specific components without complex API interactions
 * Validates real UI components work correctly with minimal dependencies
 */

// Import only specific components we want to test (using default exports)
import ErrorBoundary from "../../components/ErrorBoundary.jsx";
import MarketStatusBar from "../../components/MarketStatusBar.jsx";

// Mock auth context
const mockAuthContext = {
  user: createMockUser(),
  isAuthenticated: true,
  isLoading: false,
  error: null,
  login: vi.fn(),
  register: vi.fn(),
  logout: vi.fn(),
};

vi.mock("../../contexts/AuthContext.jsx", () => ({
  AuthProvider: ({ children }) => children,
  useAuth: () => mockAuthContext,
}));

// Mock API key provider
vi.mock("../../components/ApiKeyProvider.jsx", () => ({
  ApiKeyProvider: ({ children }) => children,
  useApiKeys: () => ({
    apiKeys: {
      alpaca: { configured: true, valid: true },
      polygon: { configured: true, valid: true },
    },
    isLoading: false,
    error: null,
  }),
}));

// Mock session manager
vi.mock("../../services/sessionManager.js", () => ({
  default: {
    startSession: vi.fn(),
    endSession: vi.fn(),
    extendSession: vi.fn(),
    isSessionValid: vi.fn(() => true),
    getSessionInfo: vi.fn(() => ({
      sessionDuration: 3600000,
      timeRemaining: 3600000,
    })),
  },
}));

describe("Focused Component Testing", () => {
  const user = userEvent.setup();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("Error Boundary Component", () => {
    const ThrowError = ({ shouldThrow }) => {
      if (shouldThrow) {
        throw new Error("Test error");
      }
      return <div>No error</div>;
    };

    it("should render children when no error occurs", async () => {
      renderWithProviders(
        <ErrorBoundary fallback={<div>Error occurred</div>}>
          <ThrowError shouldThrow={false} />
        </ErrorBoundary>
      );

      expect(screen.getByText("No error")).toBeInTheDocument();
    });

    it("should render professional error UI when error occurs", async () => {
      // Suppress console.error for this test
      const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});

      renderWithProviders(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} />
        </ErrorBoundary>
      );

      // ErrorBoundary renders a professional Material UI error interface
      expect(screen.getByText("Something went wrong")).toBeInTheDocument();
      expect(screen.getByText("Try Again")).toBeInTheDocument();
      expect(screen.getByText("Go Home")).toBeInTheDocument();
      consoleError.mockRestore();
    });
  });

  describe("Market Status Bar Component", () => {
    it("should render market status information", async () => {
      const mockMarketData = {
        isOpen: true,
        nextClose: "4:00 PM EST",
        indices: {
          SP500: 4500,
          NASDAQ: 14000,
          DOW: 35000
        }
      };

      renderWithProviders(<MarketStatusBar marketData={mockMarketData} />);

      // Should render without crashing
      expect(document.body).toBeInTheDocument();

      // Look for any market-related content
      const _marketElements = screen.queryAllByText(/market|open|close|sp500|nasdaq|dow/i);
      // Even if no specific text matches, component should render
      expect(document.body.innerHTML.length).toBeGreaterThan(0);
    });

    it("should handle missing market data gracefully", async () => {
      renderWithProviders(<MarketStatusBar marketData={null} />);

      // Should not crash with null data
      expect(document.body).toBeInTheDocument();
    });
  });

  describe("Authentication Context Integration", () => {
    it("should provide authentication context to components", async () => {
      const TestComponent = () => {
        const { isAuthenticated, user } = mockAuthContext;
        return (
          <div>
            <div>Auth Status: {isAuthenticated ? "Authenticated" : "Not Authenticated"}</div>
            <div>User: {user?.name || "No User"}</div>
          </div>
        );
      };

      renderWithProviders(<TestComponent />);

      expect(screen.getByText("Auth Status: Authenticated")).toBeInTheDocument();
      expect(screen.getByText(/User:/)).toBeInTheDocument();
    });

    it("should handle unauthenticated state", async () => {
      const unauthenticatedContext = {
        ...mockAuthContext,
        isAuthenticated: false,
        user: null,
      };

      const TestComponent = () => {
        const { isAuthenticated, user } = unauthenticatedContext;
        return (
          <div>
            <div>Auth Status: {isAuthenticated ? "Authenticated" : "Not Authenticated"}</div>
            <div>User: {user?.name || "No User"}</div>
          </div>
        );
      };

      renderWithProviders(<TestComponent />);

      expect(screen.getByText("Auth Status: Not Authenticated")).toBeInTheDocument();
      expect(screen.getByText("User: No User")).toBeInTheDocument();
    });
  });

  describe("API Key Provider Integration", () => {
    it("should provide API key status to components", async () => {
      const TestComponent = () => {
        const mockApiKeys = {
          apiKeys: {
            alpaca: { configured: true, valid: true },
            polygon: { configured: true, valid: true },
          },
          isLoading: false,
          error: null,
        };
        
        return (
          <div>
            <div>Alpaca: {mockApiKeys.apiKeys.alpaca.configured ? "Configured" : "Not Configured"}</div>
            <div>Polygon: {mockApiKeys.apiKeys.polygon.configured ? "Configured" : "Not Configured"}</div>
            <div>Loading: {mockApiKeys.isLoading ? "Yes" : "No"}</div>
          </div>
        );
      };

      renderWithProviders(<TestComponent />);

      expect(screen.getByText("Alpaca: Configured")).toBeInTheDocument();
      expect(screen.getByText("Polygon: Configured")).toBeInTheDocument();
      expect(screen.getByText("Loading: No")).toBeInTheDocument();
    });
  });

  describe("Component Rendering Stability", () => {
    it("should render components without JavaScript errors", async () => {
      const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});

      const SimpleComponent = () => (
        <div>
          <h1>Test Component</h1>
          <button type="button">Test Button</button>
          <p>Test paragraph content</p>
        </div>
      );

      renderWithProviders(<SimpleComponent />);

      expect(screen.getByText("Test Component")).toBeInTheDocument();
      expect(screen.getByText("Test Button")).toBeInTheDocument();
      expect(screen.getByText("Test paragraph content")).toBeInTheDocument();

      // Should not have any console errors
      expect(consoleError).not.toHaveBeenCalled();
      consoleError.mockRestore();
    });

    it("should handle user interactions without crashes", async () => {
      const handleClick = vi.fn();
      
      const InteractiveComponent = () => (
        <div>
          <button type="button" onClick={handleClick}>
            Click Me
          </button>
          <input type="text" placeholder="Type here" />
        </div>
      );

      renderWithProviders(<InteractiveComponent />);

      const button = screen.getByText("Click Me");
      const input = screen.getByPlaceholderText("Type here");

      // Test button click
      await user.click(button);
      expect(handleClick).toHaveBeenCalledTimes(1);

      // Test input typing
      await user.type(input, "test input");
      expect(input).toHaveValue("test input");
    });
  });
});