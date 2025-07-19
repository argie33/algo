import React from 'react';
import { LineChart as RechartsLineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

export const LineChart = ({ data = [], width = '100%', height = 300, color = '#1f77b4', showGrid = true, ...props }) => {
  return (
    <ResponsiveContainer width={width} height={height}>
      <RechartsLineChart data={data} {...props}>
        {showGrid && <CartesianGrid strokeDasharray="3 3" />}
        <XAxis dataKey="date" />
        <YAxis />
        <Tooltip />
        <Line type="monotone" dataKey="value" stroke={color} strokeWidth={2} />
      </RechartsLineChart>
    </ResponsiveContainer>
  );
};