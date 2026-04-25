import React from 'react';
import { Box, Typography, Button, Card, CardContent } from '@mui/material';
import { ErrorOutline, Refresh } from '@mui/icons-material';

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, errorId: null };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, info) {
    const errorId = Math.random().toString(36).slice(2, 10);
    this.setState({ errorId });
    // Forward to Sentry if available
    try {
      if (window.__SENTRY__) {
        window.__SENTRY__.captureException(error, { extra: { componentStack: info.componentStack } });
      }
    } catch {}
    console.error('[ErrorBoundary] Caught render error (id=%s):', errorId, error, info);
  }

  handleReload = () => {
    this.setState({ hasError: false, errorId: null });
    window.location.reload();
  };

  render() {
    if (!this.state.hasError) return this.props.children;

    return (
      <Box
        sx={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          bgcolor: 'background.default',
          p: 3,
        }}
      >
        <Card sx={{ maxWidth: 480, width: '100%', textAlign: 'center' }}>
          <CardContent sx={{ p: 4 }}>
            <ErrorOutline sx={{ fontSize: 56, color: 'error.main', mb: 2 }} />
            <Typography variant="h5" fontWeight={700} mb={1}>
              Something went wrong
            </Typography>
            <Typography variant="body2" color="text.secondary" mb={3}>
              An unexpected error occurred. Our team has been notified.
              {this.state.errorId && (
                <> Error ID: <code>{this.state.errorId}</code></>
              )}
            </Typography>
            <Button
              variant="contained"
              startIcon={<Refresh />}
              onClick={this.handleReload}
              sx={{ mr: 1 }}
            >
              Reload Page
            </Button>
            <Button variant="outlined" onClick={() => { window.location.href = '/dashboard'; }}>
              Go to Dashboard
            </Button>
          </CardContent>
        </Card>
      </Box>
    );
  }
}
