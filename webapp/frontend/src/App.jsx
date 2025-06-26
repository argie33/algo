import React from 'react'
import { Routes, Route } from 'react-router-dom'
import { 
  Box, 
  Typography,
  Container
} from '@mui/material'

// Simple test component to isolate the issue
const TestDashboard = () => (
  <Box sx={{ p: 3 }}>
    <Typography variant="h4">Test Dashboard</Typography>
    <Typography variant="body1">This is a simple test to isolate React error #300</Typography>
  </Box>
)

function App() {
  console.log('🚀 App component loading...');

  return (
    <Container maxWidth="xl">
      <Routes>
        <Route path="/" element={<TestDashboard />} />
        <Route path="*" element={<TestDashboard />} />
      </Routes>
    </Container>
  )
}

export default App
