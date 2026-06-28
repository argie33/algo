/**
 * Wrapper for Recharts ResponsiveContainer to fix width/height -1 issue
 * Ensures parent div has proper dimensions before ResponsiveContainer measures
 */
import React, { useRef, useEffect } from "react";
import { ResponsiveContainer } from "recharts";

export const ResponsiveChartWrapper = ({
  height = 300,
  width = "100%",
  children,
  className = "",
  ...containerProps
}) => {
  const containerRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current) return;

    // Trigger a resize event for Recharts to remeasure
    // This helps resolve cases where dimensions are initially 0
    const timer = setTimeout(() => {
      window.dispatchEvent(new Event("resize"));
    }, 100);

    return () => clearTimeout(timer);
  }, []);

  return (
    <div
      ref={containerRef}
      className={`chart-container ${className}`.trim()}
      style={{
        height: typeof height === "number" ? `${height}px` : height,
        width:
          width === "100%"
            ? "100%"
            : typeof width === "number"
              ? `${width}px`
              : width,
        minWidth: 0,
        minHeight: 0,
        overflow: "hidden",
        display: "flex",
        alignItems: "stretch",
      }}
    >
      <ResponsiveContainer width="100%" height="100%" {...containerProps}>
        {children}
      </ResponsiveContainer>
    </div>
  );
};

export default ResponsiveChartWrapper;
