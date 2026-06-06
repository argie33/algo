/**
 * Wrapper for Recharts ResponsiveContainer to fix width/height -1 issue
 * Ensures parent div has proper dimensions before ResponsiveContainer measures
 */
import React, { useRef, useEffect, useState } from 'react';
import { ResponsiveContainer } from 'recharts';

export const ResponsiveChartWrapper = ({
  height = 300,
  width = '100%',
  children,
  ...containerProps
}) => {
  const containerRef = useRef(null);
  const [containerWidth, setContainerWidth] = useState(null);

  useEffect(() => {
    if (!containerRef.current) return;

    // Use ResizeObserver to track container width changes
    const observer = new ResizeObserver(() => {
      if (containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect();
        if (rect.width > 0) {
          setContainerWidth(rect.width);
        }
      }
    });

    observer.observe(containerRef.current);

    // Initial measurement
    const rect = containerRef.current.getBoundingClientRect();
    if (rect.width > 0) {
      setContainerWidth(rect.width);
    }

    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={containerRef}
      style={{
        height: typeof height === 'number' ? `${height}px` : height,
        width: width === '100%' ? '100%' : (typeof width === 'number' ? `${width}px` : width),
        minWidth: 0,
        overflow: 'hidden',
        display: 'flex',
        alignItems: 'stretch',
      }}
    >
      <ResponsiveContainer
        width="100%"
        height="100%"
        {...containerProps}
      >
        {children}
      </ResponsiveContainer>
    </div>
  );
};

export default ResponsiveChartWrapper;
