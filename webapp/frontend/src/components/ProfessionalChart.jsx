import {
  Box,
  Card,
  CardContent,
  Typography,
  Skeleton,
  IconButton,
  Tooltip,
} from "@mui/material";
import { Download, Fullscreen, Refresh } from "@mui/icons-material";
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  ComposedChart,
  Tooltip as RechartsTooltip,
} from "recharts";
import { format } from "date-fns";

const CHART_COLORS = {
  primary: "#1976d2",
  secondary: "#dc004e",
  success: "#4caf50",
  warning: "#ff9800",
  error: "#f44336",
  info: "#2196f3",
  neutral: "#9e9e9e",
};

const ProfessionalChart = ({
  title,
  subtitle,
  data = [],
  type = "line",
  height = 300,
  loading = false,
  error = null,
  _showLegend = true,
  showGrid = true,
  showTooltip = true,
  color = "primary",
  dataKey = "value",
  xAxisDataKey = "date",
  yAxisDomain = ["auto", "auto"],
  formatYAxis = (value) => value,
  formatTooltip = (value) => value,
  actions = [],
  onRefresh,
  onDownload,
  onFullscreen,
  className,
  ...props
}) => {
  const renderChart = () => {
    if (loading) {
      return (
        <Box
          sx={{
            height,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Skeleton variant="rectangular" width="100%" height={height - 60} />
        </Box>
      );
    }

    if (error) {
      return (
        <Box
          sx={{
            height,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Typography color="error" variant="body2">
            {error}
          </Typography>
        </Box>
      );
    }

    if (!data || data.length === 0) {
      return (
        <Box
          sx={{
            height,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Typography color="text.secondary" variant="body2">
            No data available
          </Typography>
        </Box>
      );
    }

    const chartColor = CHART_COLORS[color] || color;

    switch (type) {
      case "area":
        return (
          <ResponsiveContainer width="100%" height={height - 60}>
            <AreaChart
              data={data}
              margin={{ top: 10, right: 30, left: 0, bottom: 0 }}
            >
              {showGrid && (
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              )}
              <XAxis
                dataKey={xAxisDataKey}
                tick={{ fontSize: 12 }}
                tickFormatter={(value) => {
                  if (typeof value === "string" && value.includes("-")) {
                    return format(new Date(value), "MMM dd");
                  }
                  return value;
                }}
              />
              <YAxis
                tick={{ fontSize: 12 }}
                domain={yAxisDomain}
                tickFormatter={formatYAxis}
              />
              {showTooltip && (
                <RechartsTooltip
                  formatter={formatTooltip}
                  labelFormatter={(label) => {
                    if (typeof label === "string" && label.includes("-")) {
                      return format(new Date(label), "MMM dd, yyyy");
                    }
                    return label;
                  }}
                  contentStyle={{
                    backgroundColor: "rgba(255, 255, 255, 0.95)",
                    border: "1px solid #e0e0e0",
                    borderRadius: "8px",
                    boxShadow: "0 4px 12px rgba(0,0,0,0.1)",
                  }}
                />
              )}
              <Area
                type="monotone"
                dataKey={dataKey}
                stroke={chartColor}
                fill={chartColor + "20"}
                strokeWidth={2}
              />
            </AreaChart>
          </ResponsiveContainer>
        );

      case "bar":
        return (
          <ResponsiveContainer width="100%" height={height - 60}>
            <BarChart
              data={data}
              margin={{ top: 10, right: 30, left: 0, bottom: 0 }}
            >
              {showGrid && (
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              )}
              <XAxis
                dataKey={xAxisDataKey}
                tick={{ fontSize: 12 }}
                tickFormatter={(value) => {
                  if (typeof value === "string" && value.includes("-")) {
                    return format(new Date(value), "MMM dd");
                  }
                  return value;
                }}
              />
              <YAxis
                tick={{ fontSize: 12 }}
                domain={yAxisDomain}
                tickFormatter={formatYAxis}
              />
              {showTooltip && (
                <RechartsTooltip
                  formatter={formatTooltip}
                  labelFormatter={(label) => {
                    if (typeof label === "string" && label.includes("-")) {
                      return format(new Date(label), "MMM dd, yyyy");
                    }
                    return label;
                  }}
                  contentStyle={{
                    backgroundColor: "rgba(255, 255, 255, 0.95)",
                    border: "1px solid #e0e0e0",
                    borderRadius: "8px",
                    boxShadow: "0 4px 12px rgba(0,0,0,0.1)",
                  }}
                />
              )}
              <Bar dataKey={dataKey} fill={chartColor} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        );

      case "pie":
        return (
          <ResponsiveContainer width="100%" height={height - 60}>
            <PieChart>
              <Pie
                data={data}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={({ name, percent }) =>
                  `${name} ${(percent * 100).toFixed(0)}%`
                }
                outerRadius={80}
                fill="#8884d8"
                dataKey={dataKey}
              >
                {data.map((entry, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={entry.color || CHART_COLORS.primary}
                  />
                ))}
              </Pie>
              {showTooltip && (
                <RechartsTooltip
                  formatter={formatTooltip}
                  contentStyle={{
                    backgroundColor: "rgba(255, 255, 255, 0.95)",
                    border: "1px solid #e0e0e0",
                    borderRadius: "8px",
                    boxShadow: "0 4px 12px rgba(0,0,0,0.1)",
                  }}
                />
              )}
            </PieChart>
          </ResponsiveContainer>
        );

      case "composed":
        return (
          <ResponsiveContainer width="100%" height={height - 60}>
            <ComposedChart
              data={data}
              margin={{ top: 10, right: 30, left: 0, bottom: 0 }}
            >
              {showGrid && (
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              )}
              <XAxis
                dataKey={xAxisDataKey}
                tick={{ fontSize: 12 }}
                tickFormatter={(value) => {
                  if (typeof value === "string" && value.includes("-")) {
                    return format(new Date(value), "MMM dd");
                  }
                  return value;
                }}
              />
              <YAxis
                tick={{ fontSize: 12 }}
                domain={yAxisDomain}
                tickFormatter={formatYAxis}
              />
              {showTooltip && (
                <RechartsTooltip
                  formatter={formatTooltip}
                  labelFormatter={(label) => {
                    if (typeof label === "string" && label.includes("-")) {
                      return format(new Date(label), "MMM dd, yyyy");
                    }
                    return label;
                  }}
                  contentStyle={{
                    backgroundColor: "rgba(255, 255, 255, 0.95)",
                    border: "1px solid #e0e0e0",
                    borderRadius: "8px",
                    boxShadow: "0 4px 12px rgba(0,0,0,0.1)",
                  }}
                />
              )}
              <Bar dataKey="volume" fill="#8884d8" opacity={0.3} />
              <Line
                type="monotone"
                dataKey={dataKey}
                stroke={chartColor}
                strokeWidth={2}
              />
            </ComposedChart>
          </ResponsiveContainer>
        );

      default: // line chart
        return (
          <ResponsiveContainer width="100%" height={height - 60}>
            <LineChart
              data={data}
              margin={{ top: 10, right: 30, left: 0, bottom: 0 }}
            >
              {showGrid && (
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              )}
              <XAxis
                dataKey={xAxisDataKey}
                tick={{ fontSize: 12 }}
                tickFormatter={(value) => {
                  if (typeof value === "string" && value.includes("-")) {
                    return format(new Date(value), "MMM dd");
                  }
                  return value;
                }}
              />
              <YAxis
                tick={{ fontSize: 12 }}
                domain={yAxisDomain}
                tickFormatter={formatYAxis}
              />
              {showTooltip && (
                <RechartsTooltip
                  formatter={formatTooltip}
                  labelFormatter={(label) => {
                    if (typeof label === "string" && label.includes("-")) {
                      return format(new Date(label), "MMM dd, yyyy");
                    }
                    return label;
                  }}
                  contentStyle={{
                    backgroundColor: "rgba(255, 255, 255, 0.95)",
                    border: "1px solid #e0e0e0",
                    borderRadius: "8px",
                    boxShadow: "0 4px 12px rgba(0,0,0,0.1)",
                  }}
                />
              )}
              <Line
                type="monotone"
                dataKey={dataKey}
                stroke={chartColor}
                strokeWidth={2}
                dot={false}
                activeDot={{
                  r: 4,
                  stroke: chartColor,
                  strokeWidth: 2,
                  fill: "#fff",
                }}
              />
            </LineChart>
          </ResponsiveContainer>
        );
    }
  };

  return (
    <Card elevation={2} className={className} {...props}>
      <CardContent>
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            mb: 2,
          }}
        >
          <Box>
            <Typography variant="h6" gutterBottom sx={{ fontWeight: 600 }}>
              {title}
            </Typography>
            {subtitle && (
              <Typography variant="body2" color="text.secondary">
                {subtitle}
              </Typography>
            )}
          </Box>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            {onRefresh && (
              <Tooltip title="Refresh">
                <IconButton size="small" onClick={onRefresh}>
                  <Refresh fontSize="small" />
                </IconButton>
              </Tooltip>
            )}
            {onDownload && (
              <Tooltip title="Download">
                <IconButton size="small" onClick={onDownload}>
                  <Download fontSize="small" />
                </IconButton>
              </Tooltip>
            )}
            {onFullscreen && (
              <Tooltip title="Fullscreen">
                <IconButton size="small" onClick={onFullscreen}>
                  <Fullscreen fontSize="small" />
                </IconButton>
              </Tooltip>
            )}
            {actions.map((action, index) => (
              <Tooltip key={index} title={action.tooltip}>
                <IconButton size="small" onClick={action.onClick}>
                  {action.icon}
                </IconButton>
              </Tooltip>
            ))}
          </Box>
        </Box>
        {renderChart()}
      </CardContent>
    </Card>
  );
};

export default ProfessionalChart;
