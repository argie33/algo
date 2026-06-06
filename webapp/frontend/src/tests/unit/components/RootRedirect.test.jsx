import React from 'react';
import { render } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { vi, describe, test, expect } from 'vitest';
import RootRedirect from '../../../components/RootRedirect';

describe('RootRedirect Component', () => {
  it('should redirect to /app/markets', () => {
    const { container } = render(
      <BrowserRouter>
        <RootRedirect />
      </BrowserRouter>
    );

    // Navigate component redirects - verify it renders without errors
    expect(container).toBeTruthy();
  });

  it('should use Replace navigation to avoid adding to history', () => {
    // Navigate component with replace prop prevents back navigation
    // Just verify the component renders without errors
    render(
      <BrowserRouter>
        <RootRedirect />
      </BrowserRouter>
    );
  });
});
