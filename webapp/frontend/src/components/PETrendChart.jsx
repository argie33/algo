import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, Typography, CircularProgress, Alert } from "@mui/material";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";
import api from "../services/api";

export default function PETrendChart({ sectorName, industryName }) {
  const name = sectorName || industryName;
  const endpoint = sectorName ? `sectors/trend/${sectorName}` : `industries/trend/${industryName}`;

  const { data, isLoading, error } = useQuery({
    queryKey: ["pe-trend", name],
    queryFn: async () => {
      // Request max available data (limited to ~752 days = ~2 years in database)
      const response = await api.get(`/api/${endpoint}?days=3650`);
      return response?.data;
    },
    enabled: !!name,
  });

  if (!name) return null;
  if (isLoading) return <CircularProgress size={30} />;
  if (error || !data?.history) {
    return <Alert severity="info">No trend data available</Alert>;
  }

  // Use actual P/E values from historical data
  const chartData = data.history.map(item => ({
    date: new Date(item.date).toLocaleDateString(),
    pe: item.trailing_pe !== null ? parseFloat(item.trailing_pe) : null
  })).filter(item => item.pe !== null);

  return (
    <Card sx={{ mt: 2 }}>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          P/E Over Time
        </Typography>

        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" angle={-45} textAnchor="end" height={60} />
            <YAxis label={{ value: "P/E Ratio", angle: -90, position: "insideLeft" }} />
            <Tooltip
              contentStyle={{ backgroundColor: "rgba(0,0,0,0.8)", border: "1px solid #666", borderRadius: 4 }}
              labelStyle={{ color: "#fff" }}
              formatter={(value) => {
                if (value === null || value === undefined) return "—";
                const num = parseFloat(value);
                return isNaN(num) ? "—" : num.toFixed(2);
              }}
              labelFormatter={(label) => label}
            />
            <Line type="monotone" dataKey="pe" stroke="#E91E63" strokeWidth={3} dot={false} name="P/E" />
          </LineChart>
        </ResponsiveContainer>

        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 2 }}>
          Higher = more expensive | Lower = cheaper
        </Typography>
      </CardContent>
    </Card>
  );
}
