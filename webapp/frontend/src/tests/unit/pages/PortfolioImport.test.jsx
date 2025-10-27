import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, test, expect, beforeEach } from "vitest";
import { AuthContext } from "../../../contexts/AuthContext";
import PortfolioDashboard from "../../../pages/PortfolioDashboard";
import * as api from "../../../services/api";

// Mock the API services
vi.mock("../../../services/api", () => ({
  getPortfolioHoldings: vi.fn(),
  getStockPrices: vi.fn(),
  importPortfolioFromBroker: vi.fn(),
  addHolding: vi.fn(),
  updateHolding: vi.fn(),
  deleteHolding: vi.fn(),
}));

// Mock the auth context
const mockAuthContext = {
  user: { id: "test-user-id", userId: "test-user-id" },
  tokens: { accessToken: "test-token" },
  isAuthenticated: true,
};

// Mock the AuthContext module
vi.mock("../../../contexts/AuthContext", () => ({
  AuthContext: React.createContext(null),
  useAuth: () => mockAuthContext,
  AuthProvider: ({ children }) => children,
}));

// Comprehensive Material-UI mock to avoid conflicts

// Mock all Material-UI components to prevent import issues
vi.mock("@mui/material", () => ({
  Container: ({ children, maxWidth, ...props }) => {
    // Filter out MUI-specific props that should not appear on DOM elements
    const domProps = { ...props };
    delete domProps.maxWidth;
    return <div {...domProps}>{children}</div>;
  },
  Grid: ({ children, container, item, xs, md, lg, spacing, sx, ...props }) => {
    const domProps = { ...props };
    delete domProps.container;
    delete domProps.item;
    delete domProps.xs;
    delete domProps.md;
    delete domProps.lg;
    delete domProps.spacing;
    delete domProps.sx;
    return <div {...domProps}>{children}</div>;
  },
  Paper: ({ children, ...props }) => <div {...props}>{children}</div>,
  Box: ({ children, sx, ...props }) => {
    // Filter out MUI-specific props that should not appear on DOM elements
    const { justifyContent, alignItems, minHeight, maxWidth, ...domProps } = props;
    return <div {...domProps}>{children}</div>;
  },
  Dialog: ({ children, open, "data-testid": testId }) =>
    open ? <div data-testid={testId}>{children}</div> : null,
  DialogTitle: ({ children }) => <h2>{children}</h2>,
  DialogContent: ({ children }) => <div>{children}</div>,
  DialogActions: ({ children }) => <div>{children}</div>,
  Button: ({ children, onClick, disabled, "data-testid": testId, startIcon, endIcon, variant, color, size, sx, ...props }) => {
    const domProps = { ...props };
    delete domProps.startIcon;
    delete domProps.endIcon;
    delete domProps.variant;
    delete domProps.color;
    delete domProps.size;
    delete domProps.sx;
    return (
      <button onClick={onClick} disabled={disabled} data-testid={testId} {...domProps}>
        {startIcon && <span>{startIcon}</span>}
        {children}
        {endIcon && <span>{endIcon}</span>}
      </button>
    );
  },
  IconButton: ({ children, onClick, disabled, "data-testid": testId, ...props }) => (
    <button onClick={onClick} disabled={disabled} data-testid={testId} {...props}>
      {children}
    </button>
  ),
  Select: ({ children, value, onChange, "data-testid": testId, ...props }) => (
    <select data-testid={testId} value={value} onChange={onChange} {...props}>
      {children}
    </select>
  ),
  MenuItem: ({ children, value, ...props }) => (
    <option value={value} {...props}>
      {children}
    </option>
  ),
  FormControl: ({ children, fullWidth, variant, sx, ...props }) => {
    const domProps = { ...props };
    delete domProps.fullWidth;
    delete domProps.variant;
    delete domProps.sx;
    return <div {...domProps}>{children}</div>;
  },
  InputLabel: ({ children, ...props }) => <label {...props}>{children}</label>,
  Typography: ({ children, gutterBottom, variant, component, sx, ...props }) => {
    const domProps = { ...props };
    delete domProps.gutterBottom;
    delete domProps.variant;
    delete domProps.component;
    delete domProps.sx;
    return <div {...domProps}>{children}</div>;
  },
  Alert: ({ children, severity, ...props }) => (
    <div className={`alert alert-${severity}`} {...props}>
      {children}
    </div>
  ),
  Card: ({ children, ...props }) => <div {...props}>{children}</div>,
  CardContent: ({ children, ...props }) => <div {...props}>{children}</div>,
  Divider: ({ ...props }) => <hr {...props} />,
  CircularProgress: ({ ...props }) => <div {...props}>Loading...</div>,
  TableContainer: ({ children, ...props }) => <div {...props}>{children}</div>,
  Table: ({ children, ...props }) => <table {...props}>{children}</table>,
  TableHead: ({ children, ...props }) => <thead {...props}>{children}</thead>,
  TableBody: ({ children, ...props }) => <tbody {...props}>{children}</tbody>,
  TableRow: ({ children, ...props }) => <tr {...props}>{children}</tr>,
  TableCell: ({ children, ...props }) => <td {...props}>{children}</td>,
  TableSortLabel: ({ children, onClick, active, direction, ...props }) => (
    <span onClick={onClick} data-active={active} data-direction={direction} {...props}>
      {children}
    </span>
  ),
  TablePagination: ({ count, page, rowsPerPage, onPageChange, onRowsPerPageChange, rowsPerPageOptions, component, sx, ...props }) => {
    const domProps = { ...props };
    delete domProps.rowsPerPageOptions;
    delete domProps.component;
    delete domProps.sx;
    return (
      <div {...domProps}>
        Pagination: Page {page + 1}, {rowsPerPage} per page, {count} total
      </div>
    );
  },
  CardHeader: ({ title, action, ...props }) => (
    <div {...props}>
      <div>{title}</div>
      {action && <div>{action}</div>}
    </div>
  ),
  TextField: ({ value, onChange, label, placeholder, ...props }) => (
    <div>
      {label && <label>{label}</label>}
      <input value={value} onChange={onChange} placeholder={placeholder} {...props} />
    </div>
  ),
}));

