import React from "react";
import {
  Box,
  Container,
  Typography,
  Button,
  Grid,
  useTheme,
  alpha,
} from "@mui/material";
import { useNavigate } from "react-router-dom";
import {
  ArrowForward as ArrowForwardIcon,
  TrendingUp as TrendingUpIcon,
  TrendingDown as TrendingDownIcon,
} from "@mui/icons-material";

const MOCK_SIGNALS = [
  {
    ticker: "NVDA",
    name: "NVIDIA Corp",
    score: 94,
    change: "+4.2%",
    positive: true,
    signal: "BUY",
  },
  {
    ticker: "META",
    name: "Meta Platforms",
    score: 87,
    change: "+2.1%",
    positive: true,
    signal: "BUY",
  },
  {
    ticker: "CRWD",
    name: "CrowdStrike Hldg",
    score: 82,
    change: "+1.8%",
    positive: true,
    signal: "BUY",
  },
  {
    ticker: "AAPL",
    name: "Apple Inc",
    score: 76,
    change: "+0.9%",
    positive: true,
    signal: "WATCH",
  },
  {
    ticker: "BA",
    name: "Boeing Co",
    score: 28,
    change: "-2.4%",
    positive: false,
    signal: "AVOID",
  },
];

const HeroSection = () => {
  const navigate = useNavigate();
  const theme = useTheme();

  const stats = [
    { value: "5,300+", label: "Stocks Covered" },
    { value: "10+", label: "Years of Data" },
    { value: "Daily", label: "Research Updates" },
    { value: "Free", label: "Platform Access" },
  ];

  const signalColor = (signal) =>
    signal === "BUY"
      ? "#22c55e"
      : signal === "WATCH"
        ? theme.palette.primary.main
        : "#ef4444";

  return (
    <Box
      sx={{
        position: "relative",
        overflow: "hidden",
        py: { xs: 10, sm: 12, md: 14 },
        borderBottom: `1px solid ${theme.palette.divider}`,
        backgroundImage: `url('https://images.unsplash.com/photo-1518391846015-55a9cc003b25?w=1600&h=900&fit=crop&auto=format&q=80')`,
        backgroundSize: "cover",
        backgroundPosition: "center",
        "&::before": {
          content: '""',
          position: "absolute",
          inset: 0,
          background: `linear-gradient(110deg,
            ${alpha(theme.palette.background.default, 0.98)} 0%,
            ${alpha(theme.palette.background.default, 0.93)} 42%,
            ${alpha(theme.palette.background.default, 0.65)} 68%,
            ${alpha(theme.palette.background.default, 0.35)} 100%)`,
          zIndex: 1,
        },
      }}
    >
      <Container maxWidth="xl" sx={{ position: "relative", zIndex: 2 }}>
        <Grid container spacing={{ xs: 4, md: 6 }} alignItems="center">
          {/* Left: Copy */}
          <Grid item xs={12} md={7}>
            <Box>
              <Typography
                variant="overline"
                sx={{
                  fontSize: "0.75rem",
                  fontWeight: 700,
                  letterSpacing: "3px",
                  color: theme.palette.primary.main,
                  display: "block",
                  mb: 2,
                }}
              >
                Independent Equity Research &mdash; Always Free
              </Typography>

              <Typography
                variant="h1"
                component="h1"
                sx={{
                  fontWeight: 900,
                  fontSize: { xs: "2.4rem", sm: "3.4rem", md: "4.2rem" },
                  lineHeight: 1.08,
                  mb: 3,
                  color: theme.palette.text.primary,
                  letterSpacing: "-1px",
                }}
              >
                Institutional Research.
                <Box
                  component="span"
                  sx={{
                    display: "block",
                    color: theme.palette.primary.main,
                  }}
                >
                  No Subscription Required.
                </Box>
              </Typography>

              <Typography
                variant="body1"
                sx={{
                  fontSize: { xs: "1.05rem", md: "1.15rem" },
                  color: theme.palette.text.secondary,
                  mb: 2,
                  lineHeight: 1.8,
                  maxWidth: "560px",
                  fontWeight: 500,
                }}
              >
                Wall Street runs systematic equity research on 5,300+ stocks
                every day. Now you do too&mdash;for free.
              </Typography>

              <Typography
                variant="body1"
                sx={{
                  fontSize: { xs: "0.95rem", md: "1.05rem" },
                  color: theme.palette.text.secondary,
                  mb: 5,
                  lineHeight: 1.8,
                  maxWidth: "540px",
                }}
              >
                Bullseye delivers quantitative scoring, Minervini trend signals,
                earnings analysis, sector rotation, and market health
                monitoring&mdash;the same research infrastructure institutional
                desks pay millions for.
              </Typography>

              <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap", mb: 6 }}>
                <Button
                  variant="contained"
                  size="large"
                  endIcon={<ArrowForwardIcon />}
                  onClick={() => navigate("/app/markets")}
                  sx={{
                    fontSize: "1rem",
                    fontWeight: 700,
                    py: 1.75,
                    px: 4,
                    borderRadius: "0px",
                    textTransform: "none",
                    boxShadow: `0 4px 16px ${alpha(theme.palette.primary.main, 0.35)}`,
                    "&:hover": {
                      boxShadow: `0 6px 24px ${alpha(theme.palette.primary.main, 0.5)}`,
                    },
                  }}
                >
                  Launch Platform
                </Button>
                <Button
                  variant="outlined"
                  size="large"
                  onClick={() => navigate("/research-insights")}
                  sx={{
                    fontSize: "1rem",
                    fontWeight: 600,
                    py: 1.75,
                    px: 4,
                    borderRadius: "0px",
                    textTransform: "none",
                    borderColor: alpha(theme.palette.primary.main, 0.5),
                    "&:hover": {
                      backgroundColor: alpha(theme.palette.primary.main, 0.05),
                      borderColor: theme.palette.primary.main,
                    },
                  }}
                >
                  How It Works
                </Button>
              </Box>

              {/* Stats Row */}
              <Box
                sx={{
                  display: "flex",
                  gap: { xs: 3, sm: 5 },
                  flexWrap: "wrap",
                  pt: 4,
                  borderTop: `1px solid ${theme.palette.divider}`,
                }}
              >
                {stats.map((stat) => (
                  <Box key={stat.label}>
                    <Typography
                      sx={{
                        fontSize: { xs: "1.5rem", md: "1.8rem" },
                        fontWeight: 800,
                        color: theme.palette.primary.main,
                        lineHeight: 1,
                      }}
                    >
                      {stat.value}
                    </Typography>
                    <Typography
                      sx={{
                        fontSize: "0.8rem",
                        color: theme.palette.text.secondary,
                        fontWeight: 500,
                        mt: 0.5,
                        textTransform: "uppercase",
                        letterSpacing: "0.5px",
                      }}
                    >
                      {stat.label}
                    </Typography>
                  </Box>
                ))}
              </Box>
            </Box>
          </Grid>

          {/* Right: Live Dashboard Preview */}
          <Grid
            item
            xs={12}
            md={5}
            sx={{
              display: { xs: "none", md: "flex" },
              justifyContent: "flex-end",
              alignItems: "center",
            }}
          >
            <Box
              sx={{
                width: "100%",
                maxWidth: 390,
                backgroundColor: alpha(theme.palette.background.paper, 0.95),
                border: `1px solid ${alpha(theme.palette.primary.main, 0.2)}`,
                boxShadow: `0 24px 64px ${alpha("#000", 0.45)}, 0 0 0 1px ${alpha(theme.palette.primary.main, 0.08)}`,
                overflow: "hidden",
              }}
            >
              {/* Panel header */}
              <Box
                sx={{
                  px: 2.5,
                  py: 1.5,
                  backgroundColor: alpha(theme.palette.primary.main, 0.07),
                  borderBottom: `1px solid ${theme.palette.divider}`,
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                }}
              >
                <Typography
                  sx={{
                    fontSize: "0.68rem",
                    fontWeight: 800,
                    letterSpacing: "2.5px",
                    color: theme.palette.primary.main,
                    textTransform: "uppercase",
                  }}
                >
                  Live Signals Today
                </Typography>
                <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
                  <Box
                    sx={{
                      width: 7,
                      height: 7,
                      borderRadius: "50%",
                      backgroundColor: "#22c55e",
                      boxShadow: "0 0 6px #22c55e",
                    }}
                  />
                  <Typography
                    sx={{
                      fontSize: "0.62rem",
                      color: "#22c55e",
                      fontWeight: 700,
                      letterSpacing: "1px",
                    }}
                  >
                    LIVE
                  </Typography>
                </Box>
              </Box>

              {/* Signal rows */}
              {MOCK_SIGNALS.map((row) => (
                <Box
                  key={row.ticker}
                  sx={{
                    px: 2.5,
                    py: 1.4,
                    borderBottom: `1px solid ${alpha(theme.palette.divider, 0.5)}`,
                    display: "flex",
                    alignItems: "center",
                    gap: 1.5,
                  }}
                >
                  {/* Ticker badge */}
                  <Box
                    sx={{
                      width: 36,
                      height: 36,
                      flexShrink: 0,
                      backgroundColor: alpha(theme.palette.primary.main, 0.1),
                      border: `1px solid ${alpha(theme.palette.primary.main, 0.2)}`,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontSize: "0.6rem",
                      fontWeight: 900,
                      color: theme.palette.primary.main,
                      fontFamily: "monospace",
                      letterSpacing: "0.5px",
                    }}
                  >
                    {row.ticker}
                  </Box>

                  {/* Name */}
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Typography
                      sx={{
                        fontSize: "0.85rem",
                        fontWeight: 700,
                        color: theme.palette.text.primary,
                        lineHeight: 1.1,
                      }}
                    >
                      {row.ticker}
                    </Typography>
                    <Typography
                      sx={{
                        fontSize: "0.68rem",
                        color: theme.palette.text.secondary,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {row.name}
                    </Typography>
                  </Box>

                  {/* Signal + change */}
                  <Box sx={{ textAlign: "right", flexShrink: 0 }}>
                    <Box
                      sx={{
                        fontSize: "0.65rem",
                        fontWeight: 800,
                        px: 0.85,
                        py: 0.25,
                        mb: 0.4,
                        backgroundColor: alpha(signalColor(row.signal), 0.12),
                        color: signalColor(row.signal),
                        display: "inline-block",
                        letterSpacing: "0.5px",
                      }}
                    >
                      {row.signal}
                    </Box>
                    <Box
                      sx={{
                        display: "flex",
                        alignItems: "center",
                        gap: 0.4,
                        justifyContent: "flex-end",
                      }}
                    >
                      {row.positive ? (
                        <TrendingUpIcon
                          sx={{ fontSize: "0.75rem", color: "#22c55e" }}
                        />
                      ) : (
                        <TrendingDownIcon
                          sx={{ fontSize: "0.75rem", color: "#ef4444" }}
                        />
                      )}
                      <Typography
                        sx={{
                          fontSize: "0.7rem",
                          color: row.positive ? "#22c55e" : "#ef4444",
                          fontWeight: 700,
                        }}
                      >
                        {row.change}
                      </Typography>
                      <Typography
                        sx={{
                          fontSize: "0.62rem",
                          color: theme.palette.text.secondary,
                        }}
                      >
                        &bull; {row.score}
                      </Typography>
                    </Box>
                  </Box>
                </Box>
              ))}

              {/* Footer summary bar */}
              <Box
                sx={{
                  px: 2.5,
                  py: 1.5,
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  backgroundColor: alpha(theme.palette.background.default, 0.6),
                }}
              >
                <Box sx={{ textAlign: "center" }}>
                  <Typography
                    sx={{
                      fontSize: "1.15rem",
                      fontWeight: 900,
                      color: "#22c55e",
                      lineHeight: 1,
                    }}
                  >
                    8
                  </Typography>
                  <Typography
                    sx={{
                      fontSize: "0.58rem",
                      color: theme.palette.text.secondary,
                      textTransform: "uppercase",
                      letterSpacing: "0.5px",
                      mt: 0.25,
                    }}
                  >
                    Buy Signals
                  </Typography>
                </Box>
                <Box
                  sx={{
                    width: 1,
                    height: 28,
                    backgroundColor: theme.palette.divider,
                  }}
                />
                <Box sx={{ textAlign: "center" }}>
                  <Typography
                    sx={{
                      fontSize: "1.15rem",
                      fontWeight: 900,
                      color: theme.palette.text.primary,
                      lineHeight: 1,
                    }}
                  >
                    5,312
                  </Typography>
                  <Typography
                    sx={{
                      fontSize: "0.58rem",
                      color: theme.palette.text.secondary,
                      textTransform: "uppercase",
                      letterSpacing: "0.5px",
                      mt: 0.25,
                    }}
                  >
                    Stocks Scored
                  </Typography>
                </Box>
                <Box
                  sx={{
                    width: 1,
                    height: 28,
                    backgroundColor: theme.palette.divider,
                  }}
                />
                <Box sx={{ textAlign: "center" }}>
                  <Typography
                    sx={{
                      fontSize: "0.85rem",
                      fontWeight: 900,
                      color: "#22c55e",
                      lineHeight: 1,
                    }}
                  >
                    HEALTHY
                  </Typography>
                  <Typography
                    sx={{
                      fontSize: "0.58rem",
                      color: theme.palette.text.secondary,
                      textTransform: "uppercase",
                      letterSpacing: "0.5px",
                      mt: 0.25,
                    }}
                  >
                    Market Status
                  </Typography>
                </Box>
              </Box>
            </Box>
          </Grid>
        </Grid>
      </Container>
    </Box>
  );
};

export default HeroSection;
