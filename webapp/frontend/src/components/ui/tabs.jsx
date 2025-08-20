import React from "react";
import { Tabs as MuiTabs, Tab, Box } from "@mui/material";

export const Tabs = React.forwardRef(
  ({ className, value: _value, onValueChange: _onValueChange, children, ...props }, ref) => {
    return (
      <div ref={ref} className={className} {...props}>
        {children}
      </div>
    );
  }
);
Tabs.displayName = "Tabs";

export const TabsList = React.forwardRef(
  ({ className, children, ...props }, ref) => (
    <MuiTabs ref={ref} className={className} {...props}>
      {children}
    </MuiTabs>
  )
);
TabsList.displayName = "TabsList";

export const TabsTrigger = React.forwardRef(
  ({ className, value: _value, children, ...props }, ref) => (
    <Tab
      ref={ref}
      className={className}
      value={_value}
      label={children}
      {...props}
    />
  )
);
TabsTrigger.displayName = "TabsTrigger";

export const TabsContent = React.forwardRef(
  ({ className, value, children, ...props }, ref) => (
    <Box ref={ref} className={className} {...props}>
      {children}
    </Box>
  )
);
TabsContent.displayName = "TabsContent";
