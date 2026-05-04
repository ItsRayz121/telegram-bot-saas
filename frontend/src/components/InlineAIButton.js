import React, { useState } from 'react';
import {
  Button, Dialog, DialogTitle, DialogContent, DialogActions,
  IconButton, Menu, MenuItem, CircularProgress, Typography,
  Box, Tooltip,
} from '@mui/material';
import { AutoAwesome, ContentCopy, Close } from '@mui/icons-material';
import { toast } from 'react-toastify';
import { assistant } from '../services/api';

const ACTION_LABELS = {
  summarize: 'Summarize',
  suggest_automod: 'Suggest automod rules',
  write_announcement: 'Write announcement',
  explain: 'Explain this',
  improve_message: 'Improve this message',
};

export default function InlineAIButton({
  context,           // string — the text/messages to process
  actions = ['summarize'],
  size = 'small',
  variant = 'outlined',
  label = 'AI',
  sx = {},
}) {
  const [anchorEl, setAnchorEl] = useState(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [activeAction, setActiveAction] = useState(null);

  const handleAction = async (action) => {
    setAnchorEl(null);
    if (!context?.trim()) {
      toast.warning('No content to process.');
      return;
    }
    setLoading(true);
    setActiveAction(action);
    setResult(null);
    try {
      const res = await assistant.inlineAI(action, context);
      setResult(res.data.result);
    } catch (e) {
      toast.error(e?.response?.data?.error || 'AI request failed. Check your AI settings.');
    } finally {
      setLoading(false);
    }
  };

  const copy = () => {
    navigator.clipboard.writeText(result || '');
    toast.success('Copied to clipboard');
  };

  const isSingleAction = actions.length === 1;

  return (
    <>
      <Tooltip title={isSingleAction ? ACTION_LABELS[actions[0]] : 'AI actions'}>
        <Button
          size={size}
          variant={variant}
          startIcon={loading ? <CircularProgress size={14} /> : <AutoAwesome fontSize="small" />}
          onClick={isSingleAction
            ? () => handleAction(actions[0])
            : (e) => setAnchorEl(e.currentTarget)
          }
          disabled={loading}
          sx={{ textTransform: 'none', ...sx }}
        >
          {loading ? 'Thinking…' : label}
        </Button>
      </Tooltip>

      {!isSingleAction && (
        <Menu anchorEl={anchorEl} open={Boolean(anchorEl)} onClose={() => setAnchorEl(null)}>
          {actions.map(action => (
            <MenuItem key={action} onClick={() => handleAction(action)}>
              {ACTION_LABELS[action] || action}
            </MenuItem>
          ))}
        </Menu>
      )}

      <Dialog open={Boolean(result)} onClose={() => setResult(null)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <AutoAwesome fontSize="small" color="primary" />
            <Typography variant="subtitle1" fontWeight={600}>
              {ACTION_LABELS[activeAction] || 'AI Result'}
            </Typography>
          </Box>
          <IconButton size="small" onClick={() => setResult(null)}><Close fontSize="small" /></IconButton>
        </DialogTitle>
        <DialogContent dividers>
          <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', lineHeight: 1.8 }}>
            {result}
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button startIcon={<ContentCopy fontSize="small" />} onClick={copy} size="small">
            Copy
          </Button>
          <Button onClick={() => setResult(null)} size="small">Close</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
