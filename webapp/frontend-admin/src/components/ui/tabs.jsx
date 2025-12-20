import React from "react";
import { Tabs as MuiTabs, Tab, Box } from "@mui/material";

export const Tabs = React.forwardRef(
  ({ className, value = 0, onValueChange, children, ...props }, ref) => {
    const [activeTab, setActiveTab] = React.useState(value);

    const handleChange = (event, newValue) => {
      setActiveTab(newValue);
      if (onValueChange) {
        onValueChange(newValue);
      }
    };

    // Filter out ALL MUI-specific props to prevent DOM warnings
    const {
      fullWidth,
      selectionFollowsFocus,
      textColor,
      variant,
      orientation,
      indicatorColor,
      scrollButtons,
      allowScrollButtonsMobile,
      centered: _centered,
      visibleScrollbar: _visibleScrollbar,
      ScrollButtonComponent: _ScrollButtonComponent,
      TabIndicatorProps: _TabIndicatorProps,
      TabScrollButtonProps: _TabScrollButtonProps,
      action: _action,
      onChange: _onChange,
      onValueChange: _onValueChange,
      value: _value,
      defaultValue: _defaultValue,
      sx: _sx,
      component: _component,
      ...divProps
    } = props;

    // Prepare MUI-specific props for the Tabs component
    const muiTabsProps = {};
    if (fullWidth !== undefined) {
      muiTabsProps.variant = fullWidth ? "fullWidth" : "standard";
    }
    if (selectionFollowsFocus !== undefined) {
      muiTabsProps.selectionFollowsFocus = selectionFollowsFocus;
    }
    if (textColor !== undefined) {
      muiTabsProps.textColor = textColor;
    }
    if (variant !== undefined) {
      muiTabsProps.variant = variant;
    }
    if (orientation !== undefined) {
      muiTabsProps.orientation = orientation;
    }
    if (indicatorColor !== undefined) {
      muiTabsProps.indicatorColor = indicatorColor;
    }
    if (scrollButtons !== undefined) {
      muiTabsProps.scrollButtons = scrollButtons;
    }
    if (allowScrollButtonsMobile !== undefined) {
      muiTabsProps.allowScrollButtonsMobile = allowScrollButtonsMobile;
    }

    return (
      <div ref={ref} className={className} {...divProps}>
        <MuiTabs
          value={activeTab}
          onChange={handleChange}
          {...muiTabsProps}
        >
          {React.Children.map(children, (child) => {
            if (child?.type?.displayName === "TabsList") {
              return React.cloneElement(child, {
                value: activeTab,
                onChange: handleChange,
              });
            }
            return child;
          })}
        </MuiTabs>
        {React.Children.map(children, (child) => {
          if (child?.type?.displayName === "TabsContent") {
            return React.cloneElement(child, {
              value: child.props.value,
              active: activeTab === child.props.value,
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
    // Filter out all non-MUI props to prevent DOM warnings
    const {
      fullWidth,
      selectionFollowsFocus,
      textColor,
      variant,
      orientation,
      indicatorColor,
      scrollButtons,
      allowScrollButtonsMobile,
      ...cleanProps
    } = props;

    // Build MUI-specific props object
    const muiTabsProps = {};
    if (fullWidth !== undefined) {
      muiTabsProps.variant = fullWidth ? "fullWidth" : "standard";
    }
    if (selectionFollowsFocus !== undefined) {
      muiTabsProps.selectionFollowsFocus = selectionFollowsFocus;
    }
    if (textColor !== undefined) {
      muiTabsProps.textColor = textColor;
    }
    if (variant !== undefined) {
      muiTabsProps.variant = variant;
    }
    if (orientation !== undefined) {
      muiTabsProps.orientation = orientation;
    }
    if (indicatorColor !== undefined) {
      muiTabsProps.indicatorColor = indicatorColor;
    }
    if (scrollButtons !== undefined) {
      muiTabsProps.scrollButtons = scrollButtons;
    }
    if (allowScrollButtonsMobile !== undefined) {
      muiTabsProps.allowScrollButtonsMobile = allowScrollButtonsMobile;
    }

    return (
      <MuiTabs
        ref={ref}
        className={className}
        value={value}
        onChange={onChange}
        {...muiTabsProps}
        {...cleanProps}
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
    const {
      fullWidth: _fullWidth,
      selectionFollowsFocus: _selectionFollowsFocus,
      textColor: _textColor,
      ...boxProps
    } = props;

    return (
      <Box
        ref={ref}
        className={className}
        data-testid="content-box"
        style={{ display: active ? "block" : "none" }}
        {...boxProps}
      >
        {children}
      </Box>
    );
  }
);
TabsContent.displayName = "TabsContent";
