import React, { useState } from "react";
import {
  Card,
  CardContent,
  Typography,
  Grid,
  Box,
  Button,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Chip,
  Alert,
  AlertTitle,
  LinearProgress,
  Switch,
  FormControlLabel,
  Slider,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Accordion,
  AccordionSummary,
  AccordionDetails,
} from "@mui/material";
import {
  Optimize as OptimizeIcon,
  TrendingDown as TrendingDownIcon,
  ExpandMore as ExpandMoreIcon,
  Check as CheckIcon,
  Warning as WarningIcon,
  Compare as CompareIcon,
} from "@mui/icons-material";

const CostOptimizer = ({ costData, onOptimize, onApplyRecommendation }) => {
  const [optimizationMode, setOptimizationMode] = useState("balanced");
  const [autoOptimize, setAutoOptimize] = useState(false);
  const [budgetLimit, setBudgetLimit] = useState(50);
  const [previewDialog, setPreviewDialog] = useState(false);
  const [selectedOptimization, setSelectedOptimization] = useState(null);

  // Mock cost optimization data
  const mockCostBreakdown = [
    {
      provider: "Polygon",
      current: 18.75,
      optimized: 14.2,
      savings: 4.55,
      confidence: 95,
    },
    {
      provider: "Alpaca",
      current: 12.5,
      optimized: 11.8,
      savings: 0.7,
      confidence: 85,
    },
    {
      provider: "Finnhub",
      current: 8.2,
      optimized: 6.9,
      savings: 1.3,
      confidence: 90,
    },
  ];

  const mockOptimizations = [
    {
      id: 1,
      title: "Reduce Polygon Usage During Off-Hours",
      description:
        "Switch to Alpaca for non-critical symbols during 8PM-6AM EST",
      impact: "High",
      savings: "$4.55/day",
      confidence: 95,
      effort: "Low",
      risks: ["Slightly higher latency during off-hours"],
      benefits: ["24% cost reduction", "Maintained data quality"],
      autoApply: true,
    },
    {
      id: 2,
      title: "Optimize Symbol Distribution",
      description: "Move low-volume symbols from Polygon to Finnhub",
      impact: "Medium",
      savings: "$2.30/day",
      confidence: 88,
      effort: "Medium",
      risks: ["Potential latency increase for some symbols"],
      benefits: ["Cost efficient for low-volume data", "Reduced rate limiting"],
      autoApply: false,
    },
    {
      id: 3,
      title: "Implement Smart Caching",
      description:
        "Extend cache TTL for stable symbols during low volatility periods",
      impact: "Medium",
      savings: "$1.85/day",
      confidence: 92,
      effort: "Low",
      risks: ["Slightly delayed updates during market events"],
      benefits: ["Reduced API calls", "Lower bandwidth usage"],
      autoApply: true,
    },
    {
      id: 4,
      title: "Consolidate Connections",
      description:
        "Merge multiple low-usage connections into single connections",
      impact: "Low",
      savings: "$0.95/day",
      confidence: 85,
      effort: "High",
      risks: ["Connection complexity", "Single point of failure"],
      benefits: ["Reduced overhead", "Simplified monitoring"],
      autoApply: false,
    },
  ];

  const totalSavings = mockOptimizations.reduce(
    (sum, opt) =>
      sum + parseFloat(opt.savings.replace("$", "").replace("/day", "")),
    0
  );

  const getImpactColor = (impact) => {
    switch (impact) {
      case "High":
        return "success";
      case "Medium":
        return "warning";
      case "Low":
        return "info";
      default:
        return "default";
    }
  };

  const getConfidenceColor = (confidence) => {
    if (confidence >= 90) return "success";
    if (confidence >= 80) return "warning";
    return "error";
  };

  const handleOptimizationPreview = (optimization) => {
    setSelectedOptimization(optimization);
    setPreviewDialog(true);
  };

  const handleApplyOptimization = async (optimizationId) => {
    try {
      // Mock API call
      console.log("Applying optimization:", optimizationId);
      onApplyRecommendation?.(optimizationId);
      setPreviewDialog(false);
    } catch (error) {
      console.error("Failed to apply optimization:", error);
    }
  };

  return (
    <Box>
      {/* Cost Overview */}
      <Card elevation={2} sx={{ mb: 3 }}>
        <CardContent>
          <Box
            display="flex"
            justifyContent="space-between"
            alignItems="center"
            mb={2}
          >
            <Typography variant="h6" fontWeight="bold">
              Cost Optimization Center
            </Typography>
            <Box display="flex" gap={2}>
              <FormControlLabel
                control={
                  <Switch
                    checked={autoOptimize}
                    onChange={(e) => setAutoOptimize(e.target.checked)}
                  />
                }
                label="Auto-optimize"
              />
              <Button
                startIcon={<OptimizeIcon />}
                variant="contained"
                onClick={onOptimize}
              >
                Optimize Now
              </Button>
            </Box>
          </Box>

          <Grid container spacing={3}>
            <Grid item xs={12} sm={3}>
              <Box
                textAlign="center"
                p={2}
                bgcolor="error.light"
                borderRadius={1}
              >
                <Typography variant="h4" color="white" fontWeight="bold">
                  $39.45
                </Typography>
                <Typography variant="body2" color="white">
                  Current Daily Cost
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={3}>
              <Box
                textAlign="center"
                p={2}
                bgcolor="success.light"
                borderRadius={1}
              >
                <Typography variant="h4" color="white" fontWeight="bold">
                  $30.10
                </Typography>
                <Typography variant="body2" color="white">
                  Optimized Cost
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={3}>
              <Box
                textAlign="center"
                p={2}
                bgcolor="warning.light"
                borderRadius={1}
              >
                <Typography variant="h4" color="white" fontWeight="bold">
                  $9.35
                </Typography>
                <Typography variant="body2" color="white">
                  Potential Savings
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={3}>
              <Box
                textAlign="center"
                p={2}
                bgcolor="info.light"
                borderRadius={1}
              >
                <Typography variant="h4" color="white" fontWeight="bold">
                  24%
                </Typography>
                <Typography variant="body2" color="white">
                  Cost Reduction
                </Typography>
              </Box>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      <Grid container spacing={3}>
        {/* Budget Settings */}
        <Grid item xs={12} md={4}>
          <Card elevation={2}>
            <CardContent>
              <Typography variant="h6" fontWeight="bold" gutterBottom>
                Budget Controls
              </Typography>

              <Box mb={3}>
                <Typography variant="body2" color="textSecondary" gutterBottom>
                  Daily Budget Limit
                </Typography>
                <Box px={1}>
                  <Slider
                    value={budgetLimit}
                    onChange={(e, value) => setBudgetLimit(value)}
                    min={20}
                    max={100}
                    step={5}
                    marks={[
                      { value: 20, label: "$20" },
                      { value: 50, label: "$50" },
                      { value: 100, label: "$100" },
                    ]}
                    valueLabelDisplay="auto"
                    valueLabelFormat={(value) => `$${value}`}
                  />
                </Box>
              </Box>

              <Box mb={3}>
                <FormControl fullWidth size="small">
                  <InputLabel>Optimization Mode</InputLabel>
                  <Select
                    value={optimizationMode}
                    label="Optimization Mode"
                    onChange={(e) => setOptimizationMode(e.target.value)}
                  >
                    <MenuItem value="aggressive">
                      Aggressive (Max Savings)
                    </MenuItem>
                    <MenuItem value="balanced">Balanced</MenuItem>
                    <MenuItem value="conservative">
                      Conservative (Min Risk)
                    </MenuItem>
                  </Select>
                </FormControl>
              </Box>

              <Alert severity="info" size="small">
                Current usage: {((39.45 / budgetLimit) * 100).toFixed(1)}% of
                budget
              </Alert>
            </CardContent>
          </Card>
        </Grid>

        {/* Provider Cost Breakdown */}
        <Grid item xs={12} md={8}>
          <Card elevation={2}>
            <CardContent>
              <Typography variant="h6" fontWeight="bold" gutterBottom>
                Provider Cost Analysis
              </Typography>
              <TableContainer>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell>Provider</TableCell>
                      <TableCell align="right">Current</TableCell>
                      <TableCell align="right">Optimized</TableCell>
                      <TableCell align="right">Savings</TableCell>
                      <TableCell align="center">Confidence</TableCell>
                      <TableCell align="center">Progress</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {mockCostBreakdown.map((row) => (
                      <TableRow key={row.provider}>
                        <TableCell fontWeight="medium">
                          {row.provider}
                        </TableCell>
                        <TableCell align="right">
                          ${row.current.toFixed(2)}
                        </TableCell>
                        <TableCell align="right">
                          <Typography color="success.main" fontWeight="medium">
                            ${row.optimized.toFixed(2)}
                          </Typography>
                        </TableCell>
                        <TableCell align="right">
                          <Box
                            display="flex"
                            alignItems="center"
                            justifyContent="flex-end"
                            gap={1}
                          >
                            <TrendingDownIcon
                              color="success"
                              fontSize="small"
                            />
                            <Typography
                              color="success.main"
                              fontWeight="medium"
                            >
                              ${row.savings.toFixed(2)}
                            </Typography>
                          </Box>
                        </TableCell>
                        <TableCell align="center">
                          <Chip
                            label={`${row.confidence}%`}
                            size="small"
                            color={getConfidenceColor(row.confidence)}
                          />
                        </TableCell>
                        <TableCell align="center">
                          <Box width={60}>
                            <LinearProgress
                              variant="determinate"
                              value={(row.savings / row.current) * 100}
                              color="success"
                            />
                          </Box>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        </Grid>

        {/* Optimization Recommendations */}
        <Grid item xs={12}>
          <Card elevation={2}>
            <CardContent>
              <Typography variant="h6" fontWeight="bold" gutterBottom>
                Optimization Recommendations
              </Typography>

              <Alert severity="success" sx={{ mb: 2 }}>
                <AlertTitle>
                  Potential Monthly Savings: ${(totalSavings * 30).toFixed(2)}
                </AlertTitle>
                Implementing all recommendations could save you $
                {totalSavings.toFixed(2)} per day
              </Alert>

              {mockOptimizations.map((optimization) => (
                <Accordion key={optimization.id} sx={{ mb: 1 }}>
                  <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                    <Box
                      display="flex"
                      alignItems="center"
                      width="100%"
                      gap={2}
                    >
                      <Box flexGrow={1}>
                        <Typography variant="subtitle1" fontWeight="medium">
                          {optimization.title}
                        </Typography>
                        <Typography variant="body2" color="textSecondary">
                          {optimization.description}
                        </Typography>
                      </Box>
                      <Chip
                        label={optimization.impact}
                        size="small"
                        color={getImpactColor(optimization.impact)}
                      />
                      <Typography
                        variant="body2"
                        fontWeight="bold"
                        color="success.main"
                      >
                        {optimization.savings}
                      </Typography>
                    </Box>
                  </AccordionSummary>
                  <AccordionDetails>
                    <Grid container spacing={2}>
                      <Grid item xs={12} md={6}>
                        <Typography
                          variant="body2"
                          fontWeight="medium"
                          gutterBottom
                        >
                          Benefits:
                        </Typography>
                        {optimization.benefits.map((benefit, index) => (
                          <Box
                            key={index}
                            display="flex"
                            alignItems="center"
                            gap={1}
                            mb={0.5}
                          >
                            <CheckIcon color="success" fontSize="small" />
                            <Typography variant="body2">{benefit}</Typography>
                          </Box>
                        ))}
                      </Grid>
                      <Grid item xs={12} md={6}>
                        <Typography
                          variant="body2"
                          fontWeight="medium"
                          gutterBottom
                        >
                          Risks:
                        </Typography>
                        {optimization.risks.map((risk, index) => (
                          <Box
                            key={index}
                            display="flex"
                            alignItems="center"
                            gap={1}
                            mb={0.5}
                          >
                            <WarningIcon color="warning" fontSize="small" />
                            <Typography variant="body2">{risk}</Typography>
                          </Box>
                        ))}
                      </Grid>
                      <Grid item xs={12}>
                        <Box
                          display="flex"
                          justifyContent="space-between"
                          alignItems="center"
                          mt={2}
                        >
                          <Box display="flex" gap={2}>
                            <Chip
                              label={`${optimization.confidence}% confidence`}
                              size="small"
                            />
                            <Chip
                              label={`${optimization.effort} effort`}
                              size="small"
                              variant="outlined"
                            />
                          </Box>
                          <Box display="flex" gap={1}>
                            <Button
                              size="small"
                              variant="outlined"
                              startIcon={<CompareIcon />}
                              onClick={() =>
                                handleOptimizationPreview(optimization)
                              }
                            >
                              Preview
                            </Button>
                            <Button
                              size="small"
                              variant="contained"
                              color={
                                optimization.autoApply ? "success" : "primary"
                              }
                              onClick={() =>
                                handleApplyOptimization(optimization.id)
                              }
                            >
                              {optimization.autoApply ? "Auto-Apply" : "Apply"}
                            </Button>
                          </Box>
                        </Box>
                      </Grid>
                    </Grid>
                  </AccordionDetails>
                </Accordion>
              ))}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Optimization Preview Dialog */}
      <Dialog
        open={previewDialog}
        onClose={() => setPreviewDialog(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          Optimization Preview: {selectedOptimization?.title}
        </DialogTitle>
        <DialogContent>
          {selectedOptimization && (
            <Box sx={{ pt: 2 }}>
              <Alert severity="info" sx={{ mb: 2 }}>
                <AlertTitle>Impact Analysis</AlertTitle>
                This optimization will save {
                  selectedOptimization.savings
                } with {selectedOptimization.confidence}% confidence
              </Alert>

              <Typography variant="h6" gutterBottom>
                Implementation Details:
              </Typography>
              <Typography variant="body2" paragraph>
                {selectedOptimization.description}
              </Typography>

              <Grid container spacing={2}>
                <Grid item xs={6}>
                  <Typography variant="subtitle2" gutterBottom>
                    Expected Benefits:
                  </Typography>
                  {selectedOptimization.benefits?.map((benefit, index) => (
                    <Typography
                      key={index}
                      variant="body2"
                      color="success.main"
                    >
                      • {benefit}
                    </Typography>
                  ))}
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="subtitle2" gutterBottom>
                    Potential Risks:
                  </Typography>
                  {selectedOptimization.risks?.map((risk, index) => (
                    <Typography
                      key={index}
                      variant="body2"
                      color="warning.main"
                    >
                      • {risk}
                    </Typography>
                  ))}
                </Grid>
              </Grid>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPreviewDialog(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={() => handleApplyOptimization(selectedOptimization?.id)}
          >
            Apply Optimization
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default CostOptimizer;