// Mock MUI icons
vi.mock("@mui/icons-material", () => ({
  Add: () => <span>Add</span>,
  Delete: () => <span>Delete</span>,
  Edit: () => <span>Edit</span>,
  FilterList: () => <span>Filter</span>,
  Refresh: () => <span>Refresh</span>,
  CloudDownload: () => <span>Download</span>,
}));

// Mock Recharts
vi.mock("recharts", () => ({
  PieChart: ({ children, width, height, ...props }) => {
    const domProps = { ...props };
    delete domProps.width;
    delete domProps.height;
    return <div data-testid="pie-chart" {...domProps}>{children}</div>;
  },
  Pie: ({ data, dataKey, cx, cy, outerRadius, innerRadius, fill, label, ...props }) => {
    const domProps = { ...props };
    delete domProps.data;
    delete domProps.dataKey;
    delete domProps.cx;
    delete domProps.cy;
    delete domProps.outerRadius;
    delete domProps.innerRadius;
    delete domProps.fill;
    delete domProps.label;
    return <div data-testid="pie" {...domProps}>{data ? JSON.stringify(data) : ''}</div>;
  },
  Cell: ({ fill, ...props }) => {
    const domProps = { ...props };
    delete domProps.fill;
    return <div data-testid="pie-cell" style={{ color: fill }} {...domProps}></div>;
  },
  ResponsiveContainer: ({ children, width, height, ...props }) => {
    const domProps = { ...props };
    delete domProps.width;
    delete domProps.height;
    return <div data-testid="responsive-container" {...domProps}>{children}</div>;
  },
  Tooltip: ({ content, formatter, ...props }) => {
    const domProps = { ...props };
    delete domProps.formatter;
    return <div data-testid="tooltip" {...domProps}>{content}</div>;
  },
}));

const renderPortfolioDashboard = () => {
  return render(
    <AuthContext.Provider value={mockAuthContext}>
      <PortfolioDashboard />
    </AuthContext.Provider>
  );
};

