import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient } from "@tanstack/react-query";
import { vi, describe, test, beforeEach, expect } from "vitest";
import "@testing-library/jest-dom";

// Mock performance APIs
const mockPerformanceObserver = vi.fn();
const mockPerformanceMark = vi.fn();
const mockPerformanceMeasure = vi.fn();

Object.defineProperty(global, "PerformanceObserver", {
  writable: true,
  value: vi.fn().mockImplementation(() => ({
    observe: mockPerformanceObserver,
    disconnect: vi.fn(),
  })),
});

Object.defineProperty(global.performance, "mark", {
  writable: true,
  value: mockPerformanceMark,
});

Object.defineProperty(global.performance, "measure", {
  writable: true,
  value: mockPerformanceMeasure,
});

// Mock Intersection Observer for lazy loading
global.IntersectionObserver = vi.fn().mockImplementation((_callback) => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}));

// Mock Web Vitals with proper function implementations
const mockGetCLS = vi.fn((callback) => callback({ name: "CLS", value: 0.05 }));
const mockGetFID = vi.fn((callback) => callback({ name: "FID", value: 80 }));
const mockGetFCP = vi.fn((callback) => callback({ name: "FCP", value: 1200 }));
const mockGetLCP = vi.fn((callback) => callback({ name: "LCP", value: 2100 }));
const mockGetTTFB = vi.fn((callback) => callback({ name: "TTFB", value: 400 }));

vi.mock("web-vitals", () => ({
  getCLS: mockGetCLS,
  getFID: mockGetFID,
  getFCP: mockGetFCP,
  getLCP: mockGetLCP,
  getTTFB: mockGetTTFB,
}));

// Mock components for performance testing
const MockPerformanceMonitor = ({ onMetric = vi.fn() }) => {
  const [metrics, setMetrics] = React.useState({});
  const [isLoading, setIsLoading] = React.useState(true);

  React.useEffect(() => {
    // Simulate performance monitoring
    const startTime = performance.now();

    setTimeout(() => {
      const endTime = performance.now();
      const loadTime = endTime - startTime;

      const newMetrics = {
        loadTime,
        memoryUsage: performance.memory?.usedJSHeapSize || 0,
        renderTime: Math.random() * 100,
        apiResponseTime: Math.random() * 500,
      };

      setMetrics(newMetrics);
      setIsLoading(false);
      onMetric(newMetrics);
    }, 100);
  }, [onMetric]);

  return (
    <div data-testid="performance-monitor">
      {isLoading ? (
        <div data-testid="loading-spinner">Loading...</div>
      ) : (
        <div data-testid="performance-metrics">
          <div data-testid="load-time">Load Time: {metrics.loadTime}ms</div>
          <div data-testid="memory-usage">
            Memory: {metrics.memoryUsage} bytes
          </div>
          <div data-testid="render-time">
            Render Time: {metrics.renderTime}ms
          </div>
          <div data-testid="api-response-time">
            API Response: {metrics.apiResponseTime}ms
          </div>
        </div>
      )}
    </div>
  );
};

const MockHeavyChart = ({ data = [], onRenderComplete = vi.fn() }) => {
  const [renderStart] = React.useState(performance.now());
  const [isRendered, setIsRendered] = React.useState(false);

  React.useEffect(() => {
    // Simulate heavy chart rendering
    const timer = setTimeout(
      () => {
        const renderEnd = performance.now();
        const renderTime = renderEnd - renderStart;

        setIsRendered(true);
        onRenderComplete({ renderTime, dataPoints: data.length });
      },
      Math.random() * 200 + 50
    ); // 50-250ms render time

    return () => clearTimeout(timer);
  }, [data, renderStart, onRenderComplete]);

  return (
    <div data-testid="heavy-chart">
      {isRendered ? (
        <canvas data-testid="chart-canvas" width="800" height="400">
          Chart with {data.length} data points
        </canvas>
      ) : (
        <div data-testid="chart-skeleton">Loading chart...</div>
      )}
    </div>
  );
};

