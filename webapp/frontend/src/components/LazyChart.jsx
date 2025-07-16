import React, { Suspense, lazy } from 'react';
import { CircularProgress, Box } from '@mui/material';

const ChartLoader = ({ height = 200 }) => (
  <Box 
    sx={{ 
      display: 'flex', 
      justifyContent: 'center', 
      alignItems: 'center', 
      height: height,
      backgroundColor: 'grey.50',
      borderRadius: 1
    }}
  >
    <CircularProgress size={24} />
  </Box>
);

// This is a completely wrong approach - just export normal recharts for now
export {
  LineChart,
  AreaChart, 
  BarChart,
  PieChart,
  Line,
  Area,
  Bar,
  Pie,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell
} from 'recharts';

export default ChartLoader;