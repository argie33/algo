/**
 * Simple working unit test to validate test infrastructure
 */

describe("Basic Test Infrastructure", () => {
  test("should validate test environment is working", () => {
    expect(1 + 1).toBe(2);
  });

  test("should validate async operations work", async () => {
    const result = await Promise.resolve("test");
    expect(result).toBe("test");
  });

  test("should validate mock functions work", () => {
    const mockFn = jest.fn();
    mockFn("test");
    expect(mockFn).toHaveBeenCalledWith("test");
  });
});
