/**
 * Minimal test to check if Jest is working
 */

describe("Minimal Test Suite", () => {
  test("basic math should work", () => {
    expect(2 + 2).toBe(4);
  });

  test("string operations should work", () => {
    expect("hello".toUpperCase()).toBe("HELLO");
  });
});