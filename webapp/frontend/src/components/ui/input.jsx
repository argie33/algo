import React from "react";
import { TextField } from "@mui/material";

export const Input = React.forwardRef(
  ({ 
    className, 
    type = "text", 
    invalid, 
    variant = "outlined", 
    size = "small",
    disabled,
    placeholder,
    label,
    helperText,
    debounce,
    min,
    max,
    step,
    accept,
    maxLength,
    ...props 
  }, ref) => {
    const validVariant = variant === "outline" ? "outlined" : variant;
    // Convert custom size values to MUI sizes
    const muiSize = size === "sm" ? "small" : size === "lg" ? "medium" : size;
    const [debouncedValue, setDebouncedValue] = React.useState(props.value || props.defaultValue || '');
    const inputRef = React.useRef(null);
    const debounceRef = React.useRef(null);

    // Handle debounced onChange
    const { onChange, value } = props;
    React.useEffect(() => {
      if (debounce && onChange && debounceRef.current !== debouncedValue) {
        const timer = setTimeout(() => {
          onChange({ target: { value: debouncedValue } });
          debounceRef.current = debouncedValue;
        }, debounce);
        return () => clearTimeout(timer);
      }
    }, [debouncedValue, debounce, onChange]);

    const handleChange = (e) => {
      const newValue = e.target.value;
      if (debounce) {
        setDebouncedValue(newValue);
        // Don't call onChange immediately when debouncing
        return;
      } else if (onChange) {
        onChange(e);
      }
    };

    // Forward ref to the actual input element
    React.useImperativeHandle(ref, () => {
      return inputRef.current?.querySelector('input') || inputRef.current;
    });

    // Build inputProps properly
    const inputProps = {
      'aria-describedby': helperText ? 'error-message' : undefined,
      ...(min !== undefined && { min }),
      ...(max !== undefined && { max }),
      ...(step !== undefined && { step }),
      ...(maxLength !== undefined && { maxLength }),
      ...props.inputProps
    };

    // Filter out props that shouldn't go to TextField
    const { onChange: _onChange, value: _value, defaultValue: _defaultValue, inputProps: _inputProps, ...textFieldProps } = props;
    
    return (
      <TextField
        ref={inputRef}
        className={className}
        type={type}
        variant={validVariant}
        size={muiSize}
        error={invalid}
        disabled={disabled}
        placeholder={placeholder}
        label={label}
        helperText={helperText}
        onChange={handleChange}
        value={debounce ? debouncedValue : value}
        defaultValue={!debounce && !value ? props.defaultValue : undefined}
        inputProps={inputProps}
        InputProps={{
          ...(accept && { accept }),
          ...props.InputProps
        }}
        {...textFieldProps}
      />
    );
  }
);
Input.displayName = "Input";
