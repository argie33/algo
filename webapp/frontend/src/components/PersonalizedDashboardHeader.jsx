import React, { useState, useEffect } from 'react';
import {
  Box, Typography, Avatar, Chip, IconButton, Badge, 
  Card, CardContent, Grow, Fade, Button, Stack
} from '@mui/material';
import {
  TrendingUp, Psychology, Security, Insights,
  Timeline, AutoGraph, Speed, Bolt, Star, LocalFireDepartment
} from '@mui/icons-material';
import NotificationSystem from './NotificationSystem';
import { useAuth } from '../contexts/AuthContext';

const PersonalizedDashboardHeader = ({ onNotificationClick }) => {
  const [timeOfDay, setTimeOfDay] = useState('');
  const [showWelcome, setShowWelcome] = useState(true);
  const { user } = useAuth();

  useEffect(() => {
    const hour = new Date().getHours();
    if (hour < 12) setTimeOfDay('morning');
    else if (hour < 17) setTimeOfDay('afternoon');
    else setTimeOfDay('evening');
  }, []);

  const getGreeting = () => {
    const name = user?.name || user?.email?.split('@')[0] || 'Trader';
    return `Good ${timeOfDay}, ${name}!`;
  };

  const getMotivationalMessage = () => {
    const messages = [
      "Your portfolio is performing above market averages",
      "New opportunities detected in your watchlist",
      "Market volatility creates new trading opportunities",
      "AI signals show strong bullish momentum",
      "Your risk management is on point today"
    ];
    return messages[Math.floor(Math.random() * messages.length)];
  };

  return (
    <Box sx={{ mb: 4 }}>
      <Fade in={showWelcome} timeout={1000}>
        <Card 
          sx={{ 
            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
            color: 'white',
            position: 'relative',
            overflow: 'hidden',
            borderRadius: 3,
            boxShadow: '0 8px 32px rgba(0,0,0,0.1)'
          }}
        >
          <Box
            sx={{
              position: 'absolute',
              top: -50,
              right: -50,
              width: 200,
              height: 200,
              background: 'radial-gradient(circle, rgba(255,255,255,0.1) 0%, transparent 70%)',
              borderRadius: '50%'
            }}
          />
          
          <CardContent sx={{ p: 4 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <Box sx={{ flex: 1 }}>
                <Grow in={true} timeout={800}>
                  <Typography variant="h4" component="h1" gutterBottom sx={{ fontWeight: 700 }}>
                    {getGreeting()}
                  </Typography>
                </Grow>
                
                <Grow in={true} timeout={1200}>
                  <Typography variant="h6" sx={{ opacity: 0.9, mb: 3 }}>
                    {getMotivationalMessage()}
                  </Typography>
                </Grow>

                <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', gap: 1 }}>
                  <Grow in={true} timeout={1000}>
                    <Chip 
                      icon={<LocalFireDepartment />} 
                      label="Markets Open" 
                      sx={{ 
                        backgroundColor: 'rgba(255,255,255,0.2)',
                        color: 'white',
                        '& .MuiChip-icon': { color: '#ff6b35' }
                      }}
                    />
                  </Grow>
                  <Grow in={true} timeout={1200}>
                    <Chip 
                      icon={<Psychology />} 
                      label="AI Active" 
                      sx={{ 
                        backgroundColor: 'rgba(255,255,255,0.2)',
                        color: 'white',
                        '& .MuiChip-icon': { color: '#43a047' }
                      }}
                    />
                  </Grow>
                  <Grow in={true} timeout={1400}>
                    <Chip 
                      icon={<Security />} 
                      label="Secure" 
                      sx={{ 
                        backgroundColor: 'rgba(255,255,255,0.2)',
                        color: 'white',
                        '& .MuiChip-icon': { color: '#ffc107' }
                      }}
                    />
                  </Grow>
                  <Grow in={true} timeout={1600}>
                    <Chip 
                      icon={<Star />} 
                      label="Premium" 
                      sx={{ 
                        backgroundColor: 'rgba(255,255,255,0.2)',
                        color: 'white',
                        '& .MuiChip-icon': { color: '#ff9800' }
                      }}
                    />
                  </Grow>
                </Stack>
              </Box>

              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                <Box sx={{ 
                  '& .MuiIconButton-root': { 
                    backgroundColor: 'rgba(255,255,255,0.1)',
                    '&:hover': { backgroundColor: 'rgba(255,255,255,0.2)' }
                  },
                  '& .MuiSvgIcon-root': { color: 'white' }
                }}>
                  <NotificationSystem />
                </Box>
                
                <Avatar 
                  sx={{ 
                    bgcolor: 'rgba(255,255,255,0.2)', 
                    width: 56, 
                    height: 56,
                    fontSize: '1.5rem',
                    fontWeight: 700,
                    border: '2px solid rgba(255,255,255,0.3)'
                  }}
                >
                  {user?.name ? user.name[0] : (user?.email ? user.email[0] : 'U')}
                </Avatar>
              </Box>
            </Box>
          </CardContent>
        </Card>
      </Fade>
    </Box>
  );
};

export default PersonalizedDashboardHeader;