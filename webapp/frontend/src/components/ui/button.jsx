import React from "react";
import { Button as MuiButton } from "@mui/material";

export const Button = React.forwardRef(
  ({ className, variant = "contained", size = "medium", loading, ...props }, ref) => {
    const muiVariant = variant === "default" ? "contained" : variant;

    return (
      <MuiButton
        ref={ref}
        className={className}
        variant={muiVariant}
        size={size}
        disabled={loading || props.disabled}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";
