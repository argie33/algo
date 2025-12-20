import React, { useState } from "react";
import {
  Box,
  TextField,
  Button,
  Alert,
  Typography,
  Paper,
  Grid,
} from "@mui/material";

function GreeksDisplay() {
  const [symbol, setSymbol] = useState("");
  const [strike, setStrike] = useState("");
  const [daysToExp, setDaysToExp] = useState("30");
  const [impliedVol, setImpliedVol] = useState("20");

  return (
    <Box>
      <Paper sx={{ p: 2, mb: 3 }}>
        <Typography variant="h6" sx={{ mb: 2 }}>
          Black-Scholes Greeks Calculator
        </Typography>

        <Grid container spacing={2} sx={{ mb: 3 }}>
          <Grid item xs={12} sm={6} md={3}>
            <TextField
              label="Symbol"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              placeholder="e.g., AAPL"
              size="small"
              fullWidth
            />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <TextField
              label="Strike Price"
              type="number"
              value={strike}
              onChange={(e) => setStrike(e.target.value)}
              placeholder="e.g., 180"
              size="small"
              fullWidth
              inputProps={{ step: 0.01 }}
            />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <TextField
              label="Days to Expiration"
              type="number"
              value={daysToExp}
              onChange={(e) => setDaysToExp(e.target.value)}
              size="small"
              fullWidth
              inputProps={{ min: 1 }}
            />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <TextField
              label="Implied Volatility (%)"
              type="number"
              value={impliedVol}
              onChange={(e) => setImpliedVol(e.target.value)}
              size="small"
              fullWidth
              inputProps={{ min: 0, step: 0.1 }}
            />
          </Grid>
        </Grid>

        <Button variant="contained" disabled sx={{ mb: 2 }}>
          Calculate Greeks
        </Button>

        <Alert severity="info">
          This tool allows you to calculate option Greeks (Delta, Gamma, Theta, Vega, Rho) using the Black-Scholes-Merton model. Enter the option parameters and view detailed Greeks analysis. Coming soon.
        </Alert>
      </Paper>
    </Box>
  );
}

export default GreeksDisplay;
