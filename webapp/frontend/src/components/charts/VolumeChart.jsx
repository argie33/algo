import React from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

export const VolumeChart = ({ data = [], width = '100%', height = 200, color = '#2ca02c', ...props }) => {
  return (
    <ResponsiveContainer width={width} height={height}>
      <BarChart data={data} {...props}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="date" />
        <YAxis />
        <Tooltip formatter={(value) => [value.toLocaleString(), 'Volume']} />
        <Bar dataKey="volume" fill={color} />
      </BarChart>
    </ResponsiveContainer>
  );
};