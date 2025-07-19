import React from 'react';
import { BarChart as RechartsBarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

export const BarChart = ({ data = [], width = '100%', height = 300, color = '#2ca02c', ...props }) => {
  return (
    <ResponsiveContainer width={width} height={height}>
      <RechartsBarChart data={data} {...props}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="name" />
        <YAxis />
        <Tooltip />
        <Bar dataKey="value" fill={color} />
      </RechartsBarChart>
    </ResponsiveContainer>
  );
};