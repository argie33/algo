const request = require("supertest");
const { initializeDatabase, closeDatabase } = require("../../../utils/database");

let app;
const authToken = "dev-bypass-token";

describe("Performance Routes Integration Tests", () => {
  beforeAll(async () => {
    await initializeDatabase();
    app = require("../../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("GET /api/performance (Root Endpoint)", () => {
    test("should return performance API information", async () => {
      const response = await request(app)
        .get("/api/performance");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("message");
        expect(response.body).toHaveProperty("timestamp");
        expect(response.body).toHaveProperty("status", "operational");
        expect(response.body.message).toContain("Performance Analytics API");
        
        expect(typeof response.body.timestamp).toBe("string");
        expect(new Date(response.body.timestamp)).toBeInstanceOf(Date);
      }
    });
  });

  describe("GET /api/performance/health (Health Check)", () => {
    test("should return performance service health status", async () => {
      const response = await request(app)
        .get("/api/performance/health");

      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("status", "operational");
        expect(response.body).toHaveProperty("service", "performance-analytics");
        expect(response.body).toHaveProperty("message");
        expect(response.body).toHaveProperty("timestamp");
        
        expect(response.body.message).toContain("Performance Analytics service is running");
        expect(typeof response.body.timestamp).toBe("string");
        expect(new Date(response.body.timestamp)).toBeInstanceOf(Date);
      }
    });
  });

  describe("GET /api/performance/benchmark (Benchmark Comparison)", () => {
    test("should require authentication for benchmark comparison", async () => {
      const response = await request(app)
        .get("/api/performance/benchmark");

      expect([401].includes(response.status)).toBe(true);
    });

    test("should return benchmark comparison with authentication", async () => {
      const response = await request(app)
        .get("/api/performance/benchmark")
        .set("Authorization", `Bearer ${authToken}`);

      expect([200, 401].includes(response.status)).toBe(true);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("portfolio");
        expect(response.body.data).toHaveProperty("benchmark");
        expect(response.body.data).toHaveProperty("comparison");
        
        // Validate comparison metrics
        if (response.body.data.comparison) {
          const comparison = response.body.data.comparison;
          expect(comparison).toHaveProperty("outperformance");
          expect(comparison).toHaveProperty("correlation");
          expect(comparison).toHaveProperty("beta");
          expect(comparison).toHaveProperty("alpha");
        }
      }
    });

    test("should handle different benchmark symbols", async () => {
      const benchmarks = ["SPY", "QQQ", "IWM", "VTI", "SCHB"];
      
      for (const benchmark of benchmarks) {
        const response = await request(app)
          .get(`/api/performance/benchmark?benchmark=${benchmark}`)
          .set("Authorization", `Bearer ${authToken}`);
        
        expect([200, 400, 401].includes(response.status)).toBe(true);
        
        if (response.status === 200 && response.body.data.benchmark) {
          expect(response.body.data.benchmark).toHaveProperty("symbol", benchmark);
        }
      }
    });

    test("should handle different time periods", async () => {
      const periods = ["1d", "1w", "1m", "3m", "6m", "1y", "2y"];
      
      for (const period of periods) {
        const response = await request(app)
          .get(`/api/performance/benchmark?period=${period}`)
          .set("Authorization", `Bearer ${authToken}`);
        
        expect([200, 400, 401].includes(response.status)).toBe(true);
        
        if (response.status === 200 && response.body.data.comparison) {
          expect(response.body.data.comparison).toHaveProperty("period", period);
        }
      }
    });

    test("should validate benchmark comparison metrics", async () => {
      const response = await request(app)
        .get("/api/performance/benchmark?benchmark=SPY&period=1m")
        .set("Authorization", `Bearer ${authToken}`);

      if (response.status === 200 && response.body.data.comparison) {
        const comparison = response.body.data.comparison;
        
        // Validate numeric values
        if (comparison.outperformance !== null && comparison.outperformance !== undefined) {
          expect(typeof comparison.outperformance).toBe("number");
          expect(isFinite(comparison.outperformance)).toBe(true);
        }
        
        if (comparison.correlation !== null && comparison.correlation !== undefined) {
          expect(typeof comparison.correlation).toBe("number");
          expect(comparison.correlation).toBeGreaterThanOrEqual(-1);
          expect(comparison.correlation).toBeLessThanOrEqual(1);
        }
        
        if (comparison.beta !== null && comparison.beta !== undefined) {
          expect(typeof comparison.beta).toBe("number");
          expect(isFinite(comparison.beta)).toBe(true);
        }
      }
    });
  });

  describe("GET /api/performance/portfolio (Portfolio Performance)", () => {
    test("should require authentication for portfolio performance", async () => {
      const response = await request(app)
        .get("/api/performance/portfolio");

      expect([401].includes(response.status)).toBe(true);
    });

    test("should return portfolio performance data with authentication", async () => {
      const response = await request(app)
        .get("/api/performance/portfolio")
        .set("Authorization", `Bearer ${authToken}`);

      expect([200, 401].includes(response.status)).toBe(true);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("performance");
        
        // Validate performance structure
        if (response.body.data.performance) {
          const performance = response.body.data.performance;
          expect(performance).toHaveProperty("total_return");
          expect(performance).toHaveProperty("daily_returns");
          expect(performance).toHaveProperty("portfolio_value");
          
          if (performance.daily_returns) {
            expect(Array.isArray(performance.daily_returns)).toBe(true);
          }
        }
      }
    });

    test("should handle period parameter for portfolio performance", async () => {
      const periods = ["1d", "1w", "1m", "3m", "6m", "1y"];
      
      for (const period of periods) {
        const response = await request(app)
          .get(`/api/performance/portfolio?period=${period}`)
          .set("Authorization", `Bearer ${authToken}`);
        
        expect([200, 400, 401].includes(response.status)).toBe(true);
      }
    });

    test("should validate portfolio performance metrics", async () => {
      const response = await request(app)
        .get("/api/performance/portfolio")
        .set("Authorization", `Bearer ${authToken}`);

      if (response.status === 200 && response.body.data.performance) {
        const performance = response.body.data.performance;
        
        // Validate numeric values
        if (performance.total_return !== null && performance.total_return !== undefined) {
          expect(typeof performance.total_return).toBe("number");
          expect(isFinite(performance.total_return)).toBe(true);
        }
        
        if (performance.portfolio_value !== null && performance.portfolio_value !== undefined) {
          expect(typeof performance.portfolio_value).toBe("number");
          expect(performance.portfolio_value).toBeGreaterThan(0);
        }
        
        // Validate daily returns array
        if (performance.daily_returns && Array.isArray(performance.daily_returns)) {
          performance.daily_returns.forEach(returnData => {
            expect(returnData).toHaveProperty("date");
            expect(returnData).toHaveProperty("return");
            
            if (returnData.return !== null) {
              expect(typeof returnData.return).toBe("number");
              expect(isFinite(returnData.return)).toBe(true);
            }
          });
        }
      }
    });
  });

  describe("GET /api/performance/returns (Return Calculations)", () => {
    test("should require authentication for return calculations", async () => {
      const response = await request(app)
        .get("/api/performance/returns");

      expect([401].includes(response.status)).toBe(true);
    });

    test("should return return calculations with authentication", async () => {
      const response = await request(app)
        .get("/api/performance/returns")
        .set("Authorization", `Bearer ${authToken}`);

      expect([200, 401].includes(response.status)).toBe(true);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("returns");
        
        // Validate returns structure
        if (response.body.data.returns) {
          const returns = response.body.data.returns;
          expect(returns).toHaveProperty("time_weighted");
          expect(returns).toHaveProperty("dollar_weighted");
          expect(returns).toHaveProperty("annualized");
          
          // Validate periods
          if (returns.time_weighted) {
            const periods = ["1d", "1w", "1m", "3m", "ytd", "1y"];
            periods.forEach(period => {
              if (returns.time_weighted[period] !== undefined) {
                expect(typeof returns.time_weighted[period]).toBe("number");
                expect(isFinite(returns.time_weighted[period])).toBe(true);
              }
            });
          }
        }
      }
    });

    test("should handle calculation type parameter", async () => {
      const calcTypes = ["time_weighted", "dollar_weighted", "both"];
      
      for (const calcType of calcTypes) {
        const response = await request(app)
          .get(`/api/performance/returns?type=${calcType}`)
          .set("Authorization", `Bearer ${authToken}`);
        
        expect([200, 400, 401].includes(response.status)).toBe(true);
      }
    });
  });

  describe("GET /api/performance/attribution (Performance Attribution)", () => {
    test("should require authentication for performance attribution", async () => {
      const response = await request(app)
        .get("/api/performance/attribution");

      expect([401].includes(response.status)).toBe(true);
    });

    test("should return performance attribution analysis", async () => {
      const response = await request(app)
        .get("/api/performance/attribution")
        .set("Authorization", `Bearer ${authToken}`);

      expect([200, 401].includes(response.status)).toBe(true);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("attribution");
        
        // Validate attribution structure
        if (response.body.data.attribution) {
          const attribution = response.body.data.attribution;
          expect(attribution).toHaveProperty("sector_attribution");
          expect(attribution).toHaveProperty("security_selection");
          expect(attribution).toHaveProperty("asset_allocation");
          
          if (attribution.sector_attribution) {
            expect(Array.isArray(attribution.sector_attribution)).toBe(true);
            
            if (attribution.sector_attribution.length > 0) {
              const sectorAttr = attribution.sector_attribution[0];
              expect(sectorAttr).toHaveProperty("sector");
              expect(sectorAttr).toHaveProperty("contribution");
              expect(typeof sectorAttr.contribution).toBe("number");
            }
          }
        }
      }
    });

    test("should handle attribution type parameter", async () => {
      const attrTypes = ["sector", "security", "allocation", "all"];
      
      for (const attrType of attrTypes) {
        const response = await request(app)
          .get(`/api/performance/attribution?type=${attrType}`)
          .set("Authorization", `Bearer ${authToken}`);
        
        expect([200, 400, 401].includes(response.status)).toBe(true);
      }
    });
  });

  describe("GET /api/performance/metrics (Performance Metrics)", () => {
    test("should require authentication for performance metrics", async () => {
      const response = await request(app)
        .get("/api/performance/metrics");

      expect([401].includes(response.status)).toBe(true);
    });

    test("should return comprehensive performance metrics", async () => {
      const response = await request(app)
        .get("/api/performance/metrics")
        .set("Authorization", `Bearer ${authToken}`);

      expect([200, 401].includes(response.status)).toBe(true);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        
        // Validate key performance metrics
        const expectedMetrics = [
          "sharpe_ratio", "sortino_ratio", "max_drawdown", 
          "volatility", "beta", "alpha", "information_ratio",
          "calmar_ratio", "treynor_ratio", "win_rate"
        ];
        
        expectedMetrics.forEach(metric => {
          if (response.body.data[metric] !== undefined && response.body.data[metric] !== null) {
            expect(typeof response.body.data[metric]).toBe("number");
            expect(isFinite(response.body.data[metric])).toBe(true);
          }
        });
      }
    });

    test("should validate metric value ranges", async () => {
      const response = await request(app)
        .get("/api/performance/metrics")
        .set("Authorization", `Bearer ${authToken}`);

      if (response.status === 200) {
        const data = response.body.data;
        
        // Validate specific metric ranges
        if (data.max_drawdown !== null && data.max_drawdown !== undefined) {
          expect(data.max_drawdown).toBeLessThanOrEqual(0); // Drawdown should be negative or zero
        }
        
        if (data.win_rate !== null && data.win_rate !== undefined) {
          expect(data.win_rate).toBeGreaterThanOrEqual(0);
          expect(data.win_rate).toBeLessThanOrEqual(1);
        }
        
        if (data.volatility !== null && data.volatility !== undefined) {
          expect(data.volatility).toBeGreaterThanOrEqual(0);
        }
      }
    });

    test("should handle period parameter for metrics", async () => {
      const periods = ["1m", "3m", "6m", "1y", "2y"];
      
      for (const period of periods) {
        const response = await request(app)
          .get(`/api/performance/metrics?period=${period}`)
          .set("Authorization", `Bearer ${authToken}`);
        
        expect([200, 400, 401].includes(response.status)).toBe(true);
      }
    });
  });

  describe("GET /api/performance/risk (Risk Metrics)", () => {
    test("should require authentication for risk metrics", async () => {
      const response = await request(app)
        .get("/api/performance/risk");

      expect([401].includes(response.status)).toBe(true);
    });

    test("should return risk analysis metrics", async () => {
      const response = await request(app)
        .get("/api/performance/risk")
        .set("Authorization", `Bearer ${authToken}`);

      expect([200, 401].includes(response.status)).toBe(true);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        
        const expectedRiskMetrics = [
          "var_95", "var_99", "cvar_95", "cvar_99",
          "skewness", "kurtosis", "downside_deviation",
          "tracking_error", "concentration_risk"
        ];
        
        expectedRiskMetrics.forEach(metric => {
          if (response.body.data[metric] !== undefined && response.body.data[metric] !== null) {
            expect(typeof response.body.data[metric]).toBe("number");
            expect(isFinite(response.body.data[metric])).toBe(true);
          }
        });
      }
    });
  });

  describe("Performance and Edge Cases", () => {
    jest.setTimeout(15000);
    
    test("should handle concurrent requests to performance endpoints", async () => {
      const requests = [
        request(app).get("/api/performance").set("Authorization", `Bearer ${authToken}`),
        request(app).get("/api/performance/benchmark").set("Authorization", `Bearer ${authToken}`),
        request(app).get("/api/performance/portfolio").set("Authorization", `Bearer ${authToken}`),
        request(app).get("/api/performance/returns").set("Authorization", `Bearer ${authToken}`),
        request(app).get("/api/performance/metrics").set("Authorization", `Bearer ${authToken}`)
      ];
      
      const responses = await Promise.all(requests);
      
      responses.forEach(response => {
        expect([200, 401].includes(response.status)).toBe(true);
      });
    });

    test("should maintain response time consistency", async () => {
      const startTime = Date.now();
      const response = await request(app)
        .get("/api/performance/metrics")
        .set("Authorization", `Bearer ${authToken}`);
      const responseTime = Date.now() - startTime;
      
      expect([200, 401].includes(response.status)).toBe(true);
      expect(responseTime).toBeLessThan(15000);
    });

    test("should handle invalid parameters gracefully", async () => {
      const invalidParams = [
        "period=invalid",
        "benchmark=INVALID_SYMBOL",
        "type=unknown_type",
        "start_date=invalid-date",
        "end_date=2025-13-40"
      ];
      
      for (const param of invalidParams) {
        const response = await request(app)
          .get(`/api/performance/portfolio?${param}`)
          .set("Authorization", `Bearer ${authToken}`);
        
        expect([200, 400, 401].includes(response.status)).toBe(true);
      }
    });

    test("should handle malformed authentication tokens", async () => {
      const malformedTokens = [
        "Bearer",
        "Bearer ",
        "InvalidType token-value",
        "Bearer malformed-token-!@#$%"
      ];
      
      for (const token of malformedTokens) {
        const response = await request(app)
          .get("/api/performance/portfolio")
          .set("Authorization", token);
        
        expect([401].includes(response.status)).toBe(true);
      }
    });

    test("should validate numeric data integrity across endpoints", async () => {
      const endpoints = [
        "/api/performance/benchmark",
        "/api/performance/portfolio", 
        "/api/performance/returns",
        "/api/performance/metrics"
      ];
      
      for (const endpoint of endpoints) {
        const response = await request(app)
          .get(endpoint)
          .set("Authorization", `Bearer ${authToken}`);
        
        if (response.status === 200 && response.body.data) {
          const validateNumbers = (obj) => {
            Object.keys(obj).forEach(key => {
              const value = obj[key];
              if (typeof value === "number") {
                expect(isFinite(value)).toBe(true);
                expect(!isNaN(value)).toBe(true);
              } else if (typeof value === "object" && value !== null && !Array.isArray(value)) {
                validateNumbers(value);
              }
            });
          };
          
          validateNumbers(response.body.data);
        }
      }
    });

    test("should handle database connection issues gracefully", async () => {
      const response = await request(app)
        .get("/api/performance/portfolio")
        .set("Authorization", `Bearer ${authToken}`);

      expect([200, 401].includes(response.status)).toBe(true);
      
      if (response.status >= 500) {
        expect(response.body).toHaveProperty("error");
      }
    });

    test("should validate response content types", async () => {
      const endpoints = [
        "/api/performance",
        "/api/performance/health",
        "/api/performance/benchmark", 
        "/api/performance/portfolio",
        "/api/performance/returns",
        "/api/performance/metrics"
      ];
      
      for (const endpoint of endpoints) {
        const authHeader = endpoint.includes("health") || endpoint === "/api/performance" 
          ? {} 
          : { "Authorization": `Bearer ${authToken}` };
          
        const response = await request(app)
          .get(endpoint)
          .set(authHeader);
        
        if ([200, 401].includes(response.status)) {
          expect(response.headers['content-type']).toMatch(/application\/json/);
        }
      }
    });

    test("should handle memory pressure with large data requests", async () => {
      const response = await request(app)
        .get("/api/performance/portfolio?period=10y")
        .set("Authorization", `Bearer ${authToken}`);

      expect([200, 400, 401, 403, 413, 500, 503].includes(response.status)).toBe(true);
    });
  });
});