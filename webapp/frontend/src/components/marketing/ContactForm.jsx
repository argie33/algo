import React, { useState } from 'react';
import {
  Box,
  TextField,
  Button,
  CircularProgress,
  Alert,
  useTheme,
} from '@mui/material';

const ContactForm = ({ onSubmit }) => {
  const theme = useTheme();
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    subject: '',
    message: '',
  });
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState(null);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    // Basic validation
    if (!formData.name || !formData.email || !formData.message) {
      setError('Please fill in all required fields');
      setLoading(false);
      return;
    }

    // Email validation
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(formData.email)) {
      setError('Please enter a valid email address');
      setLoading(false);
      return;
    }

    try {
      if (onSubmit) {
        await onSubmit(formData);
      } else {
        // Default: log to console (can be replaced with actual API call)
        console.log('Form submitted:', formData);
      }

      setSubmitted(true);
      setFormData({ name: '', email: '', subject: '', message: '' });

      // Reset success message after 5 seconds
      setTimeout(() => {
        setSubmitted(false);
      }, 5000);
    } catch (err) {
      setError(err.message || 'Failed to submit form. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box
      component="form"
      onSubmit={handleSubmit}
      sx={{
        display: 'flex',
        flexDirection: 'column',
        gap: 2.5,
        maxWidth: '600px',
      }}
    >
      {submitted && (
        <Alert severity="success">
          Thank you for reaching out! We&apos;ll get back to you soon.
        </Alert>
      )}

      {error && (
        <Alert severity="error">{error}</Alert>
      )}

      <TextField
        fullWidth
        label="Your Name"
        name="name"
        value={formData.name}
        onChange={handleChange}
        placeholder="John Doe"
        required
        variant="outlined"
        sx={{
          '& .MuiOutlinedInput-root': {
            borderRadius: 1,
          },
        }}
      />

      <TextField
        fullWidth
        label="Email Address"
        name="email"
        type="email"
        value={formData.email}
        onChange={handleChange}
        placeholder="you@example.com"
        required
        variant="outlined"
        sx={{
          '& .MuiOutlinedInput-root': {
            borderRadius: 1,
          },
        }}
      />

      <TextField
        fullWidth
        label="Subject"
        name="subject"
        value={formData.subject}
        onChange={handleChange}
        placeholder="How can we help?"
        variant="outlined"
        sx={{
          '& .MuiOutlinedInput-root': {
            borderRadius: 1,
          },
        }}
      />

      <TextField
        fullWidth
        label="Message"
        name="message"
        value={formData.message}
        onChange={handleChange}
        placeholder="Tell us more about your inquiry..."
        required
        multiline
        rows={6}
        variant="outlined"
        sx={{
          '& .MuiOutlinedInput-root': {
            borderRadius: 1,
          },
        }}
      />

      <Button
        variant="contained"
        size="large"
        type="submit"
        disabled={loading}
        sx={{
          py: 1.5,
          fontSize: '1rem',
          fontWeight: 600,
          borderRadius: 1,
          textTransform: 'none',
          position: 'relative',
        }}
      >
        {loading ? (
          <>
            <CircularProgress size={20} sx={{ mr: 1 }} />
            Sending...
          </>
        ) : (
          'Send Message'
        )}
      </Button>
    </Box>
  );
};

export default ContactForm;
