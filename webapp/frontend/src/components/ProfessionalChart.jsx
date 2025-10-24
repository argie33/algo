import {
  Box,
  Card,
  CardContent,
  IconButton,
  Skeleton,
  Tooltip,
  Typography,
  useTheme,
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
  _formatYAxis = (value) => value,
  _formatTooltip = (value) => value,
  actions = [],
  onRefresh,
  onDownload,
  onFullscreen,
  className,
  // Extract non-DOM props that shouldn't be passed to Card
  _defaultIndicators: _defaultIndicators,
  _enableDrawing: _enableDrawing,
  _saveShapes: _saveShapes,
  _realtime: _realtime,
  _enableCrosshair: _enableCrosshair,
  _priceAlerts: _priceAlerts,
  _enableAlerts: _enableAlerts,
  _onAlertCreate: _onAlertCreate,
  _onLayoutSave: _onLayoutSave,
  _enableLayoutSaving: _enableLayoutSaving,
  _lazyLoad: _lazyLoad,
  _highContrast: _highContrast,
  _symbol: _symbol,
  _interval: _interval,
  _multitimeframe: _multitimeframe,
  ...props
}) => {
  const theme = useTheme();
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

    if (!data || (data?.length || 0) === 0) {
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
                <CartesianGrid strokeDasharray="3 3" stroke={theme.palette.divider} />
              )}
              <XAxis dataKey={xAxisDataKey} tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} domain={yAxisDomain} />
              {showTooltip && <RechartsTooltip />}
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
                <CartesianGrid strokeDasharray="3 3" stroke={theme.palette.divider} />
              )}
              <XAxis dataKey={xAxisDataKey} tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} domain={yAxisDomain} />
              {showTooltip && <RechartsTooltip />}
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
                labelLine={{ stroke: "none" }}
                outerRadius={80}
                fill={theme.palette.primary.main}
                dataKey={dataKey}
              >
                {(data || []).map((entry, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={entry.color || CHART_COLORS.primary}
                  />
                ))}
              </Pie>
              {showTooltip && <RechartsTooltip />}
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
                <CartesianGrid strokeDasharray="3 3" stroke={theme.palette.divider} />
              )}
              <XAxis dataKey={xAxisDataKey} tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} domain={yAxisDomain} />
              {showTooltip && <RechartsTooltip />}
              <Bar dataKey="volume" fill={theme.palette.info.main} opacity={0.3} />
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
                <CartesianGrid strokeDasharray="3 3" stroke={theme.palette.divider} />
              )}
              <XAxis dataKey={xAxisDataKey} tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} domain={yAxisDomain} />
              {showTooltip && <RechartsTooltip />}
              <Line
                type="monotone"
                dataKey={dataKey}
                stroke={chartColor}
                strokeWidth={2}
                dot={{ r: 0 }}
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
            {(actions || []).map((action, index) => (
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
