/**
 * Backtest Store Tests
 * Tests file-based storage for backtesting strategies
 */

const backtestStore = require("../../utils/backtestStore");
const fs = require("fs");
const path = require("path");

// Mock fs module to avoid actual file operations
jest.mock("fs");

describe("Backtest Store", () => {
  const mockStrategies = [
    {
      id: "1",
      name: "Moving Average Strategy",
      code: "// MA strategy code",
      language: "javascript",
      created: "2024-01-01"
    },
    {
      id: "2", 
      name: "RSI Strategy",
      code: "// RSI strategy code",
      language: "python",
      created: "2024-01-02"
    }
  ];

  beforeEach(() => {
    jest.clearAllMocks();
    
    // Mock Date.now for consistent ID generation
    jest.spyOn(Date, 'now').mockReturnValue(1234567890123);
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe("loadStrategies", () => {
    test("should return empty array when file does not exist", () => {
      fs.existsSync.mockReturnValue(false);
      
      const result = backtestStore.loadStrategies();
      
      expect(result).toEqual([]);
      expect(fs.existsSync).toHaveBeenCalledWith(
        expect.stringContaining("user_backtest_store.json")
      );
    });

    test("should load strategies from existing file", () => {
      fs.existsSync.mockReturnValue(true);
      fs.readFileSync.mockReturnValue(JSON.stringify(mockStrategies));
      
      const result = backtestStore.loadStrategies();
      
      expect(result).toEqual(mockStrategies);
      expect(fs.readFileSync).toHaveBeenCalledWith(
        expect.stringContaining("user_backtest_store.json"),
        "utf8"
      );
    });

    test("should handle malformed JSON gracefully", () => {
      fs.existsSync.mockReturnValue(true);
      fs.readFileSync.mockReturnValue("invalid json");
      
      expect(() => backtestStore.loadStrategies()).toThrow();
    });

    test("should handle file read errors", () => {
      fs.existsSync.mockReturnValue(true);
      fs.readFileSync.mockImplementation(() => {
        throw new Error("File read error");
      });
      
      expect(() => backtestStore.loadStrategies()).toThrow("File read error");
    });
  });

  describe("saveStrategies", () => {
    test("should save strategies to file", () => {
      fs.writeFileSync.mockImplementation(() => {});
      
      backtestStore.saveStrategies(mockStrategies);
      
      expect(fs.writeFileSync).toHaveBeenCalledWith(
        expect.stringContaining("user_backtest_store.json"),
        JSON.stringify(mockStrategies, null, 2)
      );
    });

    test("should handle empty array", () => {
      fs.writeFileSync.mockImplementation(() => {});
      
      backtestStore.saveStrategies([]);
      
      expect(fs.writeFileSync).toHaveBeenCalledWith(
        expect.stringContaining("user_backtest_store.json"),
        JSON.stringify([], null, 2)
      );
    });

    test("should handle file write errors", () => {
      fs.writeFileSync.mockImplementation(() => {
        throw new Error("File write error");
      });
      
      expect(() => backtestStore.saveStrategies(mockStrategies)).toThrow("File write error");
    });

    test("should format JSON with proper indentation", () => {
      fs.writeFileSync.mockImplementation(() => {});
      
      backtestStore.saveStrategies(mockStrategies);
      
      const expectedJson = JSON.stringify(mockStrategies, null, 2);
      expect(fs.writeFileSync).toHaveBeenCalledWith(
        expect.any(String),
        expectedJson
      );
    });
  });

  describe("addStrategy", () => {
    test("should add new strategy with generated ID", () => {
      fs.existsSync.mockReturnValue(true);
      fs.readFileSync.mockReturnValue(JSON.stringify(mockStrategies));
      fs.writeFileSync.mockImplementation(() => {});
      
      const newStrategy = {
        name: "New Strategy",
        code: "// new code",
        language: "python"
      };
      
      const result = backtestStore.addStrategy(newStrategy);
      
      expect(result.id).toBe("1234567890123");
      expect(result.name).toBe("New Strategy");
      expect(result.code).toBe("// new code");
      expect(result.language).toBe("python");
      
      expect(fs.writeFileSync).toHaveBeenCalled();
    });

    test("should add strategy to empty store", () => {
      fs.existsSync.mockReturnValue(false);
      fs.writeFileSync.mockImplementation(() => {});
      
      const newStrategy = {
        name: "First Strategy",
        code: "// first code",
        language: "javascript"
      };
      
      const result = backtestStore.addStrategy(newStrategy);
      
      expect(result.id).toBe("1234567890123");
      expect(result.name).toBe("First Strategy");
      
      const expectedStrategies = [{ ...newStrategy, id: "1234567890123" }];
      expect(fs.writeFileSync).toHaveBeenCalledWith(
        expect.any(String),
        JSON.stringify(expectedStrategies, null, 2)
      );
    });

    test("should preserve existing strategies when adding", () => {
      fs.existsSync.mockReturnValue(true);
      fs.readFileSync.mockReturnValue(JSON.stringify([mockStrategies[0]]));
      fs.writeFileSync.mockImplementation(() => {});
      
      const newStrategy = {
        name: "Additional Strategy",
        code: "// additional code"
      };
      
      const result = backtestStore.addStrategy(newStrategy);
      
      expect(result.id).toBe("1234567890123");
      
      const savedData = fs.writeFileSync.mock.calls[0][1];
      const savedStrategies = JSON.parse(savedData);
      
      expect(savedStrategies).toHaveLength(2);
      expect(savedStrategies[0]).toEqual(mockStrategies[0]);
      expect(savedStrategies[1]).toEqual({ ...newStrategy, id: "1234567890123" });
    });

    test("should handle strategy with existing properties", () => {
      fs.existsSync.mockReturnValue(false);
      fs.writeFileSync.mockImplementation(() => {});
      
      const strategyWithId = {
        id: "existing-id", // This should be overwritten
        name: "Strategy with ID",
        code: "// code",
        metadata: { author: "test" }
      };
      
      const result = backtestStore.addStrategy(strategyWithId);
      
      expect(result.id).toBe("1234567890123"); // Generated ID overwrites existing
      expect(result.name).toBe("Strategy with ID");
      expect(result.metadata).toEqual({ author: "test" });
    });

    test("should handle load/save errors during add", () => {
      fs.existsSync.mockReturnValue(true);
      fs.readFileSync.mockImplementation(() => {
        throw new Error("Load error");
      });
      
      const newStrategy = { name: "Test" };
      
      expect(() => backtestStore.addStrategy(newStrategy)).toThrow("Load error");
    });
  });

  describe("getStrategy", () => {
    test("should find strategy by ID", () => {
      fs.existsSync.mockReturnValue(true);
      fs.readFileSync.mockReturnValue(JSON.stringify(mockStrategies));
      
      const result = backtestStore.getStrategy("2");
      
      expect(result).toEqual(mockStrategies[1]);
    });

    test("should return undefined for non-existent ID", () => {
      fs.existsSync.mockReturnValue(true);
      fs.readFileSync.mockReturnValue(JSON.stringify(mockStrategies));
      
      const result = backtestStore.getStrategy("999");
      
      expect(result).toBeUndefined();
    });

    test("should return undefined when store is empty", () => {
      fs.existsSync.mockReturnValue(false);
      
      const result = backtestStore.getStrategy("1");
      
      expect(result).toBeUndefined();
    });

    test("should handle string and number IDs correctly", () => {
      fs.existsSync.mockReturnValue(true);
      fs.readFileSync.mockReturnValue(JSON.stringify(mockStrategies));
      
      // Test string ID
      const result1 = backtestStore.getStrategy("1");
      expect(result1).toEqual(mockStrategies[0]);
      
      // Test that number ID doesn't match (strict comparison)
      const result2 = backtestStore.getStrategy(1);
      expect(result2).toBeUndefined();
    });

    test("should handle load errors gracefully", () => {
      fs.existsSync.mockReturnValue(true);
      fs.readFileSync.mockImplementation(() => {
        throw new Error("Load error");
      });
      
      expect(() => backtestStore.getStrategy("1")).toThrow("Load error");
    });
  });

  describe("deleteStrategy", () => {
    test("should delete strategy by ID", () => {
      fs.existsSync.mockReturnValue(true);
      fs.readFileSync.mockReturnValue(JSON.stringify(mockStrategies));
      fs.writeFileSync.mockImplementation(() => {});
      
      backtestStore.deleteStrategy("1");
      
      const savedData = fs.writeFileSync.mock.calls[0][1];
      const savedStrategies = JSON.parse(savedData);
      
      expect(savedStrategies).toHaveLength(1);
      expect(savedStrategies[0]).toEqual(mockStrategies[1]);
    });

    test("should handle deletion of non-existent ID", () => {
      fs.existsSync.mockReturnValue(true);
      fs.readFileSync.mockReturnValue(JSON.stringify(mockStrategies));
      fs.writeFileSync.mockImplementation(() => {});
      
      backtestStore.deleteStrategy("999");
      
      const savedData = fs.writeFileSync.mock.calls[0][1];
      const savedStrategies = JSON.parse(savedData);
      
      expect(savedStrategies).toHaveLength(2);
      expect(savedStrategies).toEqual(mockStrategies);
    });

    test("should handle deletion from empty store", () => {
      fs.existsSync.mockReturnValue(false);
      fs.writeFileSync.mockImplementation(() => {});
      
      backtestStore.deleteStrategy("1");
      
      const savedData = fs.writeFileSync.mock.calls[0][1];
      const savedStrategies = JSON.parse(savedData);
      
      expect(savedStrategies).toEqual([]);
    });

    test("should delete all matching IDs", () => {
      const duplicateStrategies = [
        { id: "1", name: "First" },
        { id: "2", name: "Second" }, 
        { id: "1", name: "Duplicate" } // Same ID as first
      ];
      
      fs.existsSync.mockReturnValue(true);
      fs.readFileSync.mockReturnValue(JSON.stringify(duplicateStrategies));
      fs.writeFileSync.mockImplementation(() => {});
      
      backtestStore.deleteStrategy("1");
      
      const savedData = fs.writeFileSync.mock.calls[0][1];
      const savedStrategies = JSON.parse(savedData);
      
      expect(savedStrategies).toHaveLength(1);
      expect(savedStrategies[0].name).toBe("Second");
    });

    test("should handle load/save errors during deletion", () => {
      fs.existsSync.mockReturnValue(true);
      fs.readFileSync.mockImplementation(() => {
        throw new Error("Load error");
      });
      
      expect(() => backtestStore.deleteStrategy("1")).toThrow("Load error");
    });
  });

  describe("Integration Tests", () => {
    test("should handle complete CRUD workflow", () => {
      // Start with empty store
      fs.existsSync.mockReturnValue(false);
      fs.writeFileSync.mockImplementation(() => {});
      
      // Add first strategy
      const strategy1 = { name: "Strategy 1", code: "code1" };
      const added1 = backtestStore.addStrategy(strategy1);
      expect(added1.id).toBeDefined();
      
      // Mock the store now contains the first strategy
      fs.existsSync.mockReturnValue(true);
      fs.readFileSync.mockReturnValue(JSON.stringify([added1]));
      
      // Add second strategy
      const strategy2 = { name: "Strategy 2", code: "code2" };
      const added2 = backtestStore.addStrategy(strategy2);
      
      // Mock the store now contains both strategies
      const bothStrategies = [added1, added2];
      fs.readFileSync.mockReturnValue(JSON.stringify(bothStrategies));
      
      // Load all strategies
      const loaded = backtestStore.loadStrategies();
      expect(loaded).toHaveLength(2);
      
      // Get specific strategy
      const retrieved = backtestStore.getStrategy(added1.id);
      expect(retrieved).toEqual(added1);
      
      // Delete strategy
      backtestStore.deleteStrategy(added1.id);
      expect(fs.writeFileSync).toHaveBeenCalled();
    });

    test("should maintain data consistency across operations", () => {
      const initialStrategies = [
        { id: "1", name: "Initial 1", version: 1 },
        { id: "2", name: "Initial 2", version: 1 }
      ];
      
      fs.existsSync.mockReturnValue(true);
      fs.readFileSync.mockReturnValue(JSON.stringify(initialStrategies));
      fs.writeFileSync.mockImplementation(() => {});
      
      // Add new strategy
      const newStrategy = { name: "New Strategy", version: 2 };
      const added = backtestStore.addStrategy(newStrategy);
      
      // Verify the save call preserved existing data
      const savedData = fs.writeFileSync.mock.calls[0][1];
      const savedStrategies = JSON.parse(savedData);
      
      expect(savedStrategies).toHaveLength(3);
      expect(savedStrategies.slice(0, 2)).toEqual(initialStrategies);
      expect(savedStrategies[2]).toEqual({ ...newStrategy, id: added.id });
    });

    test("should handle concurrent access simulation", () => {
      fs.existsSync.mockReturnValue(true);
      fs.readFileSync.mockReturnValue(JSON.stringify(mockStrategies));
      fs.writeFileSync.mockImplementation(() => {});
      
      // Mock different timestamps for each call
      const mockTimes = [1234567890123, 1234567890124];
      let callCount = 0;
      jest.spyOn(Date, 'now').mockImplementation(() => mockTimes[callCount++]);
      
      // Simulate multiple operations
      const strategy1 = { name: "Concurrent 1" };
      const strategy2 = { name: "Concurrent 2" };
      
      const added1 = backtestStore.addStrategy(strategy1);
      const added2 = backtestStore.addStrategy(strategy2);
      
      expect(added1.id).toBe("1234567890123");
      expect(added2.id).toBe("1234567890124");
      expect(added1.id).not.toBe(added2.id); // Different timestamps
    });
  });

  describe("File Path Handling", () => {
    test("should use correct file path", () => {
      fs.existsSync.mockReturnValue(false);
      
      backtestStore.loadStrategies();
      
      expect(fs.existsSync).toHaveBeenCalledWith(
        expect.stringMatching(/.*user_backtest_store\.json$/)
      );
    });

    test("should use absolute path from utils directory", () => {
      fs.existsSync.mockReturnValue(true);
      fs.readFileSync.mockReturnValue("[]");
      
      backtestStore.loadStrategies();
      
      const calledPath = fs.existsSync.mock.calls[0][0];
      expect(path.isAbsolute(calledPath)).toBe(true);
      expect(calledPath).toContain("lambda");
      expect(calledPath).toMatch(/user_backtest_store\.json$/);
    });
  });

  describe("Edge Cases", () => {
    test("should handle null and undefined inputs", () => {
      fs.existsSync.mockReturnValue(false);
      fs.writeFileSync.mockImplementation(() => {});
      
      // Adding null strategy should throw error
      expect(() => backtestStore.addStrategy(null)).toThrow("Cannot set properties of null");
      
      // Adding undefined strategy should throw error  
      expect(() => backtestStore.addStrategy(undefined)).toThrow("Cannot set properties of undefined");
    });

    test("should handle empty strategy objects", () => {
      fs.existsSync.mockReturnValue(false);
      fs.writeFileSync.mockImplementation(() => {});
      
      const emptyStrategy = {};
      const result = backtestStore.addStrategy(emptyStrategy);
      
      expect(result.id).toBe("1234567890123");
      expect(Object.keys(result)).toContain("id");
    });

    test("should handle strategies with complex data types", () => {
      fs.existsSync.mockReturnValue(false);
      fs.writeFileSync.mockImplementation(() => {});
      
      const complexStrategy = {
        name: "Complex Strategy",
        parameters: {
          lookback: 20,
          threshold: 0.05,
          symbols: ["AAPL", "GOOGL"]
        },
        results: {
          backtests: [
            { date: "2024-01-01", return: 0.02 },
            { date: "2024-01-02", return: -0.01 }
          ]
        }
      };
      
      const result = backtestStore.addStrategy(complexStrategy);
      
      expect(result.parameters).toEqual(complexStrategy.parameters);
      expect(result.results).toEqual(complexStrategy.results);
    });
  });
});