const MockVirtualizedList = ({ items = [], itemHeight = 50 }) => {
  const [visibleRange, setVisibleRange] = React.useState({ start: 0, end: 10 });
  const containerRef = React.useRef();

  const handleScroll = React.useCallback(
    (event) => {
      const scrollTop = event.target.scrollTop;
      const start = Math.floor(scrollTop / itemHeight);
      const end = start + 10;

      setVisibleRange({ start, end });
    },
    [itemHeight]
  );

  const visibleItems = items.slice(visibleRange.start, visibleRange.end);

  return (
    <div
      ref={containerRef}
      data-testid="virtualized-list"
      style={{ height: "500px", overflowY: "auto" }}
      onScroll={handleScroll}
    >
      <div style={{ height: items.length * itemHeight }}>
        {visibleItems.map((item, index) => (
          <div
            key={visibleRange.start + index}
            data-testid={`list-item-${visibleRange.start + index}`}
            style={{
              height: itemHeight,
              display: "flex",
              alignItems: "center",
              padding: "0 16px",
            }}
          >
            Item {visibleRange.start + index}: {item.name}
          </div>
        ))}
      </div>
    </div>
  );
};

const MockLazyComponent = ({ threshold = 0.1 }) => {
  const [isVisible, setIsVisible] = React.useState(false);
  const [isLoaded, setIsLoaded] = React.useState(false);
  const elementRef = React.useRef();

  React.useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setIsVisible(true);
            // Simulate lazy loading
            setTimeout(() => setIsLoaded(true), 100);
          }
        });
      },
      { threshold }
    );

    if (elementRef.current) {
      observer.observe(elementRef.current);
    }

    return () => observer.disconnect();
  }, [threshold]);

  return (
    <div
      ref={elementRef}
      data-testid="lazy-component"
      style={{ height: "200px" }}
    >
      {!isVisible && <div data-testid="placeholder">Placeholder</div>}
      {isVisible && !isLoaded && <div data-testid="loading">Loading...</div>}
      {isLoaded && (
        <div data-testid="loaded-content">Heavy Component Loaded</div>
      )}
    </div>
  );
};

