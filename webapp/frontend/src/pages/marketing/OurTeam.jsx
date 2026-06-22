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
import MarketingLayout from "../../components/marketing/MarketingLayout";
import PageHeader from "../../components/marketing/PageHeader";
import CTASection from "../../components/marketing/CTASection";
import {
  Code as CodeIcon,
  BarChart as BarChartIcon,
  Security as SecurityIcon,
  Speed as SpeedIcon,
} from "@mui/icons-material";

const OurTeam = () => {
  const theme = useTheme();

  const teamMembers = [
    {
      name: "Erik A.",
      initials: "EA",
      role: "Founder",
      bio: "Built Bullseye from the ground up&#8212;from the trading algorithm and data pipeline to the research platform and infrastructure. Background in quantitative strategy, systematic trend-following, and financial technology. Designed the Minervini-based scoring system and the multi-phase trading orchestrator that runs the platform.",
      areas: [
        "Quantitative Research",
        "Platform Architecture",
        "Algo Trading",
        "Systems Design",
      ],
    },
    {
      name: "Anthony Riga",
      initials: "AR",
      role: "Senior Research Analyst",
      bio: "Leads market research, macro analysis, and sector rotation coverage. Specializes in institutional capital flows, earnings dynamics, and structural market trends. Publishes research covering AI productivity cycles, market breadth analysis, and sector rotation signals.",
      areas: [
        "Market Research",
        "Macro Analysis",
        "Sector Rotation",
        "Earnings Analysis",
      ],
    },
  ];

  const platformPillars = [
    {
      icon: <BarChartIcon />,
      title: "Data Infrastructure",
      description:
        "Automated daily pipeline loading 24 data sources&#8212;prices, technicals, fundamentals, earnings, sentiment, and economic indicators&#8212;into a centralized research database updated before market open.",
    },
    {
      icon: <CodeIcon />,
      title: "Research Engine",
      description:
        "Multi-factor scoring models combining Minervini trend analysis with fundamental quality filters, earnings dynamics, and market breadth indicators. Every signal is backtested and validated before deployment.",
    },
    {
      icon: <SpeedIcon />,
      title: "Live Trading System",
      description:
        "Seven-phase orchestration algorithm that runs at market open and close&#8212;checking data freshness, evaluating circuit breakers, managing positions, executing signals, and reconciling with the broker.",
    },
    {
      icon: <SecurityIcon />,
      title: "Research Platform",
      description:
        "Full-stack web application surfacing scores, signals, earnings, sector analysis, economic data, and portfolio tracking. Built for serious investors who want professional-grade research without the institutional price tag.",
    },
  ];

  return (
    <MarketingLayout>
      <PageHeader
        title="Our Team"
        subtitle="A small, focused team building institutional-grade research tools for independent investors"
      />

      {/* Team Intro */}
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
              Who We Are
            </Typography>
            <Typography
              variant="h3"
              sx={{
                fontSize: { xs: "1.9rem", sm: "2.3rem", md: "2.8rem" },
                fontWeight: 800,
                mb: 2.5,
                color: theme.palette.text.primary,
                letterSpacing: "-0.5px",
              }}
            >
              Deep Expertise. Focused Mission.
            </Typography>
            <Typography
              sx={{
                fontSize: "1.1rem",
                color: theme.palette.text.secondary,
                maxWidth: "680px",
                mx: "auto",
                lineHeight: 1.8,
              }}
            >
              We&apos;re not a hundred-person research firm. We&apos;re a small
              team who built the entire platform&#8212;data pipeline, trading
              algorithm, research models, and web application&#8212;from
              scratch. That focus is what makes the platform exceptional.
            </Typography>
          </Box>

          <Grid container spacing={4} justifyContent="center">
            {teamMembers.map((member) => (
              <Grid item xs={12} sm={10} md={6} key={member.name}>
                <Card
                  sx={{
                    height: "100%",
                    border: `1px solid ${theme.palette.divider}`,
                    backgroundColor: theme.palette.background.paper,
                    borderRadius: "0px",
                    borderTop: `4px solid ${theme.palette.primary.main}`,
                    boxShadow: "none",
                    transition: "all 0.25s ease",
                    "&:hover": {
                      boxShadow: "0 8px 24px rgba(0,0,0,0.09)",
                    },
                  }}
                >
                  <CardContent sx={{ p: 4 }}>
                    <Box
                      sx={{
                        display: "flex",
                        alignItems: "center",
                        gap: 2,
                        mb: 2.5,
                      }}
                    >
                      <Box
                        sx={{
                          width: 56,
                          height: 56,
                          flexShrink: 0,
                          borderRadius: "50%",
                          backgroundColor: alpha(
                            theme.palette.primary.main,
                            0.12
                          ),
                          border: `2px solid ${alpha(theme.palette.primary.main, 0.3)}`,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          fontSize: "1rem",
                          fontWeight: 900,
                          color: theme.palette.primary.main,
                          letterSpacing: "1px",
                        }}
                      >
                        {member.initials}
                      </Box>
                      <Box>
                        <Typography
                          variant="h5"
                          sx={{
                            fontWeight: 800,
                            mb: 0.25,
                            color: theme.palette.text.primary,
                            fontSize: "1.15rem",
                          }}
                        >
                          {member.name}
                        </Typography>
                        <Typography
                          variant="body2"
                          sx={{
                            color: theme.palette.primary.main,
                            fontWeight: 700,
                            fontSize: "0.75rem",
                            textTransform: "uppercase",
                            letterSpacing: "1.5px",
                          }}
                        >
                          {member.role}
                        </Typography>
                      </Box>
                    </Box>

                    <Typography
                      variant="body2"
                      sx={{
                        mb: 3,
                        color: theme.palette.text.secondary,
                        lineHeight: 1.8,
                        fontSize: "0.95rem",
                      }}
                      dangerouslySetInnerHTML={{ __html: member.bio }}
                    />

                    <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap" }}>
                      {member.areas.map((area, idx) => (
                        <Box
                          key={idx}
                          sx={{
                            px: 1.5,
                            py: 0.5,
                            fontSize: "0.72rem",
                            fontWeight: 600,
                            color: theme.palette.primary.main,
                            backgroundColor: alpha(
                              theme.palette.primary.main,
                              0.08
                            ),
                            border: `1px solid ${alpha(theme.palette.primary.main, 0.2)}`,
                            borderRadius: "0px",
                          }}
                        >
                          {area}
                        </Box>
                      ))}
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* Platform Section */}
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
              What We Built
            </Typography>
            <Typography
              variant="h3"
              sx={{
                fontSize: { xs: "1.9rem", sm: "2.3rem", md: "2.8rem" },
                fontWeight: 800,
                mb: 2.5,
                color: theme.palette.text.primary,
                letterSpacing: "-0.5px",
              }}
            >
              Built End-to-End In-House
            </Typography>
            <Typography
              sx={{
                fontSize: "1.05rem",
                color: theme.palette.text.secondary,
                maxWidth: "620px",
                mx: "auto",
                lineHeight: 1.8,
              }}
            >
              Every piece of the platform&#8212;from the AWS infrastructure and
              data loaders to the trading algorithm and research
              dashboard&#8212;was designed and built by us.
            </Typography>
          </Box>

          <Grid container spacing={3}>
            {platformPillars.map((pillar, idx) => (
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
                      borderColor: theme.palette.primary.main,
                      boxShadow: "0 4px 16px rgba(0,0,0,0.07)",
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
                        mb: 2,
                        border: `1px solid ${alpha(theme.palette.primary.main, 0.2)}`,
                      }}
                    >
                      {pillar.icon}
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
                      {pillar.title}
                    </Typography>
                    <Typography
                      variant="body2"
                      sx={{
                        color: theme.palette.text.secondary,
                        lineHeight: 1.7,
                      }}
                      dangerouslySetInnerHTML={{ __html: pillar.description }}
                    />
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* Philosophy Strip */}
      <Box
        sx={{
          py: { xs: 8, md: 10 },
          background: `linear-gradient(135deg, ${theme.palette.primary.main} 0%, ${alpha(theme.palette.primary.main, 0.8)} 100%)`,
        }}
      >
        <Container maxWidth="md">
          <Typography
            variant="h3"
            sx={{
              fontSize: { xs: "1.8rem", md: "2.5rem" },
              fontWeight: 800,
              color: "#fff",
              textAlign: "center",
              mb: 3,
              lineHeight: 1.3,
            }}
          >
            &#8220;Independent research, no conflicts, no subscriptions. Just
            the best tools we could build.&#8221;
          </Typography>
          <Typography
            sx={{
              textAlign: "center",
              color: alpha("#fff", 0.75),
              fontSize: "1rem",
            }}
          >
            &mdash; Bullseye Financial
          </Typography>
        </Container>
      </Box>

      <CTASection
        variant="primary"
        title="See the Platform in Action"
        subtitle="Explore the research tools our team built&#8212;free, no account required for market data."
        primaryCTA={{ label: "Launch Platform", link: "/app/markets" }}
        secondaryCTA={{ label: "Contact Us", link: "/contact" }}
      />
    </MarketingLayout>
  );
};

export default OurTeam;
