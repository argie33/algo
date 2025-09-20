import { describe, it, expect } from "vitest";

describe("Simple Test Suite", () => {
  it("basic math works", () => {
    expect(2 + 2).toBe(4);
  });

  it("string concatenation works", () => {
    expect("hello" + " world").toBe("hello world");
  });

  it("array operations work", () => {
    const arr = [1, 2, 3];
    expect(arr.length).toBe(3);
    expect(arr[0]).toBe(1);
  });
});