describe("Portfolio Import Functionality", () => {
  beforeEach(() => {
    // Reset mocks
    vi.clearAllMocks();

    // Mock successful API responses
    api.getPortfolioHoldings.mockResolvedValue({
      data: {
        holdings: [],
        summary: { totalValue: 0, totalPnL: 0, totalPnLPercent: 0 },
      },
      success: true,
    });

    api.getStockPrices.mockResolvedValue({
      data: {
        prices: {},
      },
      success: true,
    });
  });

  test("should display import portfolio button", async () => {
    renderPortfolioDashboard();

    await waitFor(() => {
      expect(screen.getByTestId("import-portfolio-button")).toBeInTheDocument();
    });

    const importButton = screen.getByTestId("import-portfolio-button");
    expect(importButton).toHaveTextContent("Import Portfolio");
  });

  test("should open import dialog when import button is clicked", async () => {
    renderPortfolioDashboard();

    await waitFor(() => {
      expect(screen.getByTestId("import-portfolio-button")).toBeInTheDocument();
    });

    const importButton = screen.getByTestId("import-portfolio-button");
    fireEvent.click(importButton);

    await waitFor(() => {
      expect(screen.getByTestId("import-portfolio-dialog")).toBeInTheDocument();
    });

    expect(screen.getByText("Import Portfolio from Broker")).toBeInTheDocument();
    expect(screen.getByText(/Make sure you have configured your API keys/)).toBeInTheDocument();
  });

  test("should display broker selection dropdown in import dialog", async () => {
    renderPortfolioDashboard();

    await waitFor(() => {
      expect(screen.getByTestId("import-portfolio-button")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("import-portfolio-button"));

    await waitFor(() => {
      expect(screen.getByTestId("broker-select")).toBeInTheDocument();
    });

    // With our mock, the select dropdown should show the Alpaca option
    expect(screen.getByText("Alpaca")).toBeInTheDocument();
  });

  test("should call import API when broker is selected and import is confirmed", async () => {
    api.importPortfolioFromBroker.mockResolvedValue({
      data: {
        message: "Portfolio imported successfully",
        holdings: [
          { symbol: "AAPL", shares: 10, avgCost: 150.00 },
          { symbol: "MSFT", shares: 5, avgCost: 300.00 }
        ]
      },
      success: true,
    });

    renderPortfolioDashboard();

    await waitFor(() => {
      expect(screen.getByTestId("import-portfolio-button")).toBeInTheDocument();
    });

    // Open import dialog
    fireEvent.click(screen.getByTestId("import-portfolio-button"));

    await waitFor(() => {
      expect(screen.getByTestId("import-portfolio-dialog")).toBeInTheDocument();
    });

    // Select broker - use native select change event
    const brokerSelect = screen.getByTestId("broker-select");
    fireEvent.change(brokerSelect, { target: { value: "alpaca" } });

    // Click import button
    const importConfirmButton = screen.getByTestId("import-confirm-button");
    fireEvent.click(importConfirmButton);

    await waitFor(() => {
      expect(api.importPortfolioFromBroker).toHaveBeenCalledWith("alpaca");
    });
  });

  test("should show error message when import fails", async () => {
    api.importPortfolioFromBroker.mockRejectedValue(new Error("No API key found for this broker"));

    renderPortfolioDashboard();

    await waitFor(() => {
      expect(screen.getByTestId("import-portfolio-button")).toBeInTheDocument();
    });

    // Open import dialog
    fireEvent.click(screen.getByTestId("import-portfolio-button"));

    await waitFor(() => {
      expect(screen.getByTestId("import-portfolio-dialog")).toBeInTheDocument();
    });

    // Select broker - use native select change event
    const brokerSelect = screen.getByTestId("broker-select");
    fireEvent.change(brokerSelect, { target: { value: "alpaca" } });

    // Click import button
    const importConfirmButton = screen.getByTestId("import-confirm-button");
    fireEvent.click(importConfirmButton);

    await waitFor(() => {
      const errorElements = screen.getAllByText(/No API key found for this broker/);
      expect(errorElements.length).toBeGreaterThanOrEqual(1);
    });
  });

  test("should disable import button when no broker is selected", async () => {
    renderPortfolioDashboard();

    await waitFor(() => {
      expect(screen.getByTestId("import-portfolio-button")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("import-portfolio-button"));

    await waitFor(() => {
      expect(screen.getByTestId("import-confirm-button")).toBeInTheDocument();
    });

    const importConfirmButton = screen.getByTestId("import-confirm-button");
    expect(importConfirmButton).toBeDisabled();
  });

  test("should close dialog after successful import", async () => {
    api.importPortfolioFromBroker.mockResolvedValue({
      data: {
        message: "Portfolio imported successfully",
      },
      success: true,
    });

    renderPortfolioDashboard();

    await waitFor(() => {
      expect(screen.getByTestId("import-portfolio-button")).toBeInTheDocument();
    });

    // Open import dialog
    fireEvent.click(screen.getByTestId("import-portfolio-button"));

    await waitFor(() => {
      expect(screen.getByTestId("import-portfolio-dialog")).toBeInTheDocument();
    });

    // Select broker - use native select change event
    const brokerSelect = screen.getByTestId("broker-select");
    fireEvent.change(brokerSelect, { target: { value: "alpaca" } });

    const importConfirmButton = screen.getByTestId("import-confirm-button");
    fireEvent.click(importConfirmButton);

    await waitFor(() => {
      expect(screen.queryByTestId("import-portfolio-dialog")).not.toBeInTheDocument();
    });
  });
});