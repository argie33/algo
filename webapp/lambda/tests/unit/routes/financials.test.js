const request = require("supertest");
const express = require("express");
const financialsRouter = require("../../../routes/financials");

// Mock dependencies
jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
  initializeDatabase: jest.fn().mockResolvedValue({}),
  healthCheck: jest.fn(),
  getPool: jest.fn(),
  closeDatabase: jest.fn(),
  transaction: jest.fn(),
}));

const { query } = require("../../../utils/database");

describe("Financials Routes", () => {
  let app;

  beforeEach(() => {
    app = express();
    app.use(express.json());
    
    // Add response formatter middleware
    app.use((req, res, next) => {
      res.success = (data, status = 200) => {
        res.status(status).json({
          success: true,
          data: data
        });
      };
      
      res.error = (message, status = 500) => {
        res.status(status).json({
          success: false,
          error: message
        });
      };
      
      next();
    });
    
    app.use("/financials", financialsRouter);
    jest.clearAllMocks();
  });

  describe("GET /financials/debug/tables", () => {
    test("should return debug information for financial tables", async () => {
      const mockTableExists = { rows: [{ exists: true }] };
      const mockColumns = {
        rows: [
          { column_name: "symbol", data_type: "text", is_nullable: "NO" },
          { column_name: "date", data_type: "date", is_nullable: "NO" },
          { column_name: "value", data_type: "numeric", is_nullable: "YES" }
        ]
      };
      const mockCount = { rows: [{ total: "1000" }] };
      const mockSample = {
        rows: [
          { symbol: "AAPL", date: "2023-12-31", value: 1000000 }
        ]
      };

      // Mock all 6 tables - each table gets 4 queries (exists, columns, count, sample)
      for (let i = 0; i < 6; i++) {
        query
          .mockResolvedValueOnce(mockTableExists)
          .mockResolvedValueOnce(mockColumns)
          .mockResolvedValueOnce(mockCount)
          .mockResolvedValueOnce(mockSample);
      }

      const response = await request(app).get("/financials/debug/tables").expect(200);

      expect(response.body).toMatchObject({
        status: "ok",
        tables: expect.objectContaining({
          balance_sheet: {
            exists: true,
            totalRecords: 1000,
            columns: expect.arrayContaining([
              expect.objectContaining({
                column_name: "symbol",
                data_type: "text"
              })
            ]),
            sampleData: expect.arrayContaining([
              expect.objectContaining({
                symbol: "AAPL"
              })
            ])
          }
        }),
        timestamp: expect.any(String)
      });
      expect(query).toHaveBeenCalledTimes(24); // 6 tables × 4 queries each
    });

    test("should handle missing tables gracefully", async () => {
      const mockTableNotExists = { rows: [{ exists: false }] };

      // Mock all 6 tables as not existing
      for (let i = 0; i < 6; i++) {
        query.mockResolvedValueOnce(mockTableNotExists);
      }

      const response = await request(app).get("/financials/debug/tables").expect(200);

      expect(response.body.tables.balance_sheet).toMatchObject({
        exists: false,
        message: "balance_sheet table does not exist"
      });
    });

    test("should handle database errors", async () => {
      query.mockRejectedValue(new Error("Database connection failed"));

      const response = await request(app).get("/financials/debug/tables").expect(200);

      expect(response.body).toMatchObject({
        status: "ok",
        tables: expect.objectContaining({
          balance_sheet: {
            exists: false,
            error: "Database connection failed"
          }
        }),
        timestamp: expect.any(String)
      });
    });
  });

  describe("GET /financials/:ticker/balance-sheet", () => {
    test("should return balance sheet data for annual period", async () => {
      const mockBalanceSheetData = {
        rows: [
          {
            symbol: "AAPL",
            date: "2023-12-31",
            item_name: "Total Assets",
            value: "352755000000"
          },
          {
            symbol: "AAPL",
            date: "2023-12-31",
            item_name: "Total Liabilities Net Minority Interest",
            value: "290437000000"
          },
          {
            symbol: "AAPL",
            date: "2023-12-31",
            item_name: "Cash And Cash Equivalents",
            value: "29965000000"
          }
        ]
      };

      query.mockResolvedValue(mockBalanceSheetData);

      const response = await request(app)
        .get("/financials/AAPL/balance-sheet")
        .query({ period: "annual" })
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.arrayContaining([
          expect.objectContaining({
            symbol: "AAPL",
            date: "2023-12-31",
            totalAssets: 352755000000,
            totalLiabilities: 290437000000,
            cashAndCashEquivalents: 29965000000,
            items: expect.objectContaining({
              "Total Assets": 352755000000,
              "Total Liabilities Net Minority Interest": 290437000000,
              "Cash And Cash Equivalents": 29965000000
            })
          })
        ]),
        metadata: {
          ticker: "AAPL",
          period: "annual",
          count: 1,
          timestamp: expect.any(String)
        }
      });
    });

    test("should handle quarterly period", async () => {
      const mockData = {
        rows: [
          {
            symbol: "AAPL",
            date: "2023-09-30",
            item_name: "Total Assets",
            value: "350000000000"
          }
        ]
      };

      query.mockResolvedValue(mockData);

      const response = await request(app)
        .get("/financials/AAPL/balance-sheet")
        .query({ period: "quarterly" })
        .expect(200);

      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("quarterly_balance_sheet"),
        ["AAPL"]
      );
      expect(response.body.metadata.period).toBe("quarterly");
    });

    test("should handle no data found", async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get("/financials/NONEXISTENT/balance-sheet")
        .expect(404);

      expect(response.body).toEqual({
        error: "No data found for this query"
      });
    });

    test("should handle database errors", async () => {
      query.mockRejectedValue(new Error("Table does not exist"));

      const response = await request(app)
        .get("/financials/AAPL/balance-sheet")
        .expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: "Failed to fetch balance sheet data",
        message: "Table does not exist"
      });
    });
  });

  describe("GET /financials/:ticker/income-statement", () => {
    test("should return income statement data", async () => {
      const mockIncomeData = {
        rows: [
          {
            symbol: "AAPL",
            date: "2023-12-31",
            item_name: "Total Revenue",
            value: "394328000000"
          },
          {
            symbol: "AAPL",
            date: "2023-12-31",
            item_name: "Net Income",
            value: "96995000000"
          },
          {
            symbol: "AAPL",
            date: "2023-12-31",
            item_name: "Gross Profit",
            value: "169148000000"
          }
        ]
      };

      query.mockResolvedValue(mockIncomeData);

      const response = await request(app)
        .get("/financials/AAPL/income-statement")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.arrayContaining([
          expect.objectContaining({
            symbol: "AAPL",
            date: "2023-12-31",
            revenue: 394328000000,
            netIncome: 96995000000,
            grossProfit: 169148000000,
            items: expect.objectContaining({
              "Total Revenue": 394328000000,
              "Net Income": 96995000000,
              "Gross Profit": 169148000000
            })
          })
        ]),
        metadata: {
          ticker: "AAPL",
          period: "annual",
          count: 1,
          timestamp: expect.any(String)
        }
      });
    });

    test("should handle TTM period", async () => {
      const mockData = { rows: [{ symbol: "AAPL", date: "2023-12-31", item_name: "Revenue", value: "400000000000" }] };
      query.mockResolvedValue(mockData);

      const _response = await request(app)
        .get("/financials/AAPL/income-statement")
        .query({ period: "ttm" })
        .expect(200);

      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("ttm_income_stmt"),
        ["AAPL"]
      );
    });

    test("should handle quarterly period", async () => {
      const mockData = { rows: [{ symbol: "AAPL", date: "2023-09-30", item_name: "Revenue", value: "100000000000" }] };
      query.mockResolvedValue(mockData);

      const _response = await request(app)
        .get("/financials/AAPL/income-statement")
        .query({ period: "quarterly" })
        .expect(200);

      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("quarterly_income_statement"),
        ["AAPL"]
      );
    });
  });

  describe("GET /financials/:ticker/cash-flow", () => {
    test("should return cash flow data", async () => {
      const mockCashFlowData = {
        rows: [
          {
            symbol: "AAPL",
            date: "2023-12-31",
            item_name: "Operating Cash Flow",
            value: "110543000000"
          },
          {
            symbol: "AAPL",
            date: "2023-12-31",
            item_name: "Free Cash Flow",
            value: "99584000000"
          },
          {
            symbol: "AAPL",
            date: "2023-12-31",
            item_name: "Capital Expenditure",
            value: "-10959000000"
          }
        ]
      };

      query.mockResolvedValue(mockCashFlowData);

      const response = await request(app)
        .get("/financials/AAPL/cash-flow")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.arrayContaining([
          expect.objectContaining({
            symbol: "AAPL",
            date: "2023-12-31",
            operatingCashFlow: 110543000000,
            freeCashFlow: 99584000000,
            capitalExpenditures: -10959000000,
            items: expect.objectContaining({
              "Operating Cash Flow": 110543000000,
              "Free Cash Flow": 99584000000,
              "Capital Expenditure": -10959000000
            })
          })
        ]),
        metadata: {
          ticker: "AAPL",
          period: "annual",
          count: 1,
          timestamp: expect.any(String)
        }
      });
    });

    test("should handle TTM and quarterly periods", async () => {
      const mockData = { rows: [{ symbol: "AAPL", date: "2023-12-31", item_name: "Operating Cash Flow", value: "100000000000" }] };
      query.mockResolvedValue(mockData);

      // Test TTM
      const _ttmResponse = await request(app)
        .get("/financials/AAPL/cash-flow")
        .query({ period: "ttm" })
        .expect(200);

      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("ttm_cashflow"),
        ["AAPL"]
      );

      jest.clearAllMocks();
      query.mockResolvedValue(mockData);

      // Test quarterly
      const _quarterlyResponse = await request(app)
        .get("/financials/AAPL/cash-flow")
        .query({ period: "quarterly" })
        .expect(200);

      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("quarterly_cash_flow"),
        ["AAPL"]
      );
    });
  });

  describe("GET /financials/ping", () => {
    test("should return health check response", async () => {
      const response = await request(app).get("/financials/ping").expect(200);

      expect(response.body).toEqual({
        success: true,
        service: "financials",
        timestamp: expect.any(String)
      });
    });
  });

  describe("GET /financials/:ticker/key-metrics", () => {
    test("should return organized key metrics data", async () => {
      const mockKeyMetrics = {
        rows: [
          {
            ticker: "AAPL",
            trailing_pe: 28.5,
            forward_pe: 25.2,
            price_to_sales_ttm: 7.8,
            price_to_book: 45.6,
            peg_ratio: 2.1,
            enterprise_value: 2800000000000,
            total_revenue: 394328000000,
            net_income: 96995000000,
            eps_trailing: 6.13,
            profit_margin_pct: 24.6,
            return_on_equity_pct: 147.4,
            dividend_yield: 0.47
          }
        ]
      };

      query.mockResolvedValue(mockKeyMetrics);

      const response = await request(app)
        .get("/financials/AAPL/key-metrics")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          valuation: {
            title: "Valuation Ratios",
            icon: "TrendingUp",
            metrics: expect.objectContaining({
              "P/E Ratio (Trailing)": 28.5,
              "P/E Ratio (Forward)": 25.2,
              "Price/Sales (TTM)": 7.8,
              "Price/Book": 45.6,
              "PEG Ratio": 2.1
            })
          },
          enterprise: {
            title: "Enterprise Metrics",
            icon: "BusinessCenter",
            metrics: expect.objectContaining({
              "Enterprise Value": 2800000000000
            })
          },
          financial_performance: {
            title: "Financial Performance",
            icon: "Assessment",
            metrics: expect.objectContaining({
              "Total Revenue": 394328000000,
              "Net Income": 96995000000
            })
          },
          earnings: {
            title: "Earnings Per Share",
            icon: "MonetizationOn",
            metrics: expect.objectContaining({
              "EPS (Trailing)": 6.13
            })
          },
          profitability: {
            title: "Profitability Margins",
            icon: "Percent",
            metrics: expect.objectContaining({
              "Profit Margin": 24.6
            })
          },
          returns: {
            title: "Return Metrics", 
            icon: "TrendingUp",
            metrics: expect.objectContaining({
              "Return on Equity": 147.4
            })
          },
          dividends: {
            title: "Dividend Information",
            icon: "Savings",
            metrics: expect.objectContaining({
              "Dividend Yield": 0.47
            })
          }
        }),
        metadata: {
          ticker: "AAPL",
          dataQuality: expect.any(String),
          totalMetrics: expect.any(Number),
          populatedMetrics: expect.any(Number),
          lastUpdated: expect.any(String),
          source: "key_metrics table via loadinfo"
        }
      });
    });

    test("should handle no metrics data found", async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get("/financials/NONEXISTENT/key-metrics")
        .expect(200);

      expect(response.body).toMatchObject({
        success: false,
        error: "No key metrics data found",
        data: null,
        metadata: {
          ticker: "NONEXISTENT",
          message: "Key metrics data not available for this ticker"
        }
      });
    });

    test("should handle database errors", async () => {
      query.mockRejectedValue(new Error("Table does not exist"));

      const response = await request(app)
        .get("/financials/AAPL/key-metrics")
        .expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: "Failed to fetch key metrics data",
        message: "Table does not exist"
      });
    });
  });

  describe("GET /financials/data/:symbol", () => {
    test("should return comprehensive financial data for symbol", async () => {
      const mockFinancialData = {
        rows: [
          {
            symbol: "AAPL",
            date: "2023-12-31",
            item_name: "Total Revenue",
            value: "394328000000",
            statement_type: "income_statement"
          },
          {
            symbol: "AAPL",
            date: "2023-12-31",
            item_name: "Total Assets",
            value: "352755000000",
            statement_type: "balance_sheet"
          },
          {
            symbol: "AAPL",
            date: "2023-12-31",
            item_name: "Operating Cash Flow",
            value: "110543000000",
            statement_type: "cash_flow"
          }
        ]
      };

      query.mockResolvedValue(mockFinancialData);

      const response = await request(app)
        .get("/financials/data/AAPL")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: {
          balance_sheet: expect.arrayContaining([
            expect.objectContaining({
              date: "2023-12-31",
              item_name: "Total Assets",
              value: 352755000000
            })
          ]),
          income_statement: expect.arrayContaining([
            expect.objectContaining({
              date: "2023-12-31",
              item_name: "Total Revenue", 
              value: 394328000000
            })
          ]),
          cash_flow: expect.arrayContaining([
            expect.objectContaining({
              date: "2023-12-31",
              item_name: "Operating Cash Flow",
              value: 110543000000
            })
          ])
        },
        symbol: "AAPL",
        count: 3
      });
    });

    test("should handle no financial data found", async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get("/financials/data/NONEXISTENT")
        .expect(404);

      expect(response.body).toMatchObject({
        success: false,
        error: "No financial data found for symbol NONEXISTENT"
      });
    });
  });

  describe("GET /financials/earnings/:symbol", () => {
    test("should return earnings history data", async () => {
      const mockEarningsData = {
        rows: [
          {
            symbol: "AAPL",
            report_date: "2023-11-02",
            actual_eps: 1.46,
            estimated_eps: 1.39,
            surprise_percent: 5.04,
            revenue_actual: 89498000000,
            revenue_estimated: 89280000000,
            revenue_surprise_percent: 0.24
          }
        ]
      };

      query.mockResolvedValue(mockEarningsData);

      const response = await request(app)
        .get("/financials/earnings/AAPL")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.arrayContaining([
          expect.objectContaining({
            symbol: "AAPL",
            report_date: "2023-11-02",
            actual_eps: 1.46,
            estimated_eps: 1.39,
            surprise_percent: 5.04,
            revenue_actual: 89498000000,
            revenue_estimated: 89280000000,
            revenue_surprise_percent: 0.24
          })
        ]),
        count: 1,
        symbol: "AAPL"
      });
    });

    test("should handle no earnings data found", async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get("/financials/earnings/NONEXISTENT")
        .expect(404);

      expect(response.body).toMatchObject({
        success: false,
        error: "No earnings data found for symbol NONEXISTENT"
      });
    });
  });

  describe("GET /financials/cash-flow/:symbol", () => {
    test("should return cash flow data for symbol", async () => {
      const mockCashFlowData = {
        rows: [
          {
            symbol: "AAPL",
            date: "2023-12-31",
            item_name: "Operating Cash Flow",
            value: "110543000000"
          },
          {
            symbol: "AAPL",
            date: "2023-12-31",
            item_name: "Free Cash Flow",
            value: "99584000000"
          }
        ]
      };

      query.mockResolvedValue(mockCashFlowData);

      const response = await request(app)
        .get("/financials/cash-flow/AAPL")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.arrayContaining([
          expect.objectContaining({
            symbol: "AAPL",
            date: "2023-12-31",
            items: expect.objectContaining({
              "Operating Cash Flow": 110543000000,
              "Free Cash Flow": 99584000000
            })
          })
        ]),
        count: 1,
        symbol: "AAPL"
      });
    });

    test("should handle no cash flow data found", async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get("/financials/cash-flow/NONEXISTENT")
        .expect(404);

      expect(response.body).toMatchObject({
        success: false,
        error: "No cash flow data found for symbol NONEXISTENT"
      });
    });
  });
});