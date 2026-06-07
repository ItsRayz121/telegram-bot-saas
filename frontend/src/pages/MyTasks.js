import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box, Card, CardContent, Typography, Chip, Stack, CircularProgress, Alert,
} from '@mui/material';
import { Campaign as CampaignIcon, ChevronRight } from '@mui/icons-material';
import { engagementTasks } from '../services/api';

const SUB_CHIP = {
  pending: { label: 'Pending', color: 'warning' },
  verified: { label: 'Verified', color: 'success' },
  rejected: { label: 'Rejected', color: 'error' },
};

export default function MyTasks() {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    (async () => {
      try {
        const res = await engagementTasks.myTasks();
        setTasks(res.data.tasks || []);
      } catch {
        setTasks([]);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <Box sx={{ maxWidth: 560, mx: 'auto', p: 2, pb: 'calc(var(--bottom-nav-clearance, 16px))' }}>
      <Typography variant="h6" fontWeight={700} sx={{ mb: 2 }}>My Tasks</Typography>
      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}><CircularProgress /></Box>
      ) : tasks.length === 0 ? (
        <Alert severity="info">No tasks available right now. Check your groups for active campaigns.</Alert>
      ) : (
        <Stack spacing={1.5}>
          {tasks.map((t) => {
            const sub = t.my_submission;
            const chip = sub ? (SUB_CHIP[sub.status] || { label: sub.status, color: 'default' }) : null;
            return (
              <Card key={t.id} variant="outlined" sx={{ cursor: 'pointer' }} onClick={() => navigate(`/task/${t.id}`)}>
                <CardContent sx={{ display: 'flex', alignItems: 'center', gap: 1.5, '&:last-child': { pb: 2 } }}>
                  <CampaignIcon color={t.is_open ? 'primary' : 'disabled'} />
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Typography variant="body1" fontWeight={600} noWrap>{t.title}</Typography>
                    <Stack direction="row" spacing={0.5} sx={{ mt: 0.5, flexWrap: 'wrap', gap: 0.5 }}>
                      <Chip size="small" label={t.is_open ? 'Active' : 'Closed'} color={t.is_open ? 'success' : 'default'} />
                      {chip && <Chip size="small" label={chip.label} color={chip.color} />}
                      {t.reward_label && <Chip size="small" variant="outlined" label={t.reward_label} />}
                    </Stack>
                  </Box>
                  <ChevronRight color="action" />
                </CardContent>
              </Card>
            );
          })}
        </Stack>
      )}
    </Box>
  );
}
