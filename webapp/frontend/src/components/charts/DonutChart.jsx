import React from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';

export const DonutChart = ({ data = [], width = '100%', height = 300, innerRadius = 60, ...props }) => {
  return (
    <ResponsiveContainer width={width} height={height}>
      <PieChart {...props}>
        <Pie
          data={data}
          cx="50%"
          cy="50%"
          innerRadius={innerRadius}
          outerRadius={80}
          paddingAngle={5}
          dataKey="value"
        >
          {data.map((entry) => (
            <Cell key={entry.symbol || entry.name || entry.id} fill={entry.color || '#8884d8'} />
          ))}
        </Pie>
        <Tooltip />
      </PieChart>
    </ResponsiveContainer>
  );
};