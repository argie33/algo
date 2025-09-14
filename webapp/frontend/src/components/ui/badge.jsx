import React from "react";
import { Chip } from "@mui/material";

export const Badge = React.forwardRef(
  ({ className, variant = "default", children, ...props }, ref) => {
    const muiVariant = variant === "destructive" ? "filled" : "outlined";
    const color = variant === "destructive" ? "error" : "default";
    
    // Handle edge cases for label prop
    const label = children == null ? "" : String(children);

    return (
      <Chip
        ref={ref}
        className={className}
        variant={muiVariant}
        color={color}
        label={label}
        size="small"
        {...props}
      />
    );
  }
);
Badge.displayName = "Badge";
