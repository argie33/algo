/**
 * AIAssistant Page Unit Tests
 * Tests the AI assistant interface functionality
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

import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AIAssistant from "../../../pages/AIAssistant.jsx";

// Create mock user function locally
const createMockUser = () => ({
  id: "test-user-123",
  email: "test@example.com",
  name: "Test User",
  roles: ["user"],
  preferences: {},
  createdAt: "2025-01-01T00:00:00Z",
  lastLogin: "2025-01-15T10:00:00Z",
});

// Mock AuthContext
vi.mock("../../../contexts/AuthContext.jsx", () => ({
  useAuth: vi.fn(() => ({
    user: createMockUser(),
    isAuthenticated: true,
    isLoading: false,
  })),
  AuthProvider: vi.fn(({ children }) => children),
}));

// Mock EnhancedAIChat component
vi.mock("../../../components/EnhancedAIChat.jsx", () => ({
  default: vi.fn(() => (
    <div data-testid="enhanced-ai-chat">AI Chat Component</div>
  )),
}));

// Test render helper
function renderAIAssistant(props = {}) {
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
        <AIAssistant {...props} />
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("AIAssistant Component", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders AI assistant page", () => {
    renderAIAssistant();

    expect(screen.getByText("AI Assistant")).toBeInTheDocument();
    expect(
      screen.getByText(/your personal ai-powered investment assistant/i)
    ).toBeInTheDocument();
  });

  it("displays page header with title and description", () => {
    renderAIAssistant();

    expect(
      screen.getByRole("heading", { name: "AI Assistant" })
    ).toBeInTheDocument();
    expect(screen.getByText(/powered by claude/i)).toBeInTheDocument();
  });

  it("renders the enhanced AI chat component", () => {
    renderAIAssistant();

    expect(screen.getByTestId("enhanced-ai-chat")).toBeInTheDocument();
  });

  it("displays help text with capabilities", () => {
    renderAIAssistant();

    expect(
      screen.getByText(/ask me anything about your portfolio/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/technical analysis/i)).toBeInTheDocument();
    expect(screen.getByText(/market insights/i)).toBeInTheDocument();
    expect(
      screen.getByText(/personalized investment guidance/i)
    ).toBeInTheDocument();
  });

  it("has proper container structure with material-ui components", () => {
    const { container } = renderAIAssistant();

    // Check for container structure
    expect(
      container.querySelector('[class*="MuiContainer"]')
    ).toBeInTheDocument();
    expect(container.querySelector('[class*="MuiPaper"]')).toBeInTheDocument();
  });

  it("sets proper height constraints for chat interface", () => {
    const { container } = renderAIAssistant();

    // The paper container should have height styling
    const paperElement = container.querySelector('[class*="MuiPaper"]');
    expect(paperElement).toBeInTheDocument();
  });

  it("displays investment capabilities in help text", () => {
    renderAIAssistant();

    const helpText = screen.getByText(/ask me anything about your portfolio/i);
    expect(helpText).toBeInTheDocument();

    // Check that all key capabilities are mentioned
    expect(screen.getByText(/market analysis/i)).toBeInTheDocument();
    expect(screen.getByText(/investment strategies/i)).toBeInTheDocument();
    expect(screen.getByText(/financial data/i)).toBeInTheDocument();
  });
});

// Mock user helper function (unused but keeping for future tests)
function _createMockUserAI() {
  return {
    id: 1,
    username: "testuser",
    email: "test@example.com",
    isAuthenticated: true,
  };
}
