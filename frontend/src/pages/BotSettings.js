import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, AppBar, Toolbar, Typography, Button, Card, CardContent,
  CardActionArea, Grid, Chip, CircularProgress, IconButton,
} from '@mui/material';
import { ArrowBack, Group, Settings } from '@mui/icons-material';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'react-toastify';
import { bots } from '../services/api';

export default function BotSettings() {
  const navigate = useNavigate();
  const { id } = useParams();
  const [bot, setBot] = useState(null);
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const [botRes, groupsRes] = await Promise.all([
        bots.get(id),
        bots.getGroups(id),
      ]);
      setBot(botRes.data.bot);
      setGroups(groupsRes.data.groups);
    } catch {
      toast.error('Failed to load bot data');
      navigate('/dashboard');
    } finally {
      setLoading(false);
    }
  }, [id, navigate]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh' }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <AppBar position="sticky" elevation={0} sx={{ borderBottom: '1px solid', borderColor: 'divider' }}>
        <Toolbar>
          <IconButton edge="start" onClick={() => navigate('/dashboard')} sx={{ mr: 1 }}>
            <ArrowBack />
          </IconButton>
          <Typography variant="h6" fontWeight={600} sx={{ flexGrow: 1 }}>
            {bot?.bot_name}
          </Typography>
          <Chip
            label={bot?.is_active ? 'Active' : 'Stopped'}
            color={bot?.is_active ? 'success' : 'default'}
            size="small"
          />
        </Toolbar>
      </AppBar>

      <Box sx={{ maxWidth: 1200, mx: 'auto', p: 3 }}>
        <Typography variant="h6" fontWeight={600} mb={2}>
          Groups ({groups.length})
        </Typography>

        {groups.length === 0 ? (
          <Card sx={{ textAlign: 'center', py: 8 }}>
            <Group sx={{ fontSize: 64, color: 'text.disabled', mb: 2 }} />
            <Typography variant="h6" color="text.secondary" mb={1}>
              No groups yet
            </Typography>
            <Typography variant="body2" color="text.disabled">
              Add your bot to a Telegram group to manage it here.
            </Typography>
          </Card>
        ) : (
          <Grid container spacing={2}>
            {groups.map((group) => (
              <Grid item xs={12} sm={6} md={4} key={group.id}>
                <Card>
                  <CardActionArea onClick={() => navigate(`/bot/${id}/group/${group.id}`)}>
                    <CardContent>
                      <Box sx={{ display: 'flex', alignItems: 'flex-start', mb: 1 }}>
                        <Box
                          sx={{
                            width: 44, height: 44, borderRadius: 2,
                            bgcolor: 'primary.main', display: 'flex',
                            alignItems: 'center', justifyContent: 'center', mr: 1.5, flexShrink: 0,
                          }}
                        >
                          <Group />
                        </Box>
                        <Box>
                          <Typography variant="subtitle1" fontWeight={600}>
                            {group.group_name || 'Unknown Group'}
                          </Typography>
                          <Typography variant="body2" color="text.secondary">
                            {group.member_count} members
                          </Typography>
                        </Box>
                      </Box>
                      <Button
                        size="small"
                        startIcon={<Settings />}
                        variant="outlined"
                        fullWidth
                        sx={{ mt: 1 }}
                        onClick={(e) => {
                          e.stopPropagation();
                          navigate(`/bot/${id}/group/${group.id}`);
                        }}
                      >
                        Manage Settings
                      </Button>
                    </CardContent>
                  </CardActionArea>
                </Card>
              </Grid>
            ))}
          </Grid>
        )}
      </Box>
    </Box>
  );
}
