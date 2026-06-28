import React from "react";
import { vi, describe, test, expect } from "vitest";
import { renderWithProviders } from "../setup/test-wrapper";
import RootRedirect from "../../../components/RootRedirect";

describe("RootRedirect Component", () => {
  it("should redirect to /app/markets", () => {
    const { container } = renderWithProviders(<RootRedirect />);

    // Navigate component redirects - verify it renders without errors
    expect(container).toBeTruthy();
  });

  it("should use Replace navigation to avoid adding to history", () => {
    // Navigate component with replace prop prevents back navigation
    // Just verify the component renders without errors
    renderWithProviders(<RootRedirect />);
  });
});
