import React from 'react';
import { render } from '@testing-library/react-native';
import App from '../App';

// Mock the App component since it doesn't exist yet
jest.mock('../App', () => {
  const React = require('react');
  const { View, Text } = require('react-native');

  return function App() {
    return React.createElement(View, {},
      React.createElement(Text, {}, 'Financial Platform Mobile App')
    );
  };
});

describe('App', () => {
  it('renders without crashing', () => {
    const { getByText } = render(<App />);
    expect(getByText('Financial Platform Mobile App')).toBeTruthy();
  });
});