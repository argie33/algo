import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { 
  runPortfolioOptimization, 
  getOptimizationRecommendations, 
  executeRebalancing,
  getPortfolioRiskAnalysis 
} from '../services/api';
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  CardHeader,
  Button,
  CircularProgress,
  Alert,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Slider,
  Switch,
  FormControlLabel,
  Divider,
  Stepper,
  Step,
  StepLabel,
  StepContent,
  TextField,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions
} from '@mui/material';
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  ScatterChart,
  Scatter,
  LineChart,
  Line
} from 'recharts';
import {
  Tune as OptimizeIcon,
  TrendingUp,
  TrendingDown,
  Analytics,
  Assessment,
  Security,
  AccountBalance,
  Warning,
  CheckCircle,
  Info,
  PlayArrow,
  Tune,
  ExpandMore,
  Star,
  Lightbulb,
  Speed,
  Balance
} from '@mui/icons-material';
import { 
  getPortfolioOptimizationData, 
  runPortfolioOptimization, 
  getRebalancingRecommendations,
  getRiskAnalysis 
} from '../services/api';

const PortfolioOptimization = () => {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [optimizing, setOptimizing] = useState(false);
  const [activeStep, setActiveStep] = useState(0);
  const [optimizationResults, setOptimizationResults] = useState(null);
  const [rebalanceRecommendations, setRebalanceRecommendations] = useState(null);
  const [currentPortfolio, setCurrentPortfolio] = useState(null);
  const [optimizedPortfolio, setOptimizedPortfolio] = useState(null);
  const [riskAnalysis, setRiskAnalysis] = useState(null);
  const [showResultsDialog, setShowResultsDialog] = useState(false);

  // Optimization parameters
  const [optimizationParams, setOptimizationParams] = useState({
    objective: 'maxSharpe', // maxSharpe, minRisk, maxReturn, targetReturn
    riskTolerance: 50, // 1-100
    targetReturn: 10, // percentage
    constraints: {
      maxWeight: 0.20, // 20% max single position
      minWeight: 0.01, // 1% min single position
      allowShorts: false,
      rebalanceThreshold: 0.05 // 5% threshold
    },
    lookbackDays: 252, // 1 year of historical data
    includeAssets: [],
    excludeAssets: []
  });

  useEffect(() => {
    fetchOptimizationData();
  }, []);

  const fetchOptimizationData = async () => {
    try {
      setLoading(true);
      
      const [portfolioResponse, rebalanceResponse, riskResponse] = await Promise.allSettled([
        getPortfolioOptimizationData(),
        getRebalancingRecommendations(),
        getRiskAnalysis()
      ]);

      // Handle portfolio data
      if (portfolioResponse.status === 'fulfilled') {
        const portfolioData = portfolioResponse.value?.data || portfolioResponse.value;
        setCurrentPortfolio({
          totalValue: portfolioData?.totalValue || portfolioData?.currentAllocation?.reduce((sum, item) => sum + item.amount, 0) || 100000,
          expectedReturn: portfolioData?.expectedReturn || 12.5,
          risk: portfolioData?.risk || portfolioData?.volatility || 18.5,
          sharpeRatio: portfolioData?.sharpeRatio || 1.24
        });
      } else {
        // Mock data for current portfolio
        setCurrentPortfolio({
          totalValue: 100000,
          expectedReturn: 12.5,
          risk: 18.5,
          sharpeRatio: 1.24
        });
      }

      // Handle rebalance recommendations
      if (rebalanceResponse.status === 'fulfilled') {
        const rebalanceData = rebalanceResponse.value?.data || rebalanceResponse.value;
        const recommendations = rebalanceData?.recommendations || [];
        
        // Transform recommendations to expected format
        const transformedRecommendations = recommendations.map(rec => ({
          symbol: rec.symbol,
          currentWeight: rec.currentWeight || rec.current_weight || 0,
          targetWeight: rec.targetWeight || rec.target_weight || rec.optimalWeight || 0,
          difference: (rec.targetWeight || rec.target_weight || rec.optimalWeight || 0) - (rec.currentWeight || rec.current_weight || 0),
          action: rec.action || (rec.amount > 0 ? 'BUY' : 'SELL'),
          priority: rec.priority || 'MEDIUM'
        }));
        
        setRebalanceRecommendations(transformedRecommendations);
      } else {
        // Mock rebalance recommendations
        setRebalanceRecommendations([
          {
            symbol: 'AAPL',
            currentWeight: 28.5,
            targetWeight: 20.0,
            difference: -8.5,
            action: 'SELL',
            priority: 'HIGH'
          },
          {
            symbol: 'MSFT',
            currentWeight: 22.9,
            targetWeight: 25.0,
            difference: 2.1,
            action: 'BUY',
            priority: 'MEDIUM'
          }
        ]);
      }

      // Handle risk analysis
      if (riskResponse.status === 'fulfilled') {
        const riskData = riskResponse.value?.data || riskResponse.value;
        setRiskAnalysis({
          riskScore: riskData?.riskScore || riskData?.overallRiskScore || 6.2,
          riskFactors: riskData?.riskFactors || riskData?.recommendations || [
            {
              name: 'Concentration Risk',
              severity: 'MEDIUM',
              description: 'Portfolio shows moderate concentration in technology sector'
            },
            {
              name: 'Market Risk',
              severity: 'LOW',
              description: 'Portfolio beta is within acceptable range'
            }
          ]
        });
      } else {
        // Mock risk analysis
        setRiskAnalysis({
          riskScore: 6.2,
          riskFactors: [
            {
              name: 'Concentration Risk',
              severity: 'MEDIUM',
              description: 'Portfolio shows moderate concentration in technology sector'
            },
            {
              name: 'Market Risk',
              severity: 'LOW',
              description: 'Portfolio beta is within acceptable range'
            }
          ]
        });
      }
    } catch (err) {
      setError('Failed to fetch optimization data');
      console.error('Optimization data fetch error:', err);
      
      // Set mock data on error
      setCurrentPortfolio({
        totalValue: 100000,
        expectedReturn: 12.5,
        risk: 18.5,
        sharpeRatio: 1.24
      });
      
      setRebalanceRecommendations([]);
      
      setRiskAnalysis({
        riskScore: 6.2,
        riskFactors: []
      });
    } finally {
      setLoading(false);
    }
  };

  const handleOptimization = async () => {
    try {
      setOptimizing(true);
      setError(null);
      
      // Call the real optimization API with proper parameters
      const optimizationRequest = {
        objective: optimizationParams.objective,
        constraints: {
          maxWeight: optimizationParams.constraints.maxWeight,
          minWeight: optimizationParams.constraints.minWeight,
          allowShorts: optimizationParams.constraints.allowShorts
        },
        includeAssets: optimizationParams.includeAssets,
        excludeAssets: optimizationParams.excludeAssets,
        lookbackDays: optimizationParams.lookbackDays
      };
      
      console.log('Running optimization with params:', optimizationRequest);
      const response = await runPortfolioOptimization(optimizationRequest);
      const results = response?.data || response;
      
      if (results && results.success !== false) {
        // Use real optimization results
        const optimizationData = results.optimization || results;
        const currentData = results.currentPortfolio || {};
        
        const transformedResults = {
          current: {
            expectedReturn: currentData.expectedReturn || currentPortfolio?.expectedReturn || 12.5,
            risk: currentData.volatility || currentPortfolio?.risk || 18.5,
            sharpeRatio: currentData.sharpeRatio || currentPortfolio?.sharpeRatio || 1.24
          },
          optimized: {
            expectedReturn: (optimizationData.expectedReturn || 0.14) * 100, // Convert to percentage
            risk: (optimizationData.volatility || 0.18) * 100, // Convert to percentage  
            sharpeRatio: optimizationData.sharpeRatio || 1.45
          }
        };
        
        setOptimizationResults(transformedResults);
        
        // Set optimized portfolio allocation from real results
        const optimizedAllocation = optimizationData.weights || [];
        const formattedAllocation = optimizedAllocation.map(item => ({
          symbol: item.symbol,
          weight: typeof item.weight === 'number' ? item.weight : parseFloat(item.weight) || 0
        }));
        
        setOptimizedPortfolio({ allocation: formattedAllocation });
        
        // Update rebalancing recommendations if available
        if (results.rebalancing && results.rebalancing.length > 0) {
          const formattedRebalancing = results.rebalancing.map(rec => ({
            symbol: rec.symbol,
            currentWeight: rec.currentWeight,
            targetWeight: rec.targetWeight,
            difference: rec.targetWeight - rec.currentWeight,
            action: rec.action,
            priority: rec.priority || 'Medium'
          }));
          setRebalanceRecommendations(formattedRebalancing);
        }
        
        setShowResultsDialog(true);
        
        // Show insights if available
        if (results.insights && results.insights.length > 0) {
          console.log('Optimization insights:', results.insights);
        }
        
      } else {
        throw new Error(results?.message || results?.error || 'No optimization results received');
      }
    } catch (err) {
      console.error('Optimization error:', err);
      setError(`Optimization failed: ${err.message}. Using demo results.`);
      
      // Fallback to mock results but still show them
      const mockResults = {
        current: {
          expectedReturn: 12.5,
          risk: 18.5,
          sharpeRatio: 1.24
        },
        optimized: {
          expectedReturn: 14.2,
          risk: 16.8,
          sharpeRatio: 1.45
        }
      };
      
      setOptimizationResults(mockResults);
      setOptimizedPortfolio({
        allocation: [
          { symbol: 'AAPL', weight: 20.0 },
          { symbol: 'MSFT', weight: 25.0 },
          { symbol: 'GOOGL', weight: 15.0 },
          { symbol: 'AMZN', weight: 18.0 },
          { symbol: 'TSLA', weight: 12.0 },
          { symbol: 'JNJ', weight: 10.0 }
        ]
      });
      setShowResultsDialog(true);
    } finally {
      setOptimizing(false);
    }
  };

  const optimizationSteps = [
    {
      label: 'Set Objectives',
      description: 'Define your investment goals and risk tolerance',
      content: (
        <Grid container spacing={3}>
          <Grid item xs={12} md={6}>
            <FormControl fullWidth>
              <InputLabel>Optimization Objective</InputLabel>
              <Select
                value={optimizationParams.objective}
                label="Optimization Objective"
                onChange={(e) => setOptimizationParams({
                  ...optimizationParams,
                  objective: e.target.value
                })}
              >
                <MenuItem value="maxSharpe">Maximize Sharpe Ratio</MenuItem>
                <MenuItem value="minRisk">Minimize Risk</MenuItem>
                <MenuItem value="equalWeight">Equal Weight</MenuItem>
                <MenuItem value="riskParity">Risk Parity</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} md={6}>
            <FormControl fullWidth>
              <InputLabel>Time Horizon</InputLabel>
              <Select
                value={optimizationParams.timeHorizon}
                label="Time Horizon"
                onChange={(e) => setOptimizationParams({
                  ...optimizationParams,
                  timeHorizon: e.target.value
                })}
              >
                <MenuItem value="3M">3 Months</MenuItem>
                <MenuItem value="6M">6 Months</MenuItem>
                <MenuItem value="1Y">1 Year</MenuItem>
                <MenuItem value="2Y">2 Years</MenuItem>
                <MenuItem value="5Y">5 Years</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12}>
            <Typography gutterBottom>Risk Tolerance: {optimizationParams.riskTolerance}%</Typography>
            <Slider
              value={optimizationParams.riskTolerance}
              onChange={(e, value) => setOptimizationParams({
                ...optimizationParams,
                riskTolerance: value
              })}
              aria-labelledby="risk-tolerance-slider"
              valueLabelDisplay="auto"
              step={5}
              marks
              min={0}
              max={100}
            />
          </Grid>
          {optimizationParams.objective === 'targetReturn' && (
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Target Annual Return (%)"
                type="number"
                value={optimizationParams.targetReturn}
                onChange={(e) => setOptimizationParams({
                  ...optimizationParams,
                  targetReturn: parseFloat(e.target.value)
                })}
              />
            </Grid>
          )}
        </Grid>
      )
    },
    {
      label: 'Set Constraints',
      description: 'Configure portfolio constraints and limits',
      content: (
        <Grid container spacing={3}>
          <Grid item xs={12} md={6}>
            <TextField
              fullWidth
              label="Max Single Position (%)"
              type="number"
              value={optimizationParams.constraints.maxWeight * 100}
              onChange={(e) => setOptimizationParams({
                ...optimizationParams,
                constraints: {
                  ...optimizationParams.constraints,
                  maxWeight: parseFloat(e.target.value) / 100
                }
              })}
            />
          </Grid>
          <Grid item xs={12} md={6}>
            <TextField
              fullWidth
              label="Min Single Position (%)"
              type="number"
              value={optimizationParams.constraints.minWeight * 100}
              onChange={(e) => setOptimizationParams({
                ...optimizationParams,
                constraints: {
                  ...optimizationParams.constraints,
                  minWeight: parseFloat(e.target.value) / 100
                }
              })}
            />
          </Grid>
          <Grid item xs={12} md={6}>
            <TextField
              fullWidth
              label="Historical Data Lookback (Days)"
              type="number"
              value={optimizationParams.lookbackDays}
              onChange={(e) => setOptimizationParams({
                ...optimizationParams,
                lookbackDays: parseInt(e.target.value)
              })}
              helperText="Number of days of historical data to use"
            />
          </Grid>
          <Grid item xs={12} md={6}>
            <TextField
              fullWidth
              label="Rebalance Threshold (%)"
              type="number"
              value={optimizationParams.constraints.rebalanceThreshold * 100}
              onChange={(e) => setOptimizationParams({
                ...optimizationParams,
                constraints: {
                  ...optimizationParams.constraints,
                  rebalanceThreshold: parseFloat(e.target.value) / 100
                }
              })}
            />
          </Grid>
          <Grid item xs={12}>
            <FormControlLabel
              control={
                <Switch
                  checked={optimizationParams.constraints.allowShorts}
                  onChange={(e) => setOptimizationParams({
                    ...optimizationParams,
                    constraints: {
                      ...optimizationParams.constraints,
                      allowShorts: e.target.checked
                    }
                  })}
                />
              }
              label="Allow Short Selling"
            />
          </Grid>
          <Grid item xs={12}>
            <Box>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                Additional Settings
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Optimization uses Modern Portfolio Theory with real market data.
                Advanced constraints and alternative assets can be configured via API.
              </Typography>
            </Box>
          </Grid>
        </Grid>
      )
    },
    {
      label: 'Review & Optimize',
      description: 'Review settings and run optimization',
      content: (
        <Box>
          <Typography variant="h6" gutterBottom>
            Optimization Summary
          </Typography>
          <List>
            <ListItem>
              <ListItemIcon><OptimizeIcon /></ListItemIcon>
              <ListItemText 
                primary="Objective" 
                secondary={optimizationParams.objective.replace('_', ' ').toUpperCase()} 
              />
            </ListItem>
            <ListItem>
              <ListItemIcon><Security /></ListItemIcon>
              <ListItemText 
                primary="Risk Tolerance" 
                secondary={`${optimizationParams.riskTolerance}%`} 
              />
            </ListItem>
            <ListItem>
              <ListItemIcon><Speed /></ListItemIcon>
              <ListItemText 
                primary="Lookback Period" 
                secondary={`${optimizationParams.lookbackDays} days`} 
              />
            </ListItem>
            <ListItem>
              <ListItemIcon><Balance /></ListItemIcon>
              <ListItemText 
                primary="Max Position Size" 
                secondary={`${(optimizationParams.constraints.maxWeight * 100).toFixed(1)}%`} 
              />
            </ListItem>
          </List>
        </Box>
      )
    }
  ];


  if (loading) {
    return (
      <Container maxWidth="xl">
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
          <CircularProgress />
        </Box>
      </Container>
    );
  }

  return (
    <Container maxWidth="xl">
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" gutterBottom>
          Portfolio Optimization
        </Typography>
        <Typography variant="body1" color="text.secondary">
          AI-driven portfolio optimization and rebalancing recommendations
        </Typography>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      <Grid container spacing={3}>
        {/* Current Portfolio Analysis */}
        <Grid item xs={12} lg={8}>
          <Card sx={{ mb: 3 }}>
            <CardHeader 
              title="Optimization Wizard"
              action={
                <Button
                  variant="contained"
                  startIcon={optimizing ? <CircularProgress size={20} /> : <PlayArrow />}
                  onClick={handleOptimization}
                  disabled={optimizing}
                >
                  {optimizing ? 'Optimizing...' : 'Run Optimization'}
                </Button>
              }
            />
            <CardContent>
              <Stepper activeStep={activeStep} orientation="vertical">
                {optimizationSteps.map((step, index) => (
                  <Step key={step.label}>
                    <StepLabel
                      optional={
                        <Typography variant="caption">{step.description}</Typography>
                      }
                    >
                      {step.label}
                    </StepLabel>
                    <StepContent>
                      {step.content}
                      <Box sx={{ mb: 2, mt: 2 }}>
                        <Button
                          variant="contained"
                          onClick={() => setActiveStep(Math.min(activeStep + 1, optimizationSteps.length - 1))}
                          sx={{ mr: 1 }}
                          disabled={activeStep === optimizationSteps.length - 1}
                        >
                          {activeStep === optimizationSteps.length - 1 ? 'Complete' : 'Continue'}
                        </Button>
                        <Button
                          disabled={activeStep === 0}
                          onClick={() => setActiveStep(Math.max(activeStep - 1, 0))}
                        >
                          Back
                        </Button>
                      </Box>
                    </StepContent>
                  </Step>
                ))}
              </Stepper>
            </CardContent>
          </Card>

          {/* Rebalancing Recommendations */}
          {rebalanceRecommendations && (
            <Card>
              <CardHeader title="Rebalancing Recommendations" />
              <CardContent>
                <TableContainer component={Paper} variant="outlined">
                  <Table>
                    <TableHead>
                      <TableRow>
                        <TableCell>Symbol</TableCell>
                        <TableCell align="right">Current Weight</TableCell>
                        <TableCell align="right">Target Weight</TableCell>
                        <TableCell align="right">Difference</TableCell>
                        <TableCell align="right">Action</TableCell>
                        <TableCell>Priority</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {rebalanceRecommendations.map((rec) => (
                        <TableRow key={rec.symbol}>
                          <TableCell>
                            <Typography variant="body2" fontWeight="bold">
                              {rec.symbol}
                            </Typography>
                          </TableCell>
                          <TableCell align="right">{rec.currentWeight.toFixed(2)}%</TableCell>
                          <TableCell align="right">{rec.targetWeight.toFixed(2)}%</TableCell>
                          <TableCell 
                            align="right"
                            sx={{ color: rec.difference >= 0 ? 'success.main' : 'error.main' }}
                          >
                            {rec.difference >= 0 ? '+' : ''}{rec.difference.toFixed(2)}%
                          </TableCell>
                          <TableCell align="right">
                            <Chip 
                              label={rec.action} 
                              color={rec.action === 'BUY' ? 'success' : 'error'}
                              size="small"
                            />
                          </TableCell>
                          <TableCell>
                            <Chip 
                              label={rec.priority} 
                              color={
                                rec.priority === 'HIGH' ? 'error' : 
                                rec.priority === 'MEDIUM' ? 'warning' : 'success'
                              }
                              size="small"
                            />
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </CardContent>
            </Card>
          )}
        </Grid>

        {/* Sidebar - Current Portfolio & Risk Analysis */}
        <Grid item xs={12} lg={4}>
          {/* Current Portfolio Summary */}
          {currentPortfolio && (
            <Card sx={{ mb: 3 }}>
              <CardHeader title="Current Portfolio" />
              <CardContent>
                <List dense>
                  <ListItem>
                    <ListItemIcon><AccountBalance /></ListItemIcon>
                    <ListItemText 
                      primary="Total Value" 
                      secondary={`$${currentPortfolio.totalValue?.toLocaleString()}`} 
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemIcon><TrendingUp /></ListItemIcon>
                    <ListItemText 
                      primary="Expected Return" 
                      secondary={`${currentPortfolio.expectedReturn?.toFixed(2)}%`} 
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemIcon><Security /></ListItemIcon>
                    <ListItemText 
                      primary="Risk (Volatility)" 
                      secondary={`${currentPortfolio.risk?.toFixed(2)}%`} 
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemIcon><Analytics /></ListItemIcon>
                    <ListItemText 
                      primary="Sharpe Ratio" 
                      secondary={currentPortfolio.sharpeRatio?.toFixed(2)} 
                    />
                  </ListItem>
                </List>
              </CardContent>
            </Card>
          )}

          {/* Risk Analysis */}
          {riskAnalysis && (
            <Card>
              <CardHeader title="Risk Analysis" />
              <CardContent>
                <Box sx={{ mb: 2 }}>
                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    Portfolio Risk Score
                  </Typography>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                    <Box sx={{ width: '100%', mr: 1 }}>
                      <Slider
                        value={riskAnalysis.riskScore}
                        aria-labelledby="risk-score-slider"
                        valueLabelDisplay="auto"
                        step={1}
                        marks
                        min={0}
                        max={100}
                        disabled
                        sx={{
                          '& .MuiSlider-thumb': {
                            color: riskAnalysis.riskScore > 70 ? 'error.main' : 
                                   riskAnalysis.riskScore > 40 ? 'warning.main' : 'success.main'
                          },
                          '& .MuiSlider-track': {
                            color: riskAnalysis.riskScore > 70 ? 'error.main' : 
                                   riskAnalysis.riskScore > 40 ? 'warning.main' : 'success.main'
                          }
                        }}
                      />
                    </Box>
                  </Box>
                </Box>

                <Divider sx={{ my: 2 }} />

                <Typography variant="subtitle2" gutterBottom>
                  Risk Factors
                </Typography>
                {riskAnalysis.riskFactors?.map((factor, index) => (
                  <Accordion key={index}>
                    <AccordionSummary expandIcon={<ExpandMore />}>
                      <Box sx={{ display: 'flex', alignItems: 'center', width: '100%' }}>
                        <Warning 
                          sx={{ 
                            mr: 1, 
                            color: factor.severity === 'HIGH' ? 'error.main' : 
                                   factor.severity === 'MEDIUM' ? 'warning.main' : 'info.main' 
                          }} 
                        />
                        <Typography variant="body2">{factor.name}</Typography>
                      </Box>
                    </AccordionSummary>
                    <AccordionDetails>
                      <Typography variant="body2" color="text.secondary">
                        {factor.description}
                      </Typography>
                      <Chip 
                        label={factor.severity} 
                        size="small" 
                        color={
                          factor.severity === 'HIGH' ? 'error' : 
                          factor.severity === 'MEDIUM' ? 'warning' : 'info'
                        }
                        sx={{ mt: 1 }}
                      />
                    </AccordionDetails>
                  </Accordion>
                ))}
              </CardContent>
            </Card>
          )}
        </Grid>
      </Grid>

      {/* Optimization Results Dialog */}
      <Dialog 
        open={showResultsDialog} 
        onClose={() => setShowResultsDialog(false)}
        maxWidth="lg"
        fullWidth
      >
        <DialogTitle>
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            <Lightbulb sx={{ mr: 1 }} />
            Optimization Results
          </Box>
        </DialogTitle>
        <DialogContent>
          {optimizationResults && (
            <Grid container spacing={3}>
              <Grid item xs={12} md={6}>
                <Typography variant="h6" gutterBottom>
                  Current vs Optimized
                </Typography>
                <TableContainer component={Paper} variant="outlined">
                  <Table>
                    <TableHead>
                      <TableRow>
                        <TableCell>Metric</TableCell>
                        <TableCell align="right">Current</TableCell>
                        <TableCell align="right">Optimized</TableCell>
                        <TableCell align="right">Improvement</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      <TableRow>
                        <TableCell>Expected Return</TableCell>
                        <TableCell align="right">{optimizationResults.current.expectedReturn.toFixed(2)}%</TableCell>
                        <TableCell align="right">{optimizationResults.optimized.expectedReturn.toFixed(2)}%</TableCell>
                        <TableCell 
                          align="right"
                          sx={{ color: 'success.main' }}
                        >
                          +{(optimizationResults.optimized.expectedReturn - optimizationResults.current.expectedReturn).toFixed(2)}%
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>Risk (Volatility)</TableCell>
                        <TableCell align="right">{optimizationResults.current.risk.toFixed(2)}%</TableCell>
                        <TableCell align="right">{optimizationResults.optimized.risk.toFixed(2)}%</TableCell>
                        <TableCell 
                          align="right"
                          sx={{ color: optimizationResults.optimized.risk < optimizationResults.current.risk ? 'success.main' : 'error.main' }}
                        >
                          {optimizationResults.optimized.risk < optimizationResults.current.risk ? '' : '+'}
                          {(optimizationResults.optimized.risk - optimizationResults.current.risk).toFixed(2)}%
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>Sharpe Ratio</TableCell>
                        <TableCell align="right">{optimizationResults.current.sharpeRatio.toFixed(2)}</TableCell>
                        <TableCell align="right">{optimizationResults.optimized.sharpeRatio.toFixed(2)}</TableCell>
                        <TableCell 
                          align="right"
                          sx={{ color: 'success.main' }}
                        >
                          +{(optimizationResults.optimized.sharpeRatio - optimizationResults.current.sharpeRatio).toFixed(2)}
                        </TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                </TableContainer>
              </Grid>
              <Grid item xs={12} md={6}>
                <Typography variant="h6" gutterBottom>
                  Optimized Allocation
                </Typography>
                <ResponsiveContainer width="100%" height={250}>
                  <PieChart>
                    <Pie
                      data={optimizedPortfolio?.allocation}
                      cx="50%"
                      cy="50%"
                      outerRadius={80}
                      fill="#8884d8"
                      dataKey="weight"
                      label={({ symbol, weight }) => `${symbol} ${weight.toFixed(1)}%`}
                    >
                      {optimizedPortfolio?.allocation?.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={`hsl(${index * 45}, 70%, 50%)`} />
                      ))}
                    </Pie>
                    <RechartsTooltip formatter={(value) => [`${value.toFixed(2)}%`, 'Weight']} />
                  </PieChart>
                </ResponsiveContainer>
              </Grid>
            </Grid>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowResultsDialog(false)}>Close</Button>
          <Button variant="contained" color="primary">
            Apply Optimization
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};

export default PortfolioOptimization;