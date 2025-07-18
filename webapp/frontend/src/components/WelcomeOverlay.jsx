import React, { useState, useEffect } from 'react';
import {
  Box, Typography, Button, Fade, Slide, Card, CardContent, 
  Grid, Avatar, Chip, IconButton, LinearProgress, Stack
} from '@mui/material';
import {
  TrendingUp, Psychology, Security, Insights, Close, 
  ArrowForward, Dashboard, Timeline, AutoGraph
} from '@mui/icons-material';
import { useAuth } from '../contexts/AuthContext';

const WelcomeOverlay = ({ onClose }) => {
  const [currentStep, setCurrentStep] = useState(0);
  const [show, setShow] = useState(true);
  const { user } = useAuth();

  const steps = [
    {
      title: `Welcome back, ${user?.name || user?.email?.split('@')[0] || 'Trader'}!`,
      subtitle: "Your personalized financial intelligence dashboard is ready",
      icon: <Dashboard sx={{ fontSize: 60, color: '#1976d2' }} />,
      features: [
        { icon: <TrendingUp />, text: "Real-time market analysis" },
        { icon: <Psychology />, text: "AI-powered insights" },
        { icon: <Security />, text: "Institutional-grade security" }
      ]
    },
    {
      title: "Your Portfolio Intelligence",
      subtitle: "Advanced analytics and personalized recommendations",
      icon: <AutoGraph sx={{ fontSize: 60, color: '#43a047' }} />,
      features: [
        { icon: <Timeline />, text: "Advanced performance analytics" },
        { icon: <Insights />, text: "Smart trading signals" },
        { icon: <Psychology />, text: "Risk management tools" }
      ]
    }
  ];

  const handleNext = () => {
    if (currentStep < steps.length - 1) {
      setCurrentStep(currentStep + 1);
    } else {
      handleClose();
    }
  };

  const handleClose = () => {
    setShow(false);
    setTimeout(() => onClose(), 300);
  };

  // Auto-close after 8 seconds
  useEffect(() => {
    const timer = setTimeout(() => {
      handleClose();
    }, 8000);
    return () => clearTimeout(timer);
  }, []);

  if (!show) return null;

  const currentStepData = steps[currentStep];

  return (
    <Fade in={show} timeout={500}>
      <div 
        sx={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.8)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 2000,
          backdropFilter: 'blur(10px)'
        }}
      >
        <Slide direction="up" in={show} timeout={600}>
          <div className="bg-white shadow-md rounded-lg"
            sx={{
              maxWidth: 600,
              width: '90%',
              background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
              color: 'white',
              position: 'relative',
              borderRadius: 4,
              boxShadow: '0 20px 40px rgba(0,0,0,0.3)'
            }}
          >
            <button className="p-2 rounded-full hover:bg-gray-100"
              sx={{ position: 'absolute', top: 8, right: 8, color: 'white' }}
              onClick={handleClose}
            >
              <Close />
            </button>

            <div className="bg-white shadow-md rounded-lg"Content sx={{ p: 4, textAlign: 'center' }}>
              <div  sx={{ mb: 3 }}>
                {currentStepData.icon}
              </div>

              <div  variant="h4" component="h1" gutterBottom sx={{ fontWeight: 700, mb: 1 }}>
                {currentStepData.title}
              </div>

              <div  variant="h6" sx={{ mb: 4, opacity: 0.9 }}>
                {currentStepData.subtitle}
              </div>

              <div className="grid" container spacing={2} sx={{ mb: 4 }}>
                {currentStepData.features.map((feature, index) => (
                  <div className="grid" item xs={12} key={index}>
                    <Fade in={true} timeout={800 + index * 200}>
                      <div  sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                        <div  sx={{ 
                          backgroundColor: 'rgba(255,255,255,0.2)', 
                          borderRadius: '50%', 
                          p: 1,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center'
                        }}>
                          {feature.icon}
                        </div>
                        <div  variant="body1" sx={{ fontWeight: 500 }}>
                          {feature.text}
                        </div>
                      </div>
                    </Fade>
                  </div>
                ))}
              </div>

              <div className="flex flex-col space-y-2" direction="row" spacing={2} justifyContent="center" alignItems="center">
                <div className="w-full bg-gray-200 rounded-full h-2"
                  variant="determinate"
                  value={(currentStep + 1) / steps.length * 100}
                  sx={{
                    width: 100,
                    height: 6,
                    borderRadius: 3,
                    backgroundColor: 'rgba(255,255,255,0.3)',
                    '& .MuiLinearProgress-bar': {
                      backgroundColor: 'white',
                      borderRadius: 3
                    }
                  }}
                />
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  variant="contained"
                  onClick={handleNext}
                  endIcon={<ArrowForward />}
                  sx={{
                    backgroundColor: 'white',
                    color: '#1976d2',
                    px: 4,
                    py: 1.5,
                    borderRadius: 2,
                    '&:hover': {
                      backgroundColor: 'rgba(255,255,255,0.9)'
                    }
                  }}
                >
                  {currentStep === steps.length - 1 ? 'Get Started' : 'Next'}
                </button>
              </div>

              <div  variant="caption" sx={{ mt: 2, display: 'block', opacity: 0.7 }}>
                This overlay will close automatically in a few seconds
              </div>
            </div>
          </div>
        </Slide>
      </div>
    </Fade>
  );
};

export default WelcomeOverlay;