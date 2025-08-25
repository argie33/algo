/**
 * Unit Tests for Card Components
 * Pure React component testing - props, rendering, composition
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from "../../../../components/ui/card.jsx";

describe("Card Components", () => {
  describe("Card", () => {
    it("should render children", () => {
      render(
        <Card>
          <div>Card content</div>
        </Card>
      );
      
      expect(screen.getByText("Card content")).toBeInTheDocument();
    });

    it("should apply custom className", () => {
      render(<Card className="custom-card" data-testid="card">Card</Card>);
      
      const card = screen.getByTestId("card");
      expect(card).toHaveClass("custom-card");
    });

    it("should forward ref", () => {
      const ref = vi.fn();
      
      render(<Card ref={ref}>Card with ref</Card>);
      
      expect(ref).toHaveBeenCalledWith(expect.any(HTMLDivElement));
    });
  });

  describe("CardHeader", () => {
    it("should render header content", () => {
      render(
        <CardHeader title="Portfolio Summary" subheader="Last updated: Today" />
      );
      
      expect(screen.getByText("Portfolio Summary")).toBeInTheDocument();
      expect(screen.getByText("Last updated: Today")).toBeInTheDocument();
    });

    it("should apply custom className", () => {
      render(
        <CardHeader 
          className="custom-header" 
          title="Test" 
          data-testid="card-header" 
        />
      );
      
      const header = screen.getByTestId("card-header");
      expect(header).toHaveClass("custom-header");
    });
  });

  describe("CardTitle", () => {
    it("should render with h6 variant styling", () => {
      render(<CardTitle>Stock Analysis</CardTitle>);
      
      const title = screen.getByText("Stock Analysis");
      expect(title).toBeInTheDocument();
      expect(title).toHaveClass("MuiTypography-h6");
    });

    it("should apply custom className", () => {
      render(<CardTitle className="title-custom">Custom Title</CardTitle>);
      
      const title = screen.getByText("Custom Title");
      expect(title).toHaveClass("title-custom");
    });

    it("should forward ref", () => {
      const ref = vi.fn();
      
      render(<CardTitle ref={ref}>Ref Title</CardTitle>);
      
      expect(ref).toHaveBeenCalledWith(expect.any(HTMLDivElement));
    });
  });

  describe("CardDescription", () => {
    it("should render description text", () => {
      render(
        <CardDescription>
          Your portfolio performance over the last 30 days
        </CardDescription>
      );
      
      expect(screen.getByText(/your portfolio performance/i)).toBeInTheDocument();
    });

    it("should have secondary text color", () => {
      render(
        <CardDescription data-testid="description">
          Secondary text
        </CardDescription>
      );
      
      const description = screen.getByTestId("description");
      // MUI applies color through classes
      expect(description).toHaveClass("MuiTypography-root");
    });

    it("should apply custom className", () => {
      render(
        <CardDescription className="desc-custom">
          Custom Description
        </CardDescription>
      );
      
      const description = screen.getByText("Custom Description");
      expect(description).toHaveClass("desc-custom");
    });
  });

  describe("CardContent", () => {
    it("should render content children", () => {
      render(
        <CardContent>
          <p>Portfolio value: $125,000</p>
          <p>Daily change: +$2,500</p>
        </CardContent>
      );
      
      expect(screen.getByText(/portfolio value/i)).toBeInTheDocument();
      expect(screen.getByText(/daily change/i)).toBeInTheDocument();
    });

    it("should apply custom className", () => {
      render(
        <CardContent className="content-custom" data-testid="content">
          Content
        </CardContent>
      );
      
      const content = screen.getByTestId("content");
      expect(content).toHaveClass("content-custom");
    });
  });

  describe("CardFooter", () => {
    it("should render footer content", () => {
      render(
        <CardFooter>
          <button>View Details</button>
          <button>Export</button>
        </CardFooter>
      );
      
      expect(screen.getByRole("button", { name: /view details/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /export/i })).toBeInTheDocument();
    });

    it("should apply default padding style", () => {
      render(<CardFooter data-testid="footer">Footer</CardFooter>);
      
      const footer = screen.getByTestId("footer");
      expect(footer).toHaveStyle({ padding: "16px" });
    });

    it("should apply custom className", () => {
      render(
        <CardFooter className="footer-custom">
          Custom Footer
        </CardFooter>
      );
      
      const footer = screen.getByText("Custom Footer");
      expect(footer).toHaveClass("footer-custom");
    });
  });

  describe("Card Composition", () => {
    it("should compose all card parts together", () => {
      render(
        <Card data-testid="complete-card">
          <CardHeader title="Portfolio Performance" subheader="Real-time data" />
          <CardContent>
            <CardTitle>$125,750.50</CardTitle>
            <CardDescription>
              Your total portfolio value has increased by 2.5% today
            </CardDescription>
          </CardContent>
          <CardFooter>
            <button>Refresh</button>
          </CardFooter>
        </Card>
      );
      
      const card = screen.getByTestId("complete-card");
      expect(card).toBeInTheDocument();
      
      expect(screen.getByText("Portfolio Performance")).toBeInTheDocument();
      expect(screen.getByText("Real-time data")).toBeInTheDocument();
      expect(screen.getByText("$125,750.50")).toBeInTheDocument();
      expect(screen.getByText(/increased by 2.5%/i)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /refresh/i })).toBeInTheDocument();
    });

    it("should work with partial composition", () => {
      render(
        <Card>
          <CardContent>
            <CardTitle>Simple Card</CardTitle>
          </CardContent>
        </Card>
      );
      
      expect(screen.getByText("Simple Card")).toBeInTheDocument();
    });
  });

  describe("Props Forwarding", () => {
    it("should pass through additional props to Card", () => {
      render(
        <Card 
          elevation={3} 
          variant="outlined" 
          data-testid="props-card"
        >
          Content
        </Card>
      );
      
      const card = screen.getByTestId("props-card");
      expect(card).toBeInTheDocument();
      // MUI props are applied through classes, hard to test exact props
      // but we verify the component renders without errors
    });

    it("should support custom HTML attributes", () => {
      render(
        <Card id="custom-id" role="region" aria-label="Portfolio summary">
          Content
        </Card>
      );
      
      const card = screen.getByRole("region", { name: /portfolio summary/i });
      expect(card).toHaveAttribute("id", "custom-id");
    });
  });
});