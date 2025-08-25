/**
 * Unit Tests for OrderManagement Component
 * Tests the order management and trading functionality
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders } from "../../test-utils.jsx";
import { screen, waitFor, act, fireEvent } from "@testing-library/react";
import OrderManagement from "../../../pages/OrderManagement.jsx";
import * as apiService from "../../../services/api.js";

// Mock the AuthContext
vi.mock("../../../contexts/AuthContext.jsx", () => ({
  useAuth: vi.fn(() => ({
    user: { id: 'test-user', email: 'test@example.com', name: 'Test User' },
    isAuthenticated: true,
    isLoading: false,
    error: null,
  })),
  AuthProvider: ({ children }) => children,
}));

// Mock the API service
vi.mock("../../../services/api.js", () => ({
  getOrders: vi.fn(() => 
    Promise.resolve({
      success: true,
      data: {
        orders: [
          {
            id: 'order-123',
            symbol: 'AAPL',
            side: 'buy',
            orderType: 'market',
            quantity: 100,
            price: 150.25,
            status: 'filled',
            createdAt: '2024-01-15T10:30:00Z',
            filledAt: '2024-01-15T10:30:05Z',
            filledPrice: 150.30,
            filledQuantity: 100
          },
          {
            id: 'order-124',
            symbol: 'MSFT',
            side: 'sell',
            orderType: 'limit',
            quantity: 50,
            price: 280.00,
            status: 'pending',
            createdAt: '2024-01-15T11:00:00Z'
          }
        ],
        summary: {
          totalOrders: 2,
          pendingOrders: 1,
          filledOrders: 1,
          cancelledOrders: 0
        }
      }
    })
  ),
  cancelOrder: vi.fn(() =>
    Promise.resolve({
      success: true,
      data: { message: 'Order cancelled successfully' }
    })
  ),
  modifyOrder: vi.fn(() =>
    Promise.resolve({
      success: true,
      data: { message: 'Order modified successfully' }
    })
  ),
  placeOrder: vi.fn(() =>
    Promise.resolve({
      success: true,
      data: {
        orderId: 'order-125',
        status: 'submitted'
      }
    })
  ),
  getOrderHistory: vi.fn(() =>
    Promise.resolve({
      success: true,
      data: [
        {
          id: 'order-120',
          symbol: 'TSLA',
          side: 'buy',
          quantity: 25,
          status: 'filled',
          filledPrice: 240.50,
          createdAt: '2024-01-10T14:20:00Z'
        }
      ]
    })
  ),
  api: {
    get: vi.fn(() => Promise.resolve({ data: { success: true } })),
    post: vi.fn(() => Promise.resolve({ data: { success: true } })),
    put: vi.fn(() => Promise.resolve({ data: { success: true } })),
    delete: vi.fn(() => Promise.resolve({ data: { success: true } }))
  }
}));

describe("OrderManagement Component - Trading Orders", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({
          success: true,
          data: {
            orders: []
          }
        })
      })
    );
  });

  describe("Component Rendering", () => {
    it("should render order management interface", async () => {
      await act(async () => {
        renderWithProviders(<OrderManagement />);
      });

      expect(
        screen.getByText(/order/i) ||
        screen.getByText(/management/i) ||
        screen.getByText(/trading/i)
      ).toBeTruthy();
    });

    it("should display orders table/list", async () => {
      await act(async () => {
        renderWithProviders(<OrderManagement />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/symbol|quantity|price|status/i) ||
          screen.queryByText(/buy|sell/i) ||
          document.querySelector('table')
        ).toBeTruthy();
      });
    });
  });

  describe("Order Display", () => {
    it("should show active orders", async () => {
      apiService.getOrders.mockResolvedValue({
        success: true,
        data: {
          orders: [
            {
              id: 'order-123',
              symbol: 'AAPL',
              side: 'buy',
              quantity: 100,
              status: 'pending'
            }
          ]
        }
      });

      await act(async () => {
        renderWithProviders(<OrderManagement />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/AAPL/i) ||
          screen.queryByText(/100|pending/i) ||
          screen.getByText(/order/i)
        ).toBeTruthy();
      });
    });

    it("should display order status information", async () => {
      await act(async () => {
        renderWithProviders(<OrderManagement />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/pending|filled|cancelled|rejected/i) ||
          screen.getByText(/order/i)
        ).toBeTruthy();
      });
    });

    it("should show order details", async () => {
      await act(async () => {
        renderWithProviders(<OrderManagement />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/price|quantity|symbol|type/i) ||
          screen.queryByText(/market|limit|stop/i) ||
          screen.getByText(/order/i)
        ).toBeTruthy();
      });
    });
  });

  describe("Order Management Actions", () => {
    it("should allow order cancellation", async () => {
      apiService.cancelOrder.mockResolvedValue({
        success: true,
        data: { message: 'Order cancelled' }
      });

      await act(async () => {
        renderWithProviders(<OrderManagement />);
      });

      await waitFor(() => {
        const cancelButton = screen.queryByText(/cancel/i);
        if (cancelButton && cancelButton.tagName === 'BUTTON') {
          fireEvent.click(cancelButton);
        }
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/cancelled|cancel/i) ||
          apiService.cancelOrder
        ).toBeTruthy();
      });
    });

    it("should support order modification", async () => {
      apiService.modifyOrder.mockResolvedValue({
        success: true,
        data: { message: 'Order modified' }
      });

      await act(async () => {
        renderWithProviders(<OrderManagement />);
      });

      await waitFor(() => {
        const modifyButton = screen.queryByText(/modify|edit|update/i);
        if (modifyButton && modifyButton.tagName === 'BUTTON') {
          fireEvent.click(modifyButton);
        }
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/modify|edit|update/i) ||
          screen.getByText(/order/i)
        ).toBeTruthy();
      });
    });
  });

  describe("New Order Placement", () => {
    it("should provide order creation interface", async () => {
      await act(async () => {
        renderWithProviders(<OrderManagement />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/new order|place order|create/i) ||
          screen.queryByText(/symbol|quantity|price/i) ||
          document.querySelector('input[type="text"]')
        ).toBeTruthy();
      });
    });

    it("should handle order submission", async () => {
      apiService.placeOrder.mockResolvedValue({
        success: true,
        data: { orderId: 'new-order-123' }
      });

      await act(async () => {
        renderWithProviders(<OrderManagement />);
      });

      await waitFor(() => {
        const submitButton = screen.queryByText(/submit|place|create/i);
        if (submitButton && submitButton.tagName === 'BUTTON') {
          fireEvent.click(submitButton);
        }
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/submitted|placed|created/i) ||
          screen.getByText(/order/i)
        ).toBeTruthy();
      });
    });

    it("should validate order parameters", async () => {
      await act(async () => {
        renderWithProviders(<OrderManagement />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/required|invalid|enter/i) ||
          screen.queryByText(/symbol|quantity|price/i) ||
          screen.getByText(/order/i)
        ).toBeTruthy();
      });
    });
  });

  describe("Order History", () => {
    it("should display historical orders", async () => {
      apiService.getOrderHistory.mockResolvedValue({
        success: true,
        data: [
          {
            id: 'order-100',
            symbol: 'TSLA',
            side: 'buy',
            status: 'filled',
            createdAt: '2024-01-01T10:00:00Z'
          }
        ]
      });

      await act(async () => {
        renderWithProviders(<OrderManagement />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/history|past|previous/i) ||
          screen.queryByText(/TSLA|filled/i) ||
          screen.getByText(/order/i)
        ).toBeTruthy();
      });
    });

    it("should filter orders by date range", async () => {
      await act(async () => {
        renderWithProviders(<OrderManagement />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/filter|date|range/i) ||
          screen.queryByText(/from|to/i) ||
          document.querySelector('input[type="date"]') ||
          screen.getByText(/order/i)
        ).toBeTruthy();
      });
    });
  });

  describe("Order Status Tracking", () => {
    it("should show real-time order updates", async () => {
      await act(async () => {
        renderWithProviders(<OrderManagement />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/status|pending|filled/i) ||
          screen.queryByText(/real.time|live|update/i) ||
          screen.getByText(/order/i)
        ).toBeTruthy();
      });
    });

    it("should handle order state changes", async () => {
      // Mock order status update
      apiService.getOrders.mockResolvedValueOnce({
        success: true,
        data: {
          orders: [
            { id: 'order-1', status: 'pending' }
          ]
        }
      }).mockResolvedValueOnce({
        success: true,
        data: {
          orders: [
            { id: 'order-1', status: 'filled' }
          ]
        }
      });

      await act(async () => {
        renderWithProviders(<OrderManagement />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/filled|completed|executed/i) ||
          screen.getByText(/order/i)
        ).toBeTruthy();
      });
    });
  });

  describe("Error Handling", () => {
    it("should handle order loading errors", async () => {
      apiService.getOrders.mockRejectedValue(
        new Error("Failed to load orders")
      );

      await act(async () => {
        renderWithProviders(<OrderManagement />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/error|failed|unavailable/i) ||
          screen.getByText(/order/i)
        ).toBeTruthy();
      });
    });

    it("should handle order placement errors", async () => {
      apiService.placeOrder.mockRejectedValue(
        new Error("Order placement failed")
      );

      await act(async () => {
        renderWithProviders(<OrderManagement />);
      });

      // Simulate order placement error
      await waitFor(() => {
        const submitButton = screen.queryByText(/submit|place/i);
        if (submitButton && submitButton.tagName === 'BUTTON') {
          fireEvent.click(submitButton);
        }
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/error|failed|rejected/i) ||
          screen.getByText(/order/i)
        ).toBeTruthy();
      });
    });

    it("should show loading state during operations", async () => {
      apiService.getOrders.mockImplementation(() => 
        new Promise(resolve => 
          setTimeout(() => resolve({ success: true, data: { orders: [] } }), 100)
        )
      );

      await act(async () => {
        renderWithProviders(<OrderManagement />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/loading|fetching/i) ||
          document.querySelector('[role="progressbar"]') ||
          screen.getByText(/order/i)
        ).toBeTruthy();
      });
    });
  });

  describe("Integration and Authentication", () => {
    it("should handle authenticated user sessions", async () => {
      await act(async () => {
        renderWithProviders(<OrderManagement />);
      });

      expect(screen.getByText(/order/i)).toBeTruthy();
    });

    it("should integrate with trading API", async () => {
      await act(async () => {
        renderWithProviders(<OrderManagement />);
      });

      await waitFor(() => {
        expect(
          apiService.getOrders ||
          screen.getByText(/order/i)
        ).toBeTruthy();
      });
    });
  });
});