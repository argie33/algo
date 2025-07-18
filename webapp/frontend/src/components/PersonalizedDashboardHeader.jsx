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
    <div  sx={{ mb: 4 }}>
      <Fade in={showWelcome} timeout={1000}>
        <div className="bg-white shadow-md rounded-lg" 
          sx={{ 
            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
            color: 'white',
            position: 'relative',
            overflow: 'hidden',
            borderRadius: 3,
            boxShadow: '0 8px 32px rgba(0,0,0,0.1)'
          }}
        >
          <div 
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
          
          <div className="bg-white shadow-md rounded-lg"Content sx={{ p: 4 }}>
            <div  sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div  sx={{ flex: 1 }}>
                <Grow in={true} timeout={800}>
                  <div  variant="h4" component="h1" gutterBottom sx={{ fontWeight: 700 }}>
                    {getGreeting()}
                  </div>
                </Grow>
                
                <Grow in={true} timeout={1200}>
                  <div  variant="h6" sx={{ opacity: 0.9, mb: 3 }}>
                    {getMotivationalMessage()}
                  </div>
                </Grow>

                <div className="flex flex-col space-y-2" direction="row" spacing={1} sx={{ flexWrap: 'wrap', gap: 1 }}>
                  <Grow in={true} timeout={1000}>
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
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
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
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
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
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
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                      icon={<Star />} 
                      label="Premium" 
                      sx={{ 
                        backgroundColor: 'rgba(255,255,255,0.2)',
                        color: 'white',
                        '& .MuiChip-icon': { color: '#ff9800' }
                      }}
                    />
                  </Grow>
                </div>
              </div>

              <div  sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                <div  sx={{ 
                  '& .MuiIconButton-root': { 
                    backgroundColor: 'rgba(255,255,255,0.1)',
                    '&:hover': { backgroundColor: 'rgba(255,255,255,0.2)' }
                  },
                  '& .MuiSvgIcon-root': { color: 'white' }
                }}>
                  <NotificationSystem />
                </div>
                
                <div className="h-8 w-8 rounded-full bg-gray-300 flex items-center justify-center" 
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
                </div>
              </div>
            </div>
          </div>
        </div>
      </Fade>
    </div>
  );
};

export default PersonalizedDashboardHeader;