import React from 'react';
import { ComposedChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

export const CandlestickChart = ({ data = [], width = '100%', height = 400, ...props }) => {
  return (
    <ResponsiveContainer width={width} height={height}>
      <ComposedChart data={data} {...props}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="date" />
        <YAxis />
        <Tooltip formatter={(value, name) => [`$${value}`, name]} />
        <Bar dataKey="high" fill="#00ff00" />
        <Bar dataKey="low" fill="#ff0000" />
      </ComposedChart>
    </ResponsiveContainer>
  );
};