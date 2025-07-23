/**
 * Button Component Unit Test
 * Tests the actual Button component in isolation
 */

import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import Button from '../../../components/ui/button';

// Mock only the MUI Button to isolate our component
vi.mock('@mui/material', () => ({
  Button: vi.fn(({ children, onClick, variant, size, ...props }) => (
    <button 
      data-testid="mui-button" 
      data-variant={variant}
      data-size={size}
      onClick={onClick} 
      {...props}
    >
      {children}
    </button>
  ))
}));

describe('Button Component', () => {
  it('renders with default props', () => {
    render(<Button>Click me</Button>);
    
    const button = screen.getByTestId('mui-button');
    expect(button).toBeInTheDocument();
    expect(button).toHaveTextContent('Click me');
    expect(button).toHaveAttribute('data-variant', 'contained');
    expect(button).toHaveAttribute('data-size', 'medium');
  });

  it('handles variant prop correctly', () => {
    render(<Button variant="outlined">Outlined Button</Button>);
    
    const button = screen.getByTestId('mui-button');
    expect(button).toHaveAttribute('data-variant', 'outlined');
  });

  it('maps default variant to contained', () => {
    render(<Button variant="default">Default Button</Button>);
    
    const button = screen.getByTestId('mui-button');
    expect(button).toHaveAttribute('data-variant', 'contained');
  });

  it('handles size prop', () => {
    render(<Button size="small">Small Button</Button>);
    
    const button = screen.getByTestId('mui-button');
    expect(button).toHaveAttribute('data-size', 'small');
  });

  it('handles click events', () => {
    const handleClick = vi.fn();
    render(<Button onClick={handleClick}>Click me</Button>);
    
    const button = screen.getByTestId('mui-button');
    fireEvent.click(button);
    
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it('forwards other props', () => {
    render(<Button disabled className="custom-class">Disabled Button</Button>);
    
    const button = screen.getByTestId('mui-button');
    expect(button).toHaveAttribute('disabled');
    expect(button).toHaveAttribute('class', 'custom-class');
  });
});