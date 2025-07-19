import React from 'react';
import { LineChart, Line, ResponsiveContainer } from 'recharts';

export const SparklineChart = ({ data = [], width = 100, height = 50, color = '#1f77b4', ...props }) => {
  return (
    <ResponsiveContainer width={width} height={height}>
      <LineChart data={data} {...props}>
        <Line type="monotone" dataKey="value" stroke={color} strokeWidth={1} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
};