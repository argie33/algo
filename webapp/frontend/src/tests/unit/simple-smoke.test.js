/**
 * Simple smoke test to verify test infrastructure works
 */

import { describe, it, expect } from "vitest";

describe("Simple Smoke Test", () => {
  it("should pass basic assertion", () => {
    expect(true).toBe(true);
  });

  it("should handle basic math", () => {
    expect(2 + 2).toBe(4);
  });

  it("should handle string operations", () => {
    expect("hello".toUpperCase()).toBe("HELLO");
  });
});