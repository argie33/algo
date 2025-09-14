import React from "react";
import { Tabs as MuiTabs, Tab, Box } from "@mui/material";

export const Tabs = React.forwardRef(
  (
    {
      className,
      value = 0,
      onValueChange,
      children,
      ...props
    },
    ref
  ) => {
    const [activeTab, setActiveTab] = React.useState(value);

    const handleChange = (event, newValue) => {
      setActiveTab(newValue);
      if (onValueChange) {
        onValueChange(newValue);
      }
    };

    // Filter out non-DOM props
    const { fullWidth, selectionFollowsFocus, textColor, ...divProps } = props;

    return (
      <div ref={ref} className={className} {...divProps}>
        <MuiTabs 
          value={activeTab} 
          onChange={handleChange}
          {...(fullWidth !== undefined && { variant: fullWidth ? 'fullWidth' : 'standard' })}
          {...(selectionFollowsFocus !== undefined && { selectionFollowsFocus })}
          {...(textColor !== undefined && { textColor })}
        >
          {React.Children.map(children, (child) => {
            if (child?.type?.displayName === "TabsList") {
              return React.cloneElement(child, { value: activeTab, onChange: handleChange });
            }
            return child;
          })}
        </MuiTabs>
        {React.Children.map(children, (child) => {
          if (child?.type?.displayName === "TabsContent") {
            return React.cloneElement(child, { 
              value: child.props.value, 
              active: activeTab === child.props.value 
            });
          }
          return null;
        })}
      </div>
    );
  }
);
Tabs.displayName = "Tabs";

export const TabsList = React.forwardRef(
  ({ className, children, value, onChange, ...props }, ref) => {
    // Filter out non-MUI props to prevent DOM warnings
    const { fullWidth, selectionFollowsFocus, textColor, ...muiProps } = props;
    const muiTabsProps = {
      ...(fullWidth !== undefined && { variant: fullWidth ? 'fullWidth' : 'standard' }),
      ...(selectionFollowsFocus !== undefined && { selectionFollowsFocus }),
      ...(textColor !== undefined && { textColor })
    };
    
    return (
      <MuiTabs 
        ref={ref} 
        className={className} 
        value={value} 
        onChange={onChange} 
        {...muiTabsProps}
        {...muiProps}
      >
        {children}
      </MuiTabs>
    );
  }
);
TabsList.displayName = "TabsList";

export const TabsTrigger = React.forwardRef(
  ({ className, value, children, ...props }, ref) => (
    <Tab
      ref={ref}
      className={className}
      value={value}
      label={children}
      {...props}
    />
  )
);
TabsTrigger.displayName = "TabsTrigger";

export const TabsContent = React.forwardRef(
  ({ className, value: _value, children, active, ...props }, ref) => {
    // Filter out MUI-specific props to prevent DOM warnings
    const { fullWidth: _fullWidth, selectionFollowsFocus: _selectionFollowsFocus, textColor: _textColor, ...boxProps } = props;
    
    return (
      <Box 
        ref={ref} 
        className={className} 
        data-testid="content-box"
        style={{ display: active ? 'block' : 'none' }}
        {...boxProps}
      >
        {children}
      </Box>
    );
  }
);
TabsContent.displayName = "TabsContent";
