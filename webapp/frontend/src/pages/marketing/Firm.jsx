import React from "react";
import {
  Container,
  Box,
  Typography,
  Grid,
  Card,
  CardContent,
  useTheme,
  alpha,
} from "@mui/material";
import { useNavigate } from "react-router-dom";
import MarketingLayout from "../../components/marketing/MarketingLayout";
import PageHeader from "../../components/marketing/PageHeader";
import CTASection from "../../components/marketing/CTASection";
import ImagePlaceholder from "../../components/marketing/ImagePlaceholder";
import {
  Flag as FlagIcon,
  Lightbulb as LightbulbIcon,
  Groups as GroupsIcon,
  TrendingUp as TrendingUpIcon,
  Handshake as _HandshakeIcon,
} from "@mui/icons-material";

const Firm = () => {
  const theme = useTheme();
  const navigate = useNavigate();

  const expertise = [
    {
      icon: <FlagIcon />,
      title: "Independent Research",
      description:
        "We operate without investment banking relationships or sell-side conflicts. Our research is driven purely by data and analysis&#8212;no pressure to maintain ratings, no underwriting agenda. Just the facts.",
    },
    {
      icon: <LightbulbIcon />,
      title: "Quantitative & Fundamental Analysis",
      description:
        "Research combining Minervini trend template analysis with fundamental quality filters. Multi-factor scoring across momentum, value, earnings quality, and technical structure&#8212;all backtested against 10+ years of market data.",
    },
    {
      icon: <GroupsIcon />,
      title: "Comprehensive Market Coverage",
      description:
        "Research coverage across 5,300+ US equities with 10+ years of historical data. Earnings, sector trends, economic indicators, and market technicals&#8212;the full picture in one platform.",
    },
    {
      icon: <TrendingUpIcon />,
      title: "Evidence-Based Methodology",
      description:
        "All research models are backtested against historical data and validated for statistical significance. We explain the methodology transparently and show the factors driving our analysis.",
    },
  ];

  const philosophy = [
    {
      principle: "Quantitative Rigor",
      description:
        "All factor models are backtested against 10+ years of historical data. We validate statistical significance and measure out-of-sample performance before deploying any model in production.",
    },
    {
      principle: "Fundamental Analysis",
      description:
        "We evaluate companies using earnings growth, revenue acceleration, profit margins, and financial strength. Technical analysis alone is insufficient&#8212;fundamentals remain the foundation of sustainable moves.",
    },
    {
      principle: "Research Independence",
      description:
        "Bullseye maintains complete research independence. We have no investment banking relationships, no underwriting business, and no conflicts that compromise our analytical objectivity.",
    },
    {
      principle: "Transparent Methodology",
      description:
        "We explain our research process and show the factors driving our analysis. You understand exactly what metrics we evaluate and why certain stocks score positively or negatively.",
    },
    {
      principle: "Comprehensive Coverage",
      description:
        "Our research universe covers 5,300+ US equities across all market capitalizations and sectors. The breadth needed for portfolio construction and relative value analysis.",
    },
    {
      principle: "Continuous Validation",
      description:
        "Research models are continuously monitored and validated. We track performance, refine models based on changing market conditions, and adapt as evidence dictates.",
    },
  ];

  return (
    <MarketingLayout>
      <PageHeader
        title="The Firm"
        subtitle="Independent equity research delivering systematic, evidence-based analysis to every serious investor"
      />

      {/* Who We Are */}
      <Box
        sx={{
          py: { xs: 8, md: 10 },
          backgroundColor: theme.palette.background.default,
        }}
      >
        <Container maxWidth="lg">
          <Grid container spacing={7} alignItems="center">
            <Grid item xs={12} md={6}>
              <Typography
                variant="overline"
                sx={{
                  color: theme.palette.primary.main,
                  fontWeight: 700,
                  letterSpacing: "3px",
                  display: "block",
                  mb: 1.5,
                }}
              >
                Who We Are
              </Typography>
              <Typography
                variant="h3"
                sx={{
                  fontSize: { xs: "2rem", sm: "2.5rem", md: "3rem" },
                  fontWeight: 800,
                  mb: 3,
                  color: theme.palette.text.primary,
                  letterSpacing: "-0.5px",
                  lineHeight: 1.2,
                }}
              >
                Built by Investors, for Investors
              </Typography>
              <Typography
                sx={{
                  fontSize: "1.05rem",
                  color: theme.palette.text.secondary,
                  mb: 3,
                  lineHeight: 1.8,
                }}
              >
                Bullseye Financial is an independent research firm providing
                comprehensive equity analysis to institutional investors,
                registered investment advisors, and active traders. We publish
                research combining quantitative models, fundamental analysis,
                and technical insights across 5,300+ US equities.
              </Typography>
              <Typography
                sx={{
                  fontSize: "1.05rem",
                  color: theme.palette.text.secondary,
                  lineHeight: 1.8,
                }}
              >
                Our research covers earnings analysis, sector rotation, economic
                trends, and multi-factor stock scoring. We maintain research
                independence without investment banking conflicts&#8212;allowing
                us to publish unbiased analysis focused solely on investment
                merit.
              </Typography>
            </Grid>
            <Grid item xs={12} md={6}>
              <ImagePlaceholder
                src="https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=900&h=650&fit=crop&auto=format&q=80"
                alt="Financial data and market analysis"
                height={{ xs: "280px", md: "400px" }}
              />
            </Grid>
          </Grid>
        </Container>
      </Box>

      {/* Mission Statement */}
      <Box
        sx={{
          py: { xs: 8, md: 10 },
          background: `linear-gradient(135deg, ${theme.palette.primary.main} 0%, ${alpha(theme.palette.primary.main, 0.8)} 100%)`,
        }}
      >
        <Container maxWidth="md">
          <Typography
            variant="overline"
            sx={{
              color: alpha("#fff", 0.7),
              fontWeight: 700,
              letterSpacing: "3px",
              display: "block",
              mb: 2,
              textAlign: "center",
            }}
          >
            Our Mission
          </Typography>
          <Typography
            variant="h3"
            sx={{
              fontSize: { xs: "1.8rem", md: "2.4rem" },
              fontWeight: 800,
              color: "#fff",
              textAlign: "center",
              mb: 3,
              lineHeight: 1.3,
            }}
          >
            Democratize Institutional-Grade Research
          </Typography>
          <Typography
            sx={{
              fontSize: "1.1rem",
              color: alpha("#fff", 0.85),
              textAlign: "center",
              lineHeight: 1.8,
              mb: 2,
            }}
          >
            To combine rigorous quantitative analysis, fundamental insights, and
            technical expertise into a comprehensive research platform
            accessible to every serious investor&#8212;not just those who can
            afford a Bloomberg terminal or institutional research desk.
          </Typography>
          <Typography
            sx={{
              fontSize: "1rem",
              color: alpha("#fff", 0.7),
              textAlign: "center",
              lineHeight: 1.8,
              fontStyle: "italic",
            }}
          >
            Independent research drives better investment decisions. By removing
            conflicts of interest and publishing transparent, evidence-based
            analysis, we empower investors to make decisions based on
            data&#8212;not Wall Street relationships.
          </Typography>
        </Container>
      </Box>

      {/* Research Expertise */}
      <Box
        sx={{
          py: { xs: 8, md: 10 },
          backgroundColor: theme.palette.background.paper,
        }}
      >
        <Container maxWidth="lg">
          <Box sx={{ textAlign: "center", mb: 7 }}>
            <Typography
              variant="overline"
              sx={{
                color: theme.palette.primary.main,
                fontWeight: 700,
                letterSpacing: "3px",
                display: "block",
                mb: 1.5,
              }}
            >
              Research Expertise
            </Typography>
            <Typography
              variant="h3"
              sx={{
                fontSize: { xs: "1.9rem", sm: "2.3rem", md: "2.8rem" },
                fontWeight: 800,
                mb: 2,
                color: theme.palette.text.primary,
                letterSpacing: "-0.5px",
              }}
            >
              What We Do Best
            </Typography>
          </Box>
          <Grid container spacing={4}>
            {expertise.map((item, idx) => (
              <Grid item xs={12} sm={6} key={idx}>
                <Card
                  sx={{
                    height: "100%",
                    border: `1px solid ${theme.palette.divider}`,
                    backgroundColor: theme.palette.background.default,
                    borderRadius: "0px",
                    boxShadow: "none",
                    transition: "all 0.25s ease",
                    "&:hover": {
                      boxShadow: "0 4px 16px rgba(0,0,0,0.07)",
                      borderColor: theme.palette.primary.main,
                    },
                  }}
                >
                  <CardContent sx={{ p: 3.5 }}>
                    <Box
                      sx={{
                        width: 44,
                        height: 44,
                        borderRadius: "0px",
                        backgroundColor: alpha(theme.palette.primary.main, 0.1),
                        color: theme.palette.primary.main,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        mb: 2.5,
                        border: `1px solid ${alpha(theme.palette.primary.main, 0.2)}`,
                      }}
                    >
                      {item.icon}
                    </Box>
                    <Typography
                      variant="h6"
                      sx={{
                        fontWeight: 700,
                        mb: 1.5,
                        color: theme.palette.text.primary,
                        fontSize: "1.05rem",
                      }}
                    >
                      {item.title}
                    </Typography>
                    <Typography
                      variant="body2"
                      sx={{
                        color: theme.palette.text.secondary,
                        lineHeight: 1.7,
                      }}
                      dangerouslySetInnerHTML={{ __html: item.description }}
                    />
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* Leadership Spotlight */}
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" },
          gap: 0,
          alignItems: "stretch",
        }}
      >
        <Box
          sx={{
            backgroundImage: `url('https://images.unsplash.com/photo-1543286386-713bdd548da4?w=800&h=600&fit=crop&auto=format&q=80')`,
            backgroundSize: "cover",
            backgroundPosition: "center",
            minHeight: { xs: "280px", md: "480px" },
            display: { xs: "none", md: "block" },
            position: "relative",
            "&::after": {
              content: '""',
              position: "absolute",
              inset: 0,
              backgroundColor: `rgba(0,0,0,0.3)`,
            },
          }}
        />
        <Box
          sx={{
            backgroundColor: theme.palette.background.paper,
            p: { xs: 4, md: 6 },
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
            minHeight: { xs: "auto", md: "480px" },
          }}
        >
          <Typography
            sx={{
              fontSize: "0.75rem",
              fontWeight: 700,
              textTransform: "uppercase",
              letterSpacing: "3px",
              color: theme.palette.primary.main,
              mb: 1.5,
            }}
          >
            Expert Team
          </Typography>
          <Typography
            variant="h3"
            sx={{
              fontSize: { xs: "2rem", md: "2.8rem" },
              fontWeight: 900,
              mb: 3,
              color: theme.palette.text.primary,
              lineHeight: 1.2,
            }}
          >
            Built by Market Veterans
          </Typography>
          <Typography
            sx={{
              fontSize: "1.05rem",
              color: theme.palette.text.secondary,
              mb: 4,
              lineHeight: 1.8,
              maxWidth: "460px",
            }}
          >
            Our team combines deep capital markets expertise with advanced
            technology capabilities. Every piece of the platform&#8212;from the
            data infrastructure to the trading algorithm to the research
            interface&#8212;was built in-house.
          </Typography>
          <Box sx={{ mb: 4 }}>
            {[
              "Minervini-based quantitative research system",
              "24-loader automated daily data pipeline",
              "Seven-phase algorithmic trading orchestrator",
              "Full-stack research platform built from scratch",
            ].map((credential, i) => (
              <Box
                key={i}
                sx={{
                  display: "flex",
                  alignItems: "flex-start",
                  mb: 2,
                  gap: 1.5,
                }}
              >
                <Box
                  sx={{
                    width: 22,
                    height: 22,
                    flexShrink: 0,
                    backgroundColor: theme.palette.primary.main,
                    color: "#fff",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: "0.7rem",
                    fontWeight: 700,
                    mt: 0.2,
                  }}
                >
                  &#10003;
                </Box>
                <Typography
                  sx={{
                    color: theme.palette.text.secondary,
                    fontSize: "0.97rem",
                    lineHeight: 1.6,
                  }}
                >
                  {credential}
                </Typography>
              </Box>
            ))}
          </Box>
          <Box
            onClick={() => navigate("/our-team")}
            sx={{
              px: 3,
              py: 1.5,
              backgroundColor: theme.palette.primary.main,
              color: "#fff",
              cursor: "pointer",
              fontWeight: 700,
              fontSize: "0.95rem",
              transition: "all 0.25s",
              display: "inline-block",
              alignSelf: "flex-start",
              "&:hover": {
                boxShadow: `0 8px 20px ${alpha(theme.palette.primary.main, 0.35)}`,
                transform: "translateY(-2px)",
              },
            }}
          >
            Meet the Team
          </Box>
        </Box>
      </Box>

      {/* Research Philosophy */}
      <Box
        sx={{
          py: { xs: 8, md: 10 },
          backgroundColor: theme.palette.background.default,
        }}
      >
        <Container maxWidth="lg">
          <Box sx={{ textAlign: "center", mb: 7 }}>
            <Typography
              variant="overline"
              sx={{
                color: theme.palette.primary.main,
                fontWeight: 700,
                letterSpacing: "3px",
                display: "block",
                mb: 1.5,
              }}
            >
              Research Philosophy
            </Typography>
            <Typography
              variant="h3"
              sx={{
                fontSize: { xs: "1.9rem", sm: "2.3rem", md: "2.8rem" },
                fontWeight: 800,
                mb: 2,
                color: theme.palette.text.primary,
                letterSpacing: "-0.5px",
              }}
            >
              Our Core Principles
            </Typography>
            <Typography
              sx={{
                fontSize: "1.05rem",
                color: theme.palette.text.secondary,
                maxWidth: "600px",
                mx: "auto",
                lineHeight: 1.8,
              }}
            >
              Six principles that guide how we build research models and what we
              publish
            </Typography>
          </Box>
          <Grid container spacing={3}>
            {philosophy.map((item, idx) => (
              <Grid item xs={12} md={6} key={idx}>
                <Card
                  sx={{
                    height: "100%",
                    border: `1px solid ${theme.palette.divider}`,
                    backgroundColor: theme.palette.background.paper,
                    borderRadius: "0px",
                    boxShadow: "none",
                    transition: "all 0.25s ease",
                    "&:hover": {
                      boxShadow: "0 4px 12px rgba(0,0,0,0.07)",
                    },
                  }}
                >
                  <CardContent sx={{ p: 3.5 }}>
                    <Typography
                      variant="h6"
                      sx={{
                        fontWeight: 700,
                        mb: 1.5,
                        color: theme.palette.primary.main,
                        fontSize: "1rem",
                      }}
                    >
                      {item.principle}
                    </Typography>
                    <Typography
                      variant="body2"
                      sx={{
                        color: theme.palette.text.secondary,
                        lineHeight: 1.7,
                      }}
                      dangerouslySetInnerHTML={{ __html: item.description }}
                    />
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* By the Numbers */}
      <Box
        sx={{
          py: { xs: 7, md: 8 },
          backgroundColor: theme.palette.primary.main,
        }}
      >
        <Container maxWidth="lg">
          <Grid container spacing={0} justifyContent="center">
            {[
              { metric: "5,300+", label: "Stocks Covered" },
              { metric: "10+", label: "Years of Data" },
              { metric: "24", label: "Data Loaders" },
              { metric: "6", label: "Research Dimensions" },
              { metric: "Daily", label: "Research Updates" },
              { metric: "100%", label: "Free to Use" },
            ].map((item, idx) => (
              <Grid
                item
                xs={6}
                sm={4}
                md={2}
                key={idx}
                sx={{
                  textAlign: "center",
                  py: { xs: 3, md: 2 },
                  borderRight: {
                    md: idx < 5 ? `1px solid ${alpha("#fff", 0.2)}` : "none",
                  },
                }}
              >
                <Typography
                  sx={{
                    fontSize: { xs: "2rem", md: "2.4rem" },
                    fontWeight: 900,
                    color: "#fff",
                    lineHeight: 1,
                  }}
                >
                  {item.metric}
                </Typography>
                <Typography
                  sx={{
                    fontSize: "0.78rem",
                    color: alpha("#fff", 0.75),
                    mt: 0.75,
                    fontWeight: 500,
                    textTransform: "uppercase",
                    letterSpacing: "0.5px",
                  }}
                >
                  {item.label}
                </Typography>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      <CTASection
        variant="primary"
        title="Ready to Get Started?"
        subtitle="Access research-driven equity analysis designed for serious investors&#8212;completely free, no subscription required."
        primaryCTA={{ label: "Launch Platform", link: "/app/markets" }}
        secondaryCTA={{ label: "Meet the Team", link: "/our-team" }}
      />
    </MarketingLayout>
  );
};

export default Firm;
