import React from 'react';
import { AreaChart as RechartsAreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

export const AreaChart = ({ data = [], width = '100%', height = 300, color = '#1f77b4', ...props }) => {
  return (
    <ResponsiveContainer width={width} height={height}>
      <RechartsAreaChart data={data} {...props}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="date" />
        <YAxis />
        <Tooltip />
        <Area type="monotone" dataKey="value" stroke={color} fill={color} fillOpacity={0.3} />
      </RechartsAreaChart>
    </ResponsiveContainer>
  );
};