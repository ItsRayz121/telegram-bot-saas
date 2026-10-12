import React from 'react';
import { Box, Typography, Button, Card, CardContent, Divider, IconButton, Tooltip } from '@mui/material';
import { ErrorOutline, Refresh, ContentCopy, OpenInNew } from '@mui/icons-material';
import TelegizerLogo from './TelegizerLogo';

// A page/script chunk that failed to download (offline, flaky network, or a stale tab after a deploy) is
// a connectivity problem, not an application bug, and should not be reported or worded as one.
export function isChunkLoadError(error) {
  const msg = `${error?.name || ''} ${error?.message || ''}`;
  return /ChunkLoadError|Loading chunk [\w-]+ failed|Loading CSS chunk|Failed to fetch dynamically imported module|Importing a module script failed/i.test(msg);
}

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, errorId: null, copied: false, loadFailure: false };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, loadFailure: isChunkLoadError(error) };
  }

  componentDidCatch(error, info) {
    const errorId = Math.random().toString(36).slice(2, 10).toUpperCase();
    this.setState({ errorId });
    if (!isChunkLoadError(error)) {
      try {
        import('@sentry/react')
          .then(({ captureException }) => captureException(error, {
            extra: { componentStack: info?.componentStack, errorId },
          }))
          .catch(() => {});
      } catch {}
    }
    console.error('[ErrorBoundary] Caught render error (id=%s):', errorId, error, info);
  }

  handleReload = () => {
    this.setState({ hasError: false, errorId: null, copied: false });
    window.location.reload();
  };

  handleCopy = () => {
    if (this.state.errorId) {
      navigator.clipboard.writeText(this.state.errorId).catch(() => {});
      this.setState({ copied: true });
      setTimeout(() => this.setState({ copied: false }), 2000);
    }
  };

  render() {
    if (!this.state.hasError) return this.props.children;

    const { errorId, copied, loadFailure } = this.state;

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
            <Box sx={{ display: 'flex', justifyContent: 'center', mb: 2 }}>
              <TelegizerLogo size={36} />
            </Box>
            <ErrorOutline sx={{ fontSize: 40, color: 'error.main', mb: 2 }} />
            <Typography variant="h5" fontWeight={700} mb={1}>
              {loadFailure ? "This page didn't load" : 'Something went wrong'}
            </Typography>
            <Typography variant="body2" color="text.secondary" mb={2}>
              {loadFailure
                ? 'Part of the page could not be downloaded. Check your connection and reload — a newer version may also have been released.'
                : "We've been notified and are working on a fix. Try reloading — if the problem persists, check the status page or contact support."}
            </Typography>

            {errorId && (
              <>
                <Divider sx={{ my: 2 }} />
                <Box
                  sx={{
                    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 1,
                    bgcolor: 'rgba(255,255,255,0.04)', borderRadius: 1, px: 2, py: 1,
                  }}
                >
                  <Typography variant="caption" color="text.disabled">Error ID:</Typography>
                  <Typography variant="caption" fontFamily="monospace" fontWeight={600}>
                    {errorId}
                  </Typography>
                  <Tooltip title={copied ? 'Copied!' : 'Copy error ID'}>
                    <IconButton size="small" onClick={this.handleCopy} sx={{ color: 'text.disabled' }}>
                      <ContentCopy sx={{ fontSize: 14 }} />
                    </IconButton>
                  </Tooltip>
                </Box>
                <Divider sx={{ my: 2 }} />
              </>
            )}

            <Box sx={{ display: 'flex', gap: 1, justifyContent: 'center', flexWrap: 'wrap' }}>
              <Button variant="contained" startIcon={<Refresh />} onClick={this.handleReload}>
                Reload Page
              </Button>
              <Button variant="outlined" onClick={() => { window.location.href = '/dashboard'; }}>
                Go to Dashboard
              </Button>
              <Button
                variant="text"
                size="small"
                endIcon={<OpenInNew sx={{ fontSize: 14 }} />}
                onClick={() => { window.open('/status', '_blank', 'noopener,noreferrer'); }}
                sx={{ color: 'text.secondary' }}
              >
                Status Page
              </Button>
            </Box>
          </CardContent>
        </Card>
      </Box>
    );
  }
}
