import React from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';

export const PerformanceChart = ({ data = [], width = '100%', height = 300, ...props }) => {
  return (
    <ResponsiveContainer width={width} height={height}>
      <LineChart data={data} {...props}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="date" />
        <YAxis />
        <Tooltip />
        <Legend />
        <Line type="monotone" dataKey="portfolio" stroke="#1f77b4" strokeWidth={2} name="Portfolio" />
        <Line type="monotone" dataKey="benchmark" stroke="#ff7f0e" strokeWidth={2} name="Benchmark" />
      </LineChart>
    </ResponsiveContainer>
  );
};