import React, { Suspense, useState } from 'react';
import { Box, Button, CircularProgress, Collapse, Stack, ToggleButton, ToggleButtonGroup } from '@mui/material';
import { VisibilityOutlined, VisibilityOffOutlined } from '@mui/icons-material';

// The renderers and Telegram/Discord parsers live in MessagePreviewImpl and are fetched only the first time a
// preview is opened, so pages that merely contain a (closed) preview do not pay for them.
const Impl = React.lazy(() => import('./MessagePreviewImpl'));

export function MessagePreview(props) {
  return (
    <Suspense fallback={<Box sx={{ display: 'flex', justifyContent: 'center', py: 2 }}><CircularProgress size={20} /></Box>}>
      <Impl {...props} />
    </Suspense>
  );
}

/**
 * Collapsible wrapper: the preview is only mounted while open, so a closed preview does no work.
 * Opening/closing never touches the form behind it.
 */
export function PreviewPanel({ children, label = 'Preview', platforms, platform, onPlatform, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Box sx={{ mt: 1.5 }}>
      <Stack direction="row" spacing={1} alignItems="center" useFlexGap flexWrap="wrap">
        <Button size="small" variant={open ? 'contained' : 'outlined'} aria-expanded={open}
          startIcon={open ? <VisibilityOffOutlined fontSize="small" /> : <VisibilityOutlined fontSize="small" />}
          onClick={() => setOpen((o) => !o)}>
          {open ? `Hide ${label.toLowerCase()}` : label}
        </Button>
        {open && platforms && platforms.length > 1 && (
          <ToggleButtonGroup size="small" exclusive value={platform} onChange={(_, v) => v && onPlatform(v)} aria-label="Preview platform">
            {platforms.map((p) => <ToggleButton key={p} value={p} sx={{ textTransform: 'none', px: 1.25 }}>{p === 'telegram' ? 'Telegram' : 'Discord'}</ToggleButton>)}
          </ToggleButtonGroup>
        )}
      </Stack>
      <Collapse in={open} unmountOnExit timeout={150}>
        <Box sx={{ mt: 1.25 }}>{children}</Box>
      </Collapse>
    </Box>
  );
}

export default MessagePreview;
