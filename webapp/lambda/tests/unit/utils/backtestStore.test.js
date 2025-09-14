const fs = require("fs");
const path = require("path");
const backtestStore = require("../../../utils/backtestStore");

// Mock fs module
jest.mock("fs");

describe("BacktestStore", () => {
  const mockStoreFile = path.join(__dirname, "../../../user_backtest_store.json");
  const mockStrategies = [
    {
      id: "1",
      name: "Test Strategy 1",
      code: "strategy code 1",
      createdAt: "2023-01-01T00:00:00Z"
    },
    {
      id: "2", 
      name: "Test Strategy 2",
      code: "strategy code 2",
      createdAt: "2023-01-02T00:00:00Z"
    }
  ];

  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(Date, "now").mockReturnValue(1234567890);
    
    // Ensure fs mocks have consistent default behavior
    fs.writeFileSync.mockImplementation(() => {});
    fs.readFileSync.mockReturnValue(JSON.stringify([]));
    fs.existsSync.mockReturnValue(false);
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe("loadStrategies", () => {
    it("should return empty array when store file does not exist", () => {
      fs.existsSync.mockReturnValue(false);

      const result = backtestStore.loadStrategies();

      expect(result).toEqual([]);
      expect(fs.existsSync).toHaveBeenCalledWith(mockStoreFile);
    });

    it("should load and parse strategies from file when it exists", () => {
      fs.existsSync.mockReturnValue(true);
      fs.readFileSync.mockReturnValue(JSON.stringify(mockStrategies));

      const result = backtestStore.loadStrategies();

      expect(result).toEqual(mockStrategies);
      expect(fs.readFileSync).toHaveBeenCalledWith(mockStoreFile, "utf8");
    });

    it("should handle JSON parse errors gracefully", () => {
      fs.existsSync.mockReturnValue(true);
      fs.readFileSync.mockReturnValue("invalid json");

      expect(() => backtestStore.loadStrategies()).toThrow();
    });

    it("should handle file read errors", () => {
      fs.existsSync.mockReturnValue(true);
      fs.readFileSync.mockImplementation(() => {
        throw new Error("File read error");
      });

      expect(() => backtestStore.loadStrategies()).toThrow("File read error");
    });
  });

  describe("saveStrategies", () => {
    it("should write strategies to file as formatted JSON", () => {
      const strategies = mockStrategies;

      backtestStore.saveStrategies(strategies);

      expect(fs.writeFileSync).toHaveBeenCalledWith(
        mockStoreFile,
        JSON.stringify(strategies, null, 2)
      );
    });

    it("should handle empty strategies array", () => {
      const strategies = [];

      backtestStore.saveStrategies(strategies);

      expect(fs.writeFileSync).toHaveBeenCalledWith(
        mockStoreFile,
        JSON.stringify([], null, 2)
      );
    });

    it("should handle file write errors", () => {
      // Store the original mock implementation
      const originalWriteFileSync = fs.writeFileSync;
      
      // Set up error-throwing mock
      fs.writeFileSync.mockImplementation(() => {
        throw new Error("File write error");
      });

      expect(() => backtestStore.saveStrategies(mockStrategies)).toThrow("File write error");
      
      // Restore the normal mock behavior immediately
      fs.writeFileSync.mockImplementation(() => {});
    });

    it("should handle undefined strategies", () => {
      // saveStrategies doesn't validate input - it passes undefined to JSON.stringify
      // JSON.stringify(undefined) returns undefined, which gets written to file
      expect(() => backtestStore.saveStrategies(undefined)).not.toThrow();
      expect(fs.writeFileSync).toHaveBeenCalledWith(
        mockStoreFile,
        undefined // JSON.stringify(undefined, null, 2) returns undefined
      );
    });

    it("should handle null strategies", () => {
      // JSON.stringify(null) returns "null" string
      expect(() => backtestStore.saveStrategies(null)).not.toThrow();
      expect(fs.writeFileSync).toHaveBeenCalledWith(
        mockStoreFile,
        "null" // JSON.stringify(null, null, 2) returns "null"
      );
    });
  });

  describe("addStrategy", () => {
    it("should add new strategy with generated ID", () => {
      fs.existsSync.mockReturnValue(true);
      fs.readFileSync.mockReturnValue(JSON.stringify(mockStrategies));

      const newStrategy = {
        name: "New Strategy",
        code: "new strategy code",
        createdAt: "2023-01-03T00:00:00Z"
      };

      const result = backtestStore.addStrategy(newStrategy);

      expect(result).toEqual({
        ...newStrategy,
        id: "1234567890"
      });

      expect(fs.writeFileSync).toHaveBeenCalledWith(
        mockStoreFile,
        JSON.stringify([...mockStrategies, { ...newStrategy, id: "1234567890" }], null, 2)
      );
    });

    it("should add strategy to empty store", () => {
      fs.existsSync.mockReturnValue(false);

      const newStrategy = {
        name: "First Strategy",
        code: "first strategy code"
      };

      const result = backtestStore.addStrategy(newStrategy);

      expect(result).toEqual({
        ...newStrategy,
        id: "1234567890"
      });

      expect(fs.writeFileSync).toHaveBeenCalledWith(
        mockStoreFile,
        JSON.stringify([{ ...newStrategy, id: "1234567890" }], null, 2)
      );
    });

    it("should preserve existing strategy properties", () => {
      fs.existsSync.mockReturnValue(false);

      const strategyWithExtraProps = {
        name: "Complex Strategy",
        code: "complex code",
        parameters: { param1: "value1" },
        metadata: { author: "test" }
      };

      const result = backtestStore.addStrategy(strategyWithExtraProps);

      expect(result).toEqual({
        ...strategyWithExtraProps,
        id: "1234567890"
      });
    });

    it("should generate unique IDs for multiple strategies", () => {
      fs.existsSync.mockReturnValue(false);
      
      // Mock different timestamps
      Date.now
        .mockReturnValueOnce(1111111111)
        .mockReturnValueOnce(2222222222);

      const strategy1 = { name: "Strategy 1", code: "code 1" };
      const strategy2 = { name: "Strategy 2", code: "code 2" };

      const result1 = backtestStore.addStrategy(strategy1);
      const result2 = backtestStore.addStrategy(strategy2);

      expect(result1.id).toBe("1111111111");
      expect(result2.id).toBe("2222222222");
    });

    it("should handle strategy without name", () => {
      fs.existsSync.mockReturnValue(false);

      const strategyWithoutName = {
        code: "code without name"
      };

      const result = backtestStore.addStrategy(strategyWithoutName);

      expect(result.id).toBe("1234567890");
      expect(result.code).toBe("code without name");
      expect(result.name).toBeUndefined();
    });
  });

  describe("getStrategy", () => {
    it("should return strategy with matching ID", () => {
      fs.existsSync.mockReturnValue(true);
      fs.readFileSync.mockReturnValue(JSON.stringify(mockStrategies));

      const result = backtestStore.getStrategy("1");

      expect(result).toEqual(mockStrategies[0]);
    });

    it("should return undefined for non-existent ID", () => {
      fs.existsSync.mockReturnValue(true);
      fs.readFileSync.mockReturnValue(JSON.stringify(mockStrategies));

      const result = backtestStore.getStrategy("999");

      expect(result).toBeUndefined();
    });

    it("should return undefined when store is empty", () => {
      fs.existsSync.mockReturnValue(false);

      const result = backtestStore.getStrategy("1");

      expect(result).toBeUndefined();
    });

    it("should handle null ID", () => {
      fs.existsSync.mockReturnValue(true);
      fs.readFileSync.mockReturnValue(JSON.stringify(mockStrategies));

      const result = backtestStore.getStrategy(null);

      expect(result).toBeUndefined();
    });

    it("should handle undefined ID", () => {
      fs.existsSync.mockReturnValue(true);
      fs.readFileSync.mockReturnValue(JSON.stringify(mockStrategies));

      const result = backtestStore.getStrategy(undefined);

      expect(result).toBeUndefined();
    });

    it("should perform string comparison for ID", () => {
      fs.existsSync.mockReturnValue(true);
      fs.readFileSync.mockReturnValue(JSON.stringify(mockStrategies));

      // Test that numeric 1 doesn't match string "1"
      const result1 = backtestStore.getStrategy(1);
      const result2 = backtestStore.getStrategy("1");

      expect(result1).toBeUndefined();
      expect(result2).toEqual(mockStrategies[0]);
    });
  });

  describe("deleteStrategy", () => {
    it("should remove strategy with matching ID", () => {
      fs.existsSync.mockReturnValue(true);
      fs.readFileSync.mockReturnValue(JSON.stringify(mockStrategies));

      backtestStore.deleteStrategy("1");

      const expectedStrategies = [mockStrategies[1]]; // Only second strategy remains

      expect(fs.writeFileSync).toHaveBeenCalledWith(
        mockStoreFile,
        JSON.stringify(expectedStrategies, null, 2)
      );
    });

    it("should not modify store when ID does not exist", () => {
      fs.existsSync.mockReturnValue(true);
      fs.readFileSync.mockReturnValue(JSON.stringify(mockStrategies));

      backtestStore.deleteStrategy("999");

      expect(fs.writeFileSync).toHaveBeenCalledWith(
        mockStoreFile,
        JSON.stringify(mockStrategies, null, 2)
      );
    });

    it("should handle empty store", () => {
      fs.existsSync.mockReturnValue(false);

      backtestStore.deleteStrategy("1");

      expect(fs.writeFileSync).toHaveBeenCalledWith(
        mockStoreFile,
        JSON.stringify([], null, 2)
      );
    });

    it("should remove all strategies with matching ID", () => {
      const strategiesWithDuplicates = [
        { id: "1", name: "Strategy 1A" },
        { id: "2", name: "Strategy 2" },
        { id: "1", name: "Strategy 1B" }, // Duplicate ID
      ];

      fs.existsSync.mockReturnValue(true);
      fs.readFileSync.mockReturnValue(JSON.stringify(strategiesWithDuplicates));

      backtestStore.deleteStrategy("1");

      const expectedStrategies = [{ id: "2", name: "Strategy 2" }];

      expect(fs.writeFileSync).toHaveBeenCalledWith(
        mockStoreFile,
        JSON.stringify(expectedStrategies, null, 2)
      );
    });

    it("should handle null ID", () => {
      fs.existsSync.mockReturnValue(true);
      fs.readFileSync.mockReturnValue(JSON.stringify(mockStrategies));

      backtestStore.deleteStrategy(null);

      // Should not remove anything since null !== "1" or "2"
      expect(fs.writeFileSync).toHaveBeenCalledWith(
        mockStoreFile,
        JSON.stringify(mockStrategies, null, 2)
      );
    });

    it("should handle undefined ID", () => {
      fs.existsSync.mockReturnValue(true);
      fs.readFileSync.mockReturnValue(JSON.stringify(mockStrategies));

      backtestStore.deleteStrategy(undefined);

      // Should not remove anything since undefined !== "1" or "2"
      expect(fs.writeFileSync).toHaveBeenCalledWith(
        mockStoreFile,
        JSON.stringify(mockStrategies, null, 2)
      );
    });

    it("should perform string comparison for ID", () => {
      fs.existsSync.mockReturnValue(true);
      fs.readFileSync.mockReturnValue(JSON.stringify(mockStrategies));

      // Test that numeric 1 doesn't match string "1"
      backtestStore.deleteStrategy(1);

      // Should not remove anything since numeric 1 !== string "1"
      expect(fs.writeFileSync).toHaveBeenCalledWith(
        mockStoreFile,
        JSON.stringify(mockStrategies, null, 2)
      );
    });
  });

  describe("integration scenarios", () => {
    it("should support full CRUD operations lifecycle", () => {
      // Start with empty store
      fs.existsSync.mockReturnValue(false);

      // Add first strategy
      const strategy1 = { name: "Strategy 1", code: "code 1" };
      Date.now.mockReturnValueOnce(1111111111);
      const added1 = backtestStore.addStrategy(strategy1);
      expect(added1.id).toBe("1111111111");

      // Mock store now has first strategy
      const storeAfterFirst = [{ ...strategy1, id: "1111111111" }];
      fs.existsSync.mockReturnValue(true);
      fs.readFileSync.mockReturnValue(JSON.stringify(storeAfterFirst));

      // Add second strategy
      const strategy2 = { name: "Strategy 2", code: "code 2" };
      Date.now.mockReturnValueOnce(2222222222);
      const added2 = backtestStore.addStrategy(strategy2);
      expect(added2.id).toBe("2222222222");

      // Mock store now has both strategies
      const storeAfterSecond = [
        { ...strategy1, id: "1111111111" },
        { ...strategy2, id: "2222222222" }
      ];
      fs.readFileSync.mockReturnValue(JSON.stringify(storeAfterSecond));

      // Get strategy
      const retrieved = backtestStore.getStrategy("1111111111");
      expect(retrieved).toEqual({ ...strategy1, id: "1111111111" });

      // Delete strategy
      backtestStore.deleteStrategy("1111111111");
      const expectedAfterDelete = [{ ...strategy2, id: "2222222222" }];
      expect(fs.writeFileSync).toHaveBeenLastCalledWith(
        mockStoreFile,
        JSON.stringify(expectedAfterDelete, null, 2)
      );
    });

    it("should handle concurrent access scenarios", () => {
      fs.existsSync.mockReturnValue(true);
      
      // Simulate file change between read operations
      fs.readFileSync
        .mockReturnValueOnce(JSON.stringify([{ id: "1", name: "Old Strategy" }]))
        .mockReturnValueOnce(JSON.stringify([{ id: "1", name: "New Strategy" }]));

      const result1 = backtestStore.getStrategy("1");
      const result2 = backtestStore.getStrategy("1");

      expect(result1.name).toBe("Old Strategy");
      expect(result2.name).toBe("New Strategy");
    });

    it("should maintain data consistency after multiple operations", () => {
      // Start with existing data
      const initialStrategies = [
        { id: "1", name: "Strategy 1" },
        { id: "2", name: "Strategy 2" }
      ];

      fs.existsSync.mockReturnValue(true);
      fs.readFileSync.mockReturnValue(JSON.stringify(initialStrategies));

      // Delete one strategy
      backtestStore.deleteStrategy("1");

      // Verify only strategy 2 remains
      expect(fs.writeFileSync).toHaveBeenCalledWith(
        mockStoreFile,
        JSON.stringify([{ id: "2", name: "Strategy 2" }], null, 2)
      );

      // Mock the store state after deletion
      fs.readFileSync.mockReturnValue(JSON.stringify([{ id: "2", name: "Strategy 2" }]));

      // Add new strategy
      Date.now.mockReturnValue(3333333333);
      const newStrategy = { name: "Strategy 3" };
      backtestStore.addStrategy(newStrategy);

      // Verify both remaining and new strategy exist
      // Note: Property order matches actual insertion order (name first, then id added)
      const expected = [
        { id: "2", name: "Strategy 2" },
        { name: "Strategy 3", id: "3333333333" }
      ];
      expect(fs.writeFileSync).toHaveBeenLastCalledWith(
        mockStoreFile,
        JSON.stringify(expected, null, 2)
      );
    });
  });
});