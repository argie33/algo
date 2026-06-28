import React from "react";
import { LinearProgress } from "@mui/material";

export const Progress = React.forwardRef(
  ({ className, value, ...props }, ref) => {
    // Ensure value is a number or undefined to prevent PropType warnings
    const numericValue = value !== undefined ? Number(value) || 0 : undefined;

    return (
      <LinearProgress
        ref={ref}
        className={className}
        variant={numericValue !== undefined ? "determinate" : "indeterminate"}
        value={numericValue}
        {...props}
      />
    );
  }
);
Progress.displayName = "Progress";
