import { describe, it, expect } from "vitest";

describe("Simple Integration Test", () => {
  it("should integrate two functions", () => {
    const add = (a, b) => a + b;
    const multiply = (a, b) => a * b;

    // Integration test - combine operations
    const result = multiply(add(2, 3), 2);
    expect(result).toBe(10);
  });

  it("should test data flow", () => {
    const processData = (input) => {
      return input.map(x => x * 2).filter(x => x > 5);
    };

    const input = [1, 2, 3, 4, 5];
    const result = processData(input);
    expect(result).toEqual([6, 8, 10]);
  });

  it("should test module integration", () => {
    const userService = {
      getUser: (id) => ({ id, name: `User${id}` })
    };

    const displayService = {
      formatUser: (user) => `${user.name} (ID: ${user.id})`
    };

    // Integration of services
    const user = userService.getUser(123);
    const formatted = displayService.formatUser(user);
    expect(formatted).toBe("User123 (ID: 123)");
  });
});