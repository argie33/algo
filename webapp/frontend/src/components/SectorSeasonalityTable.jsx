import { useMemo } from "react";
import {
  Box,
  Card,
  CardContent,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
  Tooltip,
  alpha,
  useTheme,
} from "@mui/material";
import { TrendingUp, TrendingDown } from "@mui/icons-material";

const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

const MONTH_FULL_NAMES = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

const SectorSeasonalityTable = ({ data }) => {
  const theme = useTheme();

  const seasonalityData = useMemo(() => {
    if (!data || !Array.isArray(data)) return [];
    return data;
  }, [data]);

  const getMonthStatus = (sector, monthNum) => {
    if (sector.bestMonths?.includes(monthNum)) return "best";
    if (sector.worstMonths?.includes(monthNum)) return "worst";
    return "neutral";
  };

  const getMonthColor = (returnValue) => {
    const value = returnValue || 0;
    if (value > 0.5) {
      return {
        bg: alpha(theme.palette.success.main, 0.2),
        text: theme.palette.success.main,
        border: theme.palette.success.main,
      };
    } else if (value > 0) {
      return {
        bg: alpha(theme.palette.success.main, 0.1),
        text: theme.palette.success.main,
        border: theme.palette.success.main,
      };
    } else if (value < -0.5) {
      return {
        bg: alpha(theme.palette.error.main, 0.2),
        text: theme.palette.error.main,
        border: theme.palette.error.main,
      };
    } else if (value < 0) {
      return {
        bg: alpha(theme.palette.error.main, 0.1),
        text: theme.palette.error.main,
        border: theme.palette.error.main,
      };
    }
    return {
      bg: alpha(theme.palette.grey[500], 0.05),
      text: theme.palette.text.secondary,
      border: theme.palette.divider,
    };
  };

  const formatReturn = (value) => {
    if (value === undefined || value === null) return "—";
    const sign = value > 0 ? "+" : "";
    return `${sign}${value.toFixed(1)}%`;
  };

  return (
    <Card>
      <CardContent>
        <Box sx={{ mb: 3 }}>
          <Typography variant="h6" sx={{ mb: 1, fontWeight: 600 }}>
            Sector Monthly Seasonality Patterns
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Green = Best performing months | Red = Worst performing months | Gray = Neutral
          </Typography>
        </Box>

        <TableContainer sx={{ overflowX: "auto" }}>
          <Table size="small" sx={{ minWidth: 1200 }}>
            <TableHead>
              <TableRow
                sx={{
                  backgroundColor: alpha(theme.palette.primary.main, 0.1),
                  "& th": {
                    fontWeight: 700,
                    fontSize: "0.875rem",
                    color: theme.palette.text.primary,
                    padding: "12px 8px",
                    textAlign: "center",
                  },
                }}
              >
                <TableCell
                  sx={{
                    fontWeight: 700,
                    fontSize: "0.875rem",
                    textAlign: "left",
                    minWidth: "140px",
                  }}
                >
                  Sector
                </TableCell>
                {MONTHS.map((month, idx) => (
                  <TableCell
                    key={idx}
                    align="center"
                    title={MONTH_FULL_NAMES[idx]}
                    sx={{
                      fontWeight: 700,
                      fontSize: "0.8rem",
                      padding: "12px 4px",
                    }}
                  >
                    {month}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {seasonalityData.map((sector, sectorIdx) => (
                <TableRow
                  key={sectorIdx}
                  sx={{
                    "&:hover": {
                      backgroundColor: alpha(theme.palette.primary.main, 0.05),
                    },
                    borderBottom: `1px solid ${theme.palette.divider}`,
                  }}
                >
                  {/* Sector Name */}
                  <TableCell
                    sx={{
                      fontWeight: 600,
                      fontSize: "0.95rem",
                      textAlign: "left",
                      minWidth: "140px",
                      color: theme.palette.text.primary,
                    }}
                  >
                    {sector.sector}
                  </TableCell>

                  {/* Monthly Cells */}
                  {Array.from({ length: 12 }, (_, i) => i + 1).map((monthNum) => {
                    const monthlyReturn = sector.monthlyReturns?.[monthNum - 1];
                    const colors = getMonthColor(monthlyReturn);
                    const status = getMonthStatus(sector, monthNum);

                    return (
                      <Tooltip
                        key={monthNum}
                        title={`${sector.sector} in ${MONTH_FULL_NAMES[monthNum - 1]}: ${formatReturn(monthlyReturn)} avg return${
                          status === "best" ? " (Best month)" : status === "worst" ? " (Worst month)" : ""
                        }`}
                        arrow
                      >
                        <TableCell
                          align="center"
                          sx={{
                            backgroundColor: colors.bg,
                            border: `1px solid ${colors.border}`,
                            padding: "10px 4px",
                            cursor: "pointer",
                            transition: "all 0.2s ease",
                            fontSize: "0.85rem",
                            fontWeight: 600,
                            color: colors.text,
                            "&:hover": {
                              transform: "scale(1.12)",
                              boxShadow: `0 0 0 2px ${colors.text}`,
                              zIndex: 1,
                              backgroundColor: alpha(colors.text, 0.15),
                            },
                            userSelect: "none",
                          }}
                        >
                          {formatReturn(monthlyReturn)}
                        </TableCell>
                      </Tooltip>
                    );
                  })}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>

        {/* Summary Statistics */}
        {seasonalityData.length > 0 && (
          <Box sx={{ mt: 3, pt: 2, borderTop: `1px solid ${theme.palette.divider}` }}>
            <Typography variant="subtitle2" sx={{ mb: 2, fontWeight: 600 }}>
              Summary by Sector
            </Typography>
            <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(250px, 1fr))", gap: 2 }}>
              {seasonalityData.map((sector, idx) => (
                <Box
                  key={idx}
                  sx={{
                    p: 1.5,
                    backgroundColor: alpha(theme.palette.primary.main, 0.05),
                    borderRadius: 1,
                    border: `1px solid ${theme.palette.divider}`,
                  }}
                >
                  <Typography variant="body2" sx={{ fontWeight: 600, mb: 1 }}>
                    {sector.sector}
                  </Typography>
                  <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", mb: 1 }}>
                    <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                      <TrendingUp sx={{ fontSize: "1rem", color: theme.palette.success.main }} />
                      <Typography variant="caption" sx={{ fontWeight: 500 }}>
                        {sector.bestMonths?.length || 0} best
                      </Typography>
                    </Box>
                    <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                      <TrendingDown sx={{ fontSize: "1rem", color: theme.palette.error.main }} />
                      <Typography variant="caption" sx={{ fontWeight: 500 }}>
                        {sector.worstMonths?.length || 0} worst
                      </Typography>
                    </Box>
                  </Box>
                  {sector.rationale && (
                    <Typography variant="caption" color="text.secondary" sx={{ display: "block", fontSize: "0.75rem" }}>
                      {sector.rationale}
                    </Typography>
                  )}
                </Box>
              ))}
            </Box>
          </Box>
        )}
      </CardContent>
    </Card>
  );
};

export default SectorSeasonalityTable;
