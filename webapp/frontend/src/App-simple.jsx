import React, { useState } from 'react'
import { Routes, Route } from 'react-router-dom'
import { 
  AppBar, 
  Box, 
  Toolbar, 
  Typography, 
  Container,
  Button
} from '@mui/material'

// Simple pages that should work
import Dashboard from './pages/Dashboard'
import MarketOverview from './pages/MarketOverview'

console.log('🚀 App-simple.jsx loaded');

function App() {
  console.log('🚀 App component rendering');

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      {/* Simple Header */}
      <AppBar position="static">
        <Toolbar>
          <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
            Financial Dashboard - Simple Mode
          </Typography>
          <Button color="inherit">Dashboard</Button>
          <Button color="inherit">Market</Button>
        </Toolbar>
      </AppBar>

      {/* Main Content */}
      <Container maxWidth="xl" sx={{ mt: 2, flex: 1 }}>
        <Routes>
          <Route path="/" element={
            <div>
              <h1>✅ React App Working!</h1>
              <p>This is the simplified version without authentication.</p>
              <p>APIs are healthy and this proves the frontend can load.</p>
            </div>
          } />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/market" element={<MarketOverview />} />
          <Route path="*" element={
            <div>
              <h1>404 - Page Not Found</h1>
              <p>Go back to <a href="/">Dashboard</a></p>
            </div>
          } />
        </Routes>
      </Container>
    </Box>
  )
}

export default App