import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { AuthProvider, useAuth } from "../../../contexts/AuthContext";

// Force test environment detection
globalThis.__vitest__ = true;
globalThis.vi = vi;

// Mock AWS Amplify Auth
vi.mock("@aws-amplify/auth", () => ({
  fetchAuthSession: vi.fn(),
  signIn: vi.fn(),
  signUp: vi.fn(),
  confirmSignUp: vi.fn(),
  signOut: vi.fn(),
  resetPassword: vi.fn(),
  confirmResetPassword: vi.fn(),
  getCurrentUser: vi.fn(),
}));

// Mock config
vi.mock("../../../config/amplify", () => ({
  isCognitoConfigured: vi.fn(() => false),
}));

// Mock services
vi.mock("../../../services/devAuth", () => ({
  default: {
    signIn: vi.fn(),
    signOut: vi.fn(),
    isEnabled: false,
  },
}));

vi.mock("../../../services/sessionManager", () => ({
  default: {
    initialize: vi.fn(),
    setCallbacks: vi.fn(),
    startSession: vi.fn(),
    endSession: vi.fn(),
    on: vi.fn(),
    off: vi.fn(),
  },
}));

// Mock SessionWarningDialog
vi.mock("../../../components/auth/SessionWarningDialog", () => ({
  default: () => null,
}));

// Simple test component
const TestComponent = () => {
  const auth = useAuth();
  return (
    <div>
      <div data-testid="loading">{auth.isLoading.toString()}</div>
      <div data-testid="authenticated">{auth.isAuthenticated.toString()}</div>
    </div>
  );
};

describe("AuthContext Simple Tests", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("should render without hanging", () => {
    render(
      <AuthProvider>
        <TestComponent />
      </AuthProvider>
    );

    expect(screen.getByTestId("loading")).toBeInTheDocument();
    expect(screen.getByTestId("authenticated")).toBeInTheDocument();
  });

  it("should initialize with not loading state in test mode", () => {
    render(
      <AuthProvider>
        <TestComponent />
      </AuthProvider>
    );

    // In test mode, should immediately set loading to false
    expect(screen.getByTestId("loading")).toHaveTextContent("false");
    expect(screen.getByTestId("authenticated")).toHaveTextContent("false");
  });
});