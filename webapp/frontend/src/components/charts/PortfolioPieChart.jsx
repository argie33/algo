import React from 'react';
import { PieChart as RechartsPieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from 'recharts';

export const PortfolioPieChart = ({ data = [], width = '100%', height = 300, ...props }) => {
  return (
    <ResponsiveContainer width={width} height={height}>
      <RechartsPieChart {...props}>
        <Pie
          data={data}
          cx="50%"
          cy="50%"
          labelLine={false}
          label={({ symbol, percentage }) => `${symbol} ${percentage}%`}
          outerRadius={80}
          fill="#8884d8"
          dataKey="value"
        >
          {data.map((entry, index) => (
            <Cell key={`cell-${index}`} fill={entry.color || '#8884d8'} />
          ))}
        </Pie>
        <Tooltip formatter={(value) => [`$${value.toLocaleString()}`, 'Value']} />
        <Legend />
      </RechartsPieChart>
    </ResponsiveContainer>
  );
};