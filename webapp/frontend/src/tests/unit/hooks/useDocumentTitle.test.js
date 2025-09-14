/**
 * useDocumentTitle Hook Unit Tests
 * Tests document title management hook
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import React from "react";
import { render, cleanup } from "@testing-library/react";
import { useDocumentTitle } from "../../../hooks/useDocumentTitle.js";

// Test component to use the hook
function TestComponent({ title, suffix }) {
  useDocumentTitle(title, suffix);
  return React.createElement("div", { "data-testid": "test-component" });
}

describe("useDocumentTitle Hook", () => {
  const originalTitle = "Original Title";

  beforeEach(() => {
    document.title = originalTitle;
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("sets document title with default suffix", () => {
    render(React.createElement(TestComponent, { title: "Test Page" }));
    expect(document.title).toBe("Test Page | Financial Dashboard");
  });

  it("sets document title with custom suffix", () => {
    render(
      React.createElement(TestComponent, {
        title: "Test Page",
        suffix: "Custom App",
      })
    );
    expect(document.title).toBe("Test Page | Custom App");
  });

  it("restores previous title on unmount", () => {
    const { unmount } = render(
      React.createElement(TestComponent, { title: "Test Page" })
    );
    expect(document.title).toBe("Test Page | Financial Dashboard");

    unmount();
    expect(document.title).toBe(originalTitle);
  });

  it("handles empty title", () => {
    render(React.createElement(TestComponent, { title: "" }));
    // Should not change title if empty string provided
    expect(document.title).toBe(originalTitle);
  });

  it("handles null title", () => {
    render(React.createElement(TestComponent, { title: null }));
    // Should not change title if null provided
    expect(document.title).toBe(originalTitle);
  });

  it("handles undefined title", () => {
    render(React.createElement(TestComponent, { title: undefined }));
    // Should not change title if undefined provided
    expect(document.title).toBe(originalTitle);
  });

  it("updates title when prop changes", () => {
    const { rerender } = render(
      React.createElement(TestComponent, { title: "Initial Page" })
    );
    expect(document.title).toBe("Initial Page | Financial Dashboard");

    rerender(React.createElement(TestComponent, { title: "Updated Page" }));
    expect(document.title).toBe("Updated Page | Financial Dashboard");
  });

  it("updates suffix when prop changes", () => {
    const { rerender } = render(
      React.createElement(TestComponent, {
        title: "Test Page",
        suffix: "Initial App",
      })
    );
    expect(document.title).toBe("Test Page | Initial App");

    rerender(
      React.createElement(TestComponent, {
        title: "Test Page",
        suffix: "Updated App",
      })
    );
    expect(document.title).toBe("Test Page | Updated App");
  });

  it("handles title with special characters", () => {
    const specialTitle =
      "Test & Page > Special < Chars \"Quotes\" 'Apostrophes'";
    render(React.createElement(TestComponent, { title: specialTitle }));
    expect(document.title).toBe(`${specialTitle} | Financial Dashboard`);
  });

  it("handles title with whitespace", () => {
    render(React.createElement(TestComponent, { title: "  Spaced Title   " }));
    // The actual behavior - browser may normalize whitespace
    expect(document.title).toMatch(/Spaced Title.*Financial Dashboard/);
  });

  it("handles very long titles", () => {
    const longTitle = "A".repeat(200);
    render(React.createElement(TestComponent, { title: longTitle }));
    expect(document.title).toBe(`${longTitle} | Financial Dashboard`);
  });

  it("restores to suffix if previous title was empty", () => {
    document.title = "";

    const { unmount } = render(
      React.createElement(TestComponent, { title: "Test Page" })
    );
    expect(document.title).toBe("Test Page | Financial Dashboard");

    unmount();
    expect(document.title).toBe("Financial Dashboard");
  });

  it("handles multiple instances correctly", () => {
    const { unmount: unmount1 } = render(
      React.createElement(TestComponent, { title: "Page 1" })
    );
    expect(document.title).toBe("Page 1 | Financial Dashboard");

    const { unmount: unmount2 } = render(
      React.createElement(TestComponent, { title: "Page 2" })
    );

    // Last rendered should win
    expect(document.title).toBe("Page 2 | Financial Dashboard");

    unmount2();
    // Should restore to the original title that was there before Page 2
    expect(document.title).toBe("Page 1 | Financial Dashboard");

    unmount1();
    // Should restore to original title
    expect(document.title).toBe(originalTitle);
  });

  it("uses default suffix when suffix is not provided", () => {
    render(React.createElement(TestComponent, { title: "No Suffix Page" }));
    expect(document.title).toBe("No Suffix Page | Financial Dashboard");
  });

  it("handles component cleanup properly", () => {
    const { unmount } = render(
      React.createElement(TestComponent, { title: "Cleanup Test" })
    );
    expect(document.title).toBe("Cleanup Test | Financial Dashboard");

    unmount();
    expect(document.title).toBe(originalTitle);
  });
});
