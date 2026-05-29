import React, { useState, useCallback, useRef } from 'react';
import {
  Box, InputBase, Paper, List, ListItem, ListItemText, ListItemIcon,
  Typography, Chip, CircularProgress, ClickAwayListener,
} from '@mui/material';
import {
  Search, Event, Notifications, Notes, CheckBox, Group,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { assistant } from '../services/api';

const TYPE_ICON = {
  meeting: <Event fontSize="small" color="primary" />,
  reminder: <Notifications fontSize="small" color="warning" />,
  note: <Notes fontSize="small" color="success" />,
  task: <CheckBox fontSize="small" color="info" />,
  group: <Group fontSize="small" color="secondary" />,
};

const TYPE_COLOR = {
  meeting: 'primary',
  reminder: 'warning',
  note: 'success',
  task: 'info',
  group: 'secondary',
};

const TYPE_ROUTE = {
  meeting: null,         // no dedicated page yet — navigate to assistant hub
  reminder: '/assistant/reminders',
  note: '/assistant/notes',
  task: '/workspace/tasks',
  group: null,
};

export default function UniversalSearchBar({ placeholder = 'Search everything…', sx = {} }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const debounceRef = useRef(null);
  const navigate = useNavigate();

  const search = useCallback(async (q) => {
    if (!q.trim() || q.length < 2) { setResults([]); return; }
    setLoading(true);
    try {
      const res = await assistant.search(q);
      setResults(res.data.results || []);
      setOpen(true);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleChange = (e) => {
    const q = e.target.value;
    setQuery(q);
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => search(q), 350);
  };

  const handleSelect = (result) => {
    setOpen(false);
    setQuery('');
    const route = TYPE_ROUTE[result._type];
    if (route) navigate(route);
  };

  return (
    <ClickAwayListener onClickAway={() => setOpen(false)}>
      <Box sx={{ position: 'relative', ...sx }}>
        <Paper
          elevation={0}
          sx={{
            display: 'flex',
            alignItems: 'center',
            px: 2,
            py: 0.5,
            border: '1px solid',
            borderColor: 'divider',
            borderRadius: 2,
            bgcolor: 'background.paper',
          }}
        >
          {loading ? <CircularProgress size={18} sx={{ mr: 1 }} /> : <Search fontSize="small" sx={{ mr: 1, color: 'text.disabled' }} />}
          <InputBase
            value={query}
            onChange={handleChange}
            onFocus={() => results.length > 0 && setOpen(true)}
            placeholder={placeholder}
            sx={{ flex: 1, fontSize: 14 }}
          />
        </Paper>

        {open && results.length > 0 && (
          <Paper
            elevation={8}
            sx={{
              position: 'absolute',
              top: '100%',
              left: 0,
              right: 0,
              zIndex: 1400,
              mt: 0.5,
              maxHeight: 400,
              overflowY: 'auto',
              borderRadius: 2,
            }}
          >
            <List dense disablePadding>
              {results.map((r, i) => (
                <ListItem
                  key={i}
                  button
                  onClick={() => handleSelect(r)}
                  sx={{ borderBottom: '1px solid', borderColor: 'divider', '&:last-child': { borderBottom: 0 } }}
                >
                  <ListItemIcon sx={{ minWidth: 36 }}>{TYPE_ICON[r._type] || <Search fontSize="small" />}</ListItemIcon>
                  <ListItemText
                    primary={<Typography variant="body2" fontWeight={500} noWrap>{r._label}</Typography>}
                    secondary={
                      <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center', mt: 0.25 }}>
                        <Chip label={r._type} size="small" color={TYPE_COLOR[r._type] || 'default'} sx={{ height: 16, fontSize: 10 }} />
                        {r._date && (
                          <Typography variant="caption" color="text.disabled">
                            {new Date(r._date).toLocaleDateString()}
                          </Typography>
                        )}
                        {r.health_status && (
                          <Typography variant="caption" color="text.disabled">
                            {r.health_status === 'active' || r.health_status === 'recovering' || r.health_status === 'starting' || r.health_status === 'warning' || r.health_status === 'unknown' ? 'Active' :
                             r.health_status === 'idle' ? 'Idle' :
                             r.health_status === 'offline' || r.health_status === 'stopped' ? 'Offline' :
                             r.health_status === 'unreachable' || r.health_status === 'error' ? 'Unreachable' : 'Active'}
                          </Typography>
                        )}
                      </Box>
                    }
                  />
                </ListItem>
              ))}
            </List>
            {results.length === 0 && (
              <Box sx={{ p: 2, textAlign: 'center' }}>
                <Typography variant="body2" color="text.disabled">No results found</Typography>
              </Box>
            )}
          </Paper>
        )}
      </Box>
    </ClickAwayListener>
  );
}