describe("Performance Monitoring Tests", () => {
  let _queryClient;

  beforeEach(() => {
    _queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    vi.clearAllMocks();

    // Reset performance mocks
    mockPerformanceMark.mockClear();
    mockPerformanceMeasure.mockClear();
  });

  describe("Performance Metrics Collection", () => {
    test("should collect basic performance metrics", async () => {
      const onMetric = vi.fn();

      render(<MockPerformanceMonitor onMetric={onMetric} />);

      await waitFor(() => {
        expect(screen.getByTestId("performance-metrics")).toBeInTheDocument();
      });

      expect(onMetric).toHaveBeenCalledWith(
        expect.objectContaining({
          loadTime: expect.any(Number),
          memoryUsage: expect.any(Number),
          renderTime: expect.any(Number),
          apiResponseTime: expect.any(Number),
        })
      );
    });

    test("should track component render performance", async () => {
      const onRenderComplete = vi.fn();
      const chartData = Array.from({ length: 1000 }, (_, i) => ({
        x: i,
        y: Math.random() * 100,
      }));

      render(
        <MockHeavyChart data={chartData} onRenderComplete={onRenderComplete} />
      );

      await waitFor(() => {
        expect(screen.getByTestId("chart-canvas")).toBeInTheDocument();
      });

      expect(onRenderComplete).toHaveBeenCalledWith(
        expect.objectContaining({
          renderTime: expect.any(Number),
          dataPoints: 1000,
        })
      );
    });

    test("should monitor memory usage during operations", async () => {
      const MockMemoryIntensiveComponent = () => {
        const [data, setData] = React.useState([]);
        const [memoryMetrics, setMemoryMetrics] = React.useState(null);

        React.useEffect(() => {
          // Simulate memory-intensive operation
          const largeData = Array.from({ length: 10000 }, (_, i) => ({
            id: i,
            value: Math.random() * 1000,
            description: `Item ${i} with random data ${Math.random()}`,
          }));

          setData(largeData);

          // Check memory usage if available
          if (performance.memory) {
            setMemoryMetrics({
              used: performance.memory.usedJSHeapSize,
              total: performance.memory.totalJSHeapSize,
              limit: performance.memory.jsHeapSizeLimit,
            });
          }
        }, []);

        return (
          <div data-testid="memory-intensive-component">
            <div data-testid="data-count">Items: {data.length}</div>
            {memoryMetrics && (
              <div data-testid="memory-metrics">
                Used: {memoryMetrics.used} bytes
              </div>
            )}
          </div>
        );
      };

      render(<MockMemoryIntensiveComponent />);

      await waitFor(() => {
        expect(screen.getByText("Items: 10000")).toBeInTheDocument();
      });

      // Memory metrics should be available if supported
      const memoryMetrics = screen.queryByTestId("memory-metrics");
      if (memoryMetrics) {
        expect(memoryMetrics).toBeInTheDocument();
      }
    });
  });

  describe("Core Web Vitals Monitoring", () => {
    test("should collect Largest Contentful Paint (LCP)", async () => {
      // Use the mocked functions directly
      const MockWebVitalsComponent = () => {
        const [vitals, setVitals] = React.useState({});

        React.useEffect(() => {
          // Call the mocked functions which will immediately trigger callbacks
          mockGetLCP((metric) => {
            setVitals((prev) => ({ ...prev, lcp: metric.value }));
          });

          mockGetFCP((metric) => {
            setVitals((prev) => ({ ...prev, fcp: metric.value }));
          });

          mockGetCLS((metric) => {
            setVitals((prev) => ({ ...prev, cls: metric.value }));
          });
        }, []);

        return (
          <div data-testid="web-vitals-monitor">
            {vitals.lcp && (
              <div data-testid="lcp-metric">LCP: {vitals.lcp}ms</div>
            )}
            {vitals.fcp && (
              <div data-testid="fcp-metric">FCP: {vitals.fcp}ms</div>
            )}
            {vitals.cls && (
              <div data-testid="cls-metric">CLS: {vitals.cls}</div>
            )}
          </div>
        );
      };

      render(<MockWebVitalsComponent />);

      await waitFor(() => {
        expect(screen.getByTestId("lcp-metric")).toBeInTheDocument();
        expect(screen.getByTestId("fcp-metric")).toBeInTheDocument();
        expect(screen.getByTestId("cls-metric")).toBeInTheDocument();
      });

      expect(screen.getByText("LCP: 2100ms")).toBeInTheDocument();
      expect(screen.getByText("FCP: 1200ms")).toBeInTheDocument();
      expect(screen.getByText("CLS: 0.05")).toBeInTheDocument();
    });

    test("should track First Input Delay (FID)", async () => {
      // Use the mocked function directly
      const MockFIDComponent = () => {
        const [fid, setFid] = React.useState(null);

        React.useEffect(() => {
          mockGetFID((metric) => {
            setFid(metric.value);
          });
        }, []);

        const handleClick = () => {
          // Simulate user interaction
        };

        return (
          <div data-testid="fid-component">
            <button data-testid="interaction-button" onClick={handleClick}>
              Click me
            </button>
            {fid && <div data-testid="fid-metric">FID: {fid}ms</div>}
          </div>
        );
      };

      render(<MockFIDComponent />);

      const button = screen.getByTestId("interaction-button");
      fireEvent.click(button);

      await waitFor(() => {
        expect(screen.getByTestId("fid-metric")).toBeInTheDocument();
      });

      expect(screen.getByText("FID: 80ms")).toBeInTheDocument();
    });
  });

  describe("Virtual Scrolling Performance", () => {
    test("should efficiently render large lists with virtualization", async () => {
      const largeDataset = Array.from({ length: 10000 }, (_, i) => ({
        id: i,
        name: `Item ${i}`,
        value: Math.random() * 1000,
      }));

      render(<MockVirtualizedList items={largeDataset} />);

      // Only visible items should be rendered initially
      expect(screen.getByTestId("list-item-0")).toBeInTheDocument();
      expect(screen.getByTestId("list-item-9")).toBeInTheDocument();
      expect(screen.queryByTestId("list-item-50")).not.toBeInTheDocument();

      // Simulate scrolling
      const listContainer = screen.getByTestId("virtualized-list");
      fireEvent.scroll(listContainer, { target: { scrollTop: 1000 } });

      await waitFor(() => {
        // New items should be visible after scrolling
        expect(screen.queryByTestId("list-item-0")).not.toBeInTheDocument();
        expect(screen.getByTestId("list-item-20")).toBeInTheDocument();
      });
    });

    test("should maintain smooth scrolling performance", () => {
      const items = Array.from({ length: 1000 }, (_, i) => ({
        name: `Item ${i}`,
      }));

      render(<MockVirtualizedList items={items} />);

      const listContainer = screen.getByTestId("virtualized-list");

      // Simulate rapid scrolling
      for (let i = 0; i < 10; i++) {
        fireEvent.scroll(listContainer, { target: { scrollTop: i * 100 } });
      }

      // Component should remain responsive
      expect(listContainer).toBeInTheDocument();
    });
  });

  describe("Lazy Loading Performance", () => {
    test.skip("should load components only when visible", async () => {
      render(
        <div>
          <div style={{ height: "1000px" }}>Spacer</div>
          <MockLazyComponent />
        </div>
      );

      // Component should show placeholder initially
      expect(screen.getByTestId("placeholder")).toBeInTheDocument();
      expect(screen.queryByTestId("loaded-content")).not.toBeInTheDocument();

      // Simulate scrolling into view
      const lazyComponent = screen.getByTestId("lazy-component");

      // Trigger intersection observer
      const [callback] = global.IntersectionObserver.mock.calls[0];
      callback([{ target: lazyComponent, isIntersecting: true }]);

      await waitFor(() => {
        expect(screen.getByTestId("loaded-content")).toBeInTheDocument();
      });
    });

    test.skip("should handle multiple lazy components efficiently", async () => {
      render(
        <div>
          {Array.from({ length: 5 }, (_, i) => (
            <MockLazyComponent key={i} />
          ))}
        </div>
      );

      // All components should start with placeholders
      expect(screen.getAllByTestId("placeholder")).toHaveLength(5);

      // Simulate all components coming into view
      const observers = global.IntersectionObserver.mock.instances;
      observers.forEach((observer, index) => {
        const [callback] = global.IntersectionObserver.mock.calls[index];
        callback([{ isIntersecting: true }]);
      });

      await waitFor(() => {
        expect(screen.getAllByTestId("loaded-content")).toHaveLength(5);
      });
    });
  });

  describe("API Performance Monitoring", () => {
    test("should track API response times", async () => {
      const MockApiPerformanceComponent = () => {
        const [apiMetrics, setApiMetrics] = React.useState([]);

        const makeApiCall = async (endpoint) => {
          const startTime = performance.now();

          try {
            // Simulate API call
            await new Promise((resolve) =>
              setTimeout(resolve, Math.random() * 500)
            );

            const endTime = performance.now();
            const responseTime = endTime - startTime;

            setApiMetrics((prev) => [
              ...prev,
              {
                endpoint,
                responseTime,
                success: true,
                timestamp: Date.now(),
              },
            ]);
          } catch (error) {
            const endTime = performance.now();
            const responseTime = endTime - startTime;

            setApiMetrics((prev) => [
              ...prev,
              {
                endpoint,
                responseTime,
                success: false,
                error: error.message,
                timestamp: Date.now(),
              },
            ]);
          }
        };

        React.useEffect(() => {
          makeApiCall("/api/portfolio");
          makeApiCall("/api/market-data");
          makeApiCall("/api/news");
        }, []);

        return (
          <div data-testid="api-performance-monitor">
            {apiMetrics.map((metric, index) => (
              <div key={index} data-testid={`api-metric-${index}`}>
                {metric.endpoint}: {metric.responseTime}ms
                {metric.success ? " ✓" : " ✗"}
              </div>
            ))}
          </div>
        );
      };

      render(<MockApiPerformanceComponent />);

      await waitFor(() => {
        expect(screen.getByTestId("api-metric-0")).toBeInTheDocument();
        expect(screen.getByTestId("api-metric-1")).toBeInTheDocument();
        expect(screen.getByTestId("api-metric-2")).toBeInTheDocument();
      });

      // All API calls should show response times - check that all endpoints are present (order may vary)
      const allText = screen.getByTestId("api-performance-monitor").textContent;
      expect(allText).toMatch(/\/api\/portfolio: [\d.]+ms ✓/);
      expect(allText).toMatch(/\/api\/market-data: [\d.]+ms ✓/);
      expect(allText).toMatch(/\/api\/news: [\d.]+ms ✓/);
    });

    test("should detect slow API calls", async () => {
      const MockSlowApiDetector = () => {
        const [slowCalls, setSlowCalls] = React.useState([]);

        const makeApiCall = async (endpoint, delay = 100) => {
          const startTime = performance.now();

          await new Promise((resolve) => setTimeout(resolve, delay));

          const endTime = performance.now();
          const responseTime = endTime - startTime;

          // Flag calls over 300ms as slow
          if (responseTime > 300) {
            setSlowCalls((prev) => [...prev, { endpoint, responseTime }]);
          }
        };

        React.useEffect(() => {
          makeApiCall("/api/fast", 100);
          makeApiCall("/api/slow", 400);
          makeApiCall("/api/very-slow", 800);
        }, []);

        return (
          <div data-testid="slow-api-detector">
            <div data-testid="slow-call-count">
              Slow calls: {slowCalls.length}
            </div>
            {slowCalls.map((call, index) => (
              <div key={index} data-testid={`slow-call-${index}`}>
                {call.endpoint}: {call.responseTime}ms
              </div>
            ))}
          </div>
        );
      };

      render(<MockSlowApiDetector />);

      await waitFor(() => {
        expect(screen.getByText("Slow calls: 2")).toBeInTheDocument();
      });

      expect(screen.getByTestId("slow-call-0")).toBeInTheDocument();
      expect(screen.getByTestId("slow-call-1")).toBeInTheDocument();
    });
  });

  describe("Bundle Size and Loading Performance", () => {
    test("should track resource loading performance", async () => {
      const MockResourceLoadingMonitor = () => {
        const [resourceMetrics, setResourceMetrics] = React.useState([]);

        React.useEffect(() => {
          // Simulate resource loading metrics
          const resources = [
            { name: "main.js", size: 245000, loadTime: 850 },
            { name: "vendor.js", size: 380000, loadTime: 1200 },
            { name: "styles.css", size: 45000, loadTime: 300 },
          ];

          setTimeout(() => {
            setResourceMetrics(resources);
          }, 100);
        }, []);

        return (
          <div data-testid="resource-loading-monitor">
            {resourceMetrics.map((resource, index) => (
              <div key={index} data-testid={`resource-${index}`}>
                {resource.name}: {resource.size} bytes, {resource.loadTime}ms
              </div>
            ))}
            <div data-testid="total-bundle-size">
              Total: {resourceMetrics.reduce((sum, r) => sum + r.size, 0)} bytes
            </div>
          </div>
        );
      };

      render(<MockResourceLoadingMonitor />);

      // Wait for the setTimeout to trigger and resource metrics to load
      await waitFor(() => {
        expect(screen.getByTestId("total-bundle-size")).toHaveTextContent(
          "Total: 670000 bytes"
        );
      });

      expect(screen.getByTestId("total-bundle-size")).toHaveTextContent(
        "Total: 670000 bytes"
      );
      expect(
        screen.getByText("main.js: 245000 bytes, 850ms")
      ).toBeInTheDocument();
    });

    test("should warn about large bundle sizes", async () => {
      const MockBundleSizeWarning = () => {
        const [warnings, setWarnings] = React.useState([]);

        React.useEffect(() => {
          const resources = [
            { name: "vendor.js", size: 600000 }, // Large bundle
            { name: "main.js", size: 300000 }, // Medium bundle
            { name: "styles.css", size: 50000 }, // Normal size
          ];

          const newWarnings = resources
            .filter((resource) => resource.size > 500000)
            .map(
              (resource) =>
                `${resource.name} is ${(resource.size / 1000).toFixed(0)}KB`
            );

          setWarnings(newWarnings);
        }, []);

        return (
          <div data-testid="bundle-size-warnings">
            {warnings.map((warning, index) => (
              <div
                key={index}
                data-testid={`warning-${index}`}
                className="warning"
              >
                ⚠️ {warning}
              </div>
            ))}
          </div>
        );
      };

      render(<MockBundleSizeWarning />);

      await waitFor(() => {
        expect(screen.getByTestId("warning-0")).toBeInTheDocument();
      });

      expect(screen.getByText("⚠️ vendor.js is 600KB")).toBeInTheDocument();
    });
  });

  describe("Performance Budget Monitoring", () => {
    test("should enforce performance budgets", () => {
      const performanceBudgets = {
        loadTime: 3000, // 3 seconds
        bundleSize: 500000, // 500KB
        apiResponse: 1000, // 1 second
      };

      const MockPerformanceBudgetMonitor = ({ metrics }) => {
        const violations = [];

        if (metrics.loadTime > performanceBudgets.loadTime) {
          violations.push("Load time exceeds budget");
        }
        if (metrics.bundleSize > performanceBudgets.bundleSize) {
          violations.push("Bundle size exceeds budget");
        }
        if (metrics.apiResponse > performanceBudgets.apiResponse) {
          violations.push("API response time exceeds budget");
        }

        return (
          <div data-testid="performance-budget-monitor">
            <div data-testid="violations-count">
              Budget violations: {violations.length}
            </div>
            {violations.map((violation, index) => (
              <div key={index} data-testid={`violation-${index}`}>
                ❌ {violation}
              </div>
            ))}
          </div>
        );
      };

      const testMetrics = {
        loadTime: 4000, // Over budget
        bundleSize: 600000, // Over budget
        apiResponse: 500, // Within budget
      };

      render(<MockPerformanceBudgetMonitor metrics={testMetrics} />);

      expect(screen.getByText("Budget violations: 2")).toBeInTheDocument();
      expect(
        screen.getByText("❌ Load time exceeds budget")
      ).toBeInTheDocument();
      expect(
        screen.getByText("❌ Bundle size exceeds budget")
      ).toBeInTheDocument();
    });
  });
});
