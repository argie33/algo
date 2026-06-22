import { describe, it, expect, vi } from "vitest";
import { batchRequests, batchPromises } from "../../../utils/requestBatcher";

describe("requestBatcher", () => {
  describe("batchRequests", () => {
    it("should process items sequentially when concurrency=1", async () => {
      const items = [1, 2, 3];
      const calls = [];

      const result = await batchRequests(
        items,
        async (item) => {
          calls.push(item);
          return item * 2;
        },
        1
      );

      expect(result).toEqual([2, 4, 6]);
      expect(calls).toEqual([1, 2, 3]);
    });

    it("should limit concurrency to specified level", async () => {
      const items = [1, 2, 3, 4, 5];
      let maxConcurrent = 0;
      let currentConcurrent = 0;

      const result = await batchRequests(
        items,
        async (item) => {
          currentConcurrent++;
          maxConcurrent = Math.max(maxConcurrent, currentConcurrent);
          await new Promise((resolve) => setTimeout(resolve, 10));
          currentConcurrent--;
          return item * 2;
        },
        2
      );

      expect(result).toEqual([2, 4, 6, 8, 10]);
      expect(maxConcurrent).toBeLessThanOrEqual(2);
    });

    it("should preserve order of results regardless of execution order", async () => {
      const items = ["a", "b", "c", "d", "e"];
      const delays = { a: 50, b: 10, c: 30, d: 20, e: 5 };

      const result = await batchRequests(
        items,
        async (item) => {
          await new Promise((resolve) => setTimeout(resolve, delays[item]));
          return item.toUpperCase();
        },
        3
      );

      expect(result).toEqual(["A", "B", "C", "D", "E"]);
    });

    it("should handle empty array", async () => {
      const result = await batchRequests([], async (item) => item * 2);
      expect(result).toEqual([]);
    });

    it("should handle single item", async () => {
      const result = await batchRequests([5], async (item) => item * 2, 1);
      expect(result).toEqual([10]);
    });

    it("should handle errors gracefully", async () => {
      const items = [1, 2, 3];

      const result = await batchRequests(items, async (item) => {
        if (item === 2) throw new Error("Test error");
        return item * 2;
      });

      expect(result[0]).toBe(2);
      expect(result[1]).toHaveProperty("error");
      expect(result[2]).toBe(6);
    });

    it("should process items with concurrency > item count", async () => {
      const items = [1, 2];
      const result = await batchRequests(items, async (item) => item * 2, 10);
      expect(result).toEqual([2, 4]);
    });

    it("should work with different concurrency levels", async () => {
      const testConcurrency = async (concurrency) => {
        const items = Array.from({ length: 10 }, (_, i) => i);
        let maxActive = 0;
        let active = 0;

        await batchRequests(
          items,
          async (item) => {
            active++;
            maxActive = Math.max(maxActive, active);
            await new Promise((r) => setTimeout(r, 5));
            active--;
            return item;
          },
          concurrency
        );

        return maxActive;
      };

      const max1 = await testConcurrency(1);
      const max5 = await testConcurrency(5);

      expect(max1).toBeLessThanOrEqual(1);
      expect(max5).toBeLessThanOrEqual(5);
    });
  });

  describe("batchPromises", () => {
    it("should execute promise functions with concurrency control", async () => {
      const fns = [async () => 1, async () => 2, async () => 3];

      const result = await batchPromises(fns, 2);
      expect(result).toEqual([1, 2, 3]);
    });

    it("should handle empty promise array", async () => {
      const result = await batchPromises([], 5);
      expect(result).toEqual([]);
    });

    it("should preserve promise execution order", async () => {
      const execution = [];
      const fns = [
        async () => {
          execution.push("a");
          return "a";
        },
        async () => {
          execution.push("b");
          return "b";
        },
        async () => {
          execution.push("c");
          return "c";
        },
      ];

      const result = await batchPromises(fns, 1);
      expect(result).toEqual(["a", "b", "c"]);
      expect(execution).toEqual(["a", "b", "c"]);
    });
  });

  describe("Real-world scenarios", () => {
    it("should handle API-like request batching", async () => {
      const symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"];
      const mockApiCalls = [];

      const result = await batchRequests(
        symbols,
        async (symbol) => {
          mockApiCalls.push({ symbol, timestamp: Date.now() });
          await new Promise((r) => setTimeout(r, 10));
          return { symbol, price: Math.random() * 100 };
        },
        2
      );

      expect(result).toHaveLength(5);
      expect(result.every((r) => r.symbol && typeof r.price === "number")).toBe(
        true
      );
      expect(mockApiCalls).toHaveLength(5);
    });

    it("should efficiently batch large dataset", async () => {
      const items = Array.from({ length: 100 }, (_, i) => i);
      let maxConcurrent = 0;
      let activeTasks = 0;

      const result = await batchRequests(
        items,
        async (item) => {
          activeTasks++;
          maxConcurrent = Math.max(maxConcurrent, activeTasks);
          await new Promise((r) => setTimeout(r, 1));
          activeTasks--;
          return item * 2;
        },
        5
      );

      expect(result).toHaveLength(100);
      expect(maxConcurrent).toBeLessThanOrEqual(5);
    });
  });
});
