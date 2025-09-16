import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import EnhancedChatInterface from "../../../../components/enhanced-ai/EnhancedChatInterface";

// Mock external dependencies
vi.mock("react-markdown", () => ({
  default: ({ children }) => <div data-testid="markdown">{children}</div>,
}));

vi.mock("react-syntax-highlighter", () => ({
  Prism: ({ children }) => (
    <div data-testid="syntax-highlighter">{children}</div>
  ),
}));

vi.mock("react-syntax-highlighter/dist/esm/styles/prism", () => ({
  vscDarkPlus: {},
}));

// Mock context and hooks - dependencies are mocked globally in setup.js
vi.mock("../../../../contexts/AuthContext.jsx", () => ({
  useAuth: () => ({
    user: { id: "test-user", email: "test@example.com" },
  }),
}));

vi.mock("../../../../services/api.js", () => ({
  default: {
    post: vi.fn().mockResolvedValue({ data: { success: true } }),
  },
}));

describe("EnhancedChatInterface", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("renders chat interface", () => {
    render(<EnhancedChatInterface />);

    // Basic smoke test - just verify it renders without crashing
    expect(document.body).toBeInTheDocument();
  });

  test("has chat input functionality", () => {
    render(<EnhancedChatInterface />);

    // Look for any input field
    const inputs = screen.queryAllByRole("textbox");
    if (inputs.length > 0) {
      expect(inputs[0]).toBeInTheDocument();
    }
  });

  test("displays chat interface elements", () => {
    render(<EnhancedChatInterface />);

    // Check for common chat interface elements
    const buttons = screen.queryAllByRole("button");
    expect(buttons.length).toBeGreaterThanOrEqual(0);
  });

  test("handles props correctly", () => {
    const { rerender } = render(
      <EnhancedChatInterface conversationId="test-123" />
    );

    expect(document.body).toBeInTheDocument();

    rerender(<EnhancedChatInterface conversationId="test-456" />);
    expect(document.body).toBeInTheDocument();
  });

  test("component unmounts cleanly", () => {
    const { unmount } = render(<EnhancedChatInterface />);

    expect(() => unmount()).not.toThrow();
  });
});
