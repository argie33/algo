import React from "react";
import { Chip } from "@mui/material";

export const Badge = React.forwardRef(
  ({ className, variant = "default", children, ...props }, ref) => {
    const muiVariant = variant === "destructive" ? "filled" : "outlined";
    const color = variant === "destructive" ? "error" : "default";

    return (
      <Chip
        ref={ref}
        className={className}
        variant={muiVariant}
        color={color}
        label={children}
        size="small"
        {...props}
      />
    );
  }
);
Badge.displayName = "Badge";
