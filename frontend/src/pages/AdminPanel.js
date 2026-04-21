import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, AppBar, Toolbar, Typography, IconButton, Card, CardContent,
  Grid, CircularProgress, TextField, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, Paper, Chip, Button, Dialog,
  DialogTitle, DialogContent, DialogActions, MenuItem, Select,
  FormControl, InputLabel, Pagination, InputAdornment,
} from '@mui/material';
import { ArrowBack, Search, Block, CheckCircle, Delete } from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { toast } from 'react-toastify';
import { admin } from '../services/api';

function StatCard({ label, value, color = '#2196f3' }) {
  return (
    <Card>
      <CardContent>
        <Typography variant="h4" fontWeight={700} sx={{ color }}>{value?.toLocaleString()}</Typography>
        <Typography variant="body2" color="text.secondary">{label}</Typography>
      </CardContent>
    </Card>
  );
}

export default function AdminPanel() {
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [users, setUsers] = useState([]);
  const [usersTotal, setUsersTotal] = useState(0);
  const [usersPages, setUsersPages] = useState(1);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [selectedUser, setSelectedUser] = useState(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [subTier, setSubTier] = useState('');
  const [actionLoading, setActionLoading] = useState('');

  const fetchStats = useCallback(async () => {
    try {
      const res = await admin.getStats();
      setStats(res.data.stats);
    } catch {
      toast.error('Failed to load stats');
    }
  }, []);

  const fetchUsers = useCallback(async (p = 1, s = '') => {
    try {
      const res = await admin.getUsers({ page: p, per_page: 20, search: s });
      setUsers(res.data.users);
      setUsersTotal(res.data.total);
      setUsersPages(res.data.pages);
    } catch {
      toast.error('Failed to load users');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStats();
    fetchUsers();
  }, [fetchStats, fetchUsers]);

  const handleSearch = (e) => {
    const val = e.target.value;
    setSearch(val);
    setPage(1);
    fetchUsers(1, val);
  };

  const handlePageChange = (_, p) => {
    setPage(p);
    fetchUsers(p, search);
  };

  const openDetail = async (user) => {
    try {
      const res = await admin.getUser(user.id);
      setSelectedUser(res.data.user);
      setSubTier(res.data.user.subscription_tier);
      setDetailOpen(true);
    } catch {
      toast.error('Failed to load user details');
    }
  };

  const handleUpdateSub = async () => {
    setActionLoading('sub');
    try {
      await admin.updateSubscription(selectedUser.id, { tier: subTier });
      toast.success('Subscription updated');
      setDetailOpen(false);
      fetchUsers(page, search);
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to update subscription');
    } finally {
      setActionLoading('');
    }
  };

  const handleBan = async (user) => {
    setActionLoading(`ban-${user.id}`);
    try {
      await admin.banUser(user.id, { reason: 'Admin action' });
      toast.success('User banned');
      setDetailOpen(false);
      fetchUsers(page, search);
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to ban user');
    } finally {
      setActionLoading('');
    }
  };

  const handleUnban = async (user) => {
    setActionLoading(`unban-${user.id}`);
    try {
      await admin.unbanUser(user.id);
      toast.success('User unbanned');
      setDetailOpen(false);
      fetchUsers(page, search);
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to unban user');
    } finally {
      setActionLoading('');
    }
  };

  const handleDelete = async (user) => {
    if (!window.confirm(`Delete ${user.email}? This cannot be undone.`)) return;
    setActionLoading(`del-${user.id}`);
    try {
      await admin.deleteUser(user.id);
      toast.success('User deleted');
      setDetailOpen(false);
      fetchUsers(page, search);
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to delete user');
    } finally {
      setActionLoading('');
    }
  };

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <AppBar position="sticky" elevation={0} sx={{ borderBottom: '1px solid', borderColor: 'divider' }}>
        <Toolbar>
          <IconButton edge="start" onClick={() => navigate('/dashboard')} sx={{ mr: 1 }}>
            <ArrowBack />
          </IconButton>
          <Typography variant="h6" fontWeight={600}>Admin Panel</Typography>
        </Toolbar>
      </AppBar>

      <Box sx={{ maxWidth: 1200, mx: 'auto', p: 3 }}>
        {stats && (
          <Grid container spacing={2} mb={4}>
            <Grid item xs={6} md={3}><StatCard label="Total Users" value={stats.total_users} /></Grid>
            <Grid item xs={6} md={3}><StatCard label="Pro Users" value={stats.pro_users} color="#7c4dff" /></Grid>
            <Grid item xs={6} md={3}><StatCard label="Total Bots" value={stats.total_bots} color="#00bcd4" /></Grid>
            <Grid item xs={6} md={3}><StatCard label="Total Groups" value={stats.total_groups} color="#4caf50" /></Grid>
          </Grid>
        )}

        <Typography variant="h6" fontWeight={600} mb={2}>User Management</Typography>

        <TextField
          fullWidth
          placeholder="Search by email or name..."
          value={search}
          onChange={handleSearch}
          sx={{ mb: 2 }}
          InputProps={{
            startAdornment: <InputAdornment position="start"><Search /></InputAdornment>,
          }}
        />

        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}>
            <CircularProgress />
          </Box>
        ) : (
          <>
            <TableContainer component={Paper} sx={{ border: '1px solid', borderColor: 'divider', mb: 2 }}>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>User</TableCell>
                    <TableCell>Plan</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Joined</TableCell>
                    <TableCell align="right">Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {users.map((u) => (
                    <TableRow key={u.id} hover>
                      <TableCell>
                        <Typography variant="body2" fontWeight={500}>{u.full_name}</Typography>
                        <Typography variant="caption" color="text.secondary">{u.email}</Typography>
                      </TableCell>
                      <TableCell>
                        <Chip
                          label={u.subscription_tier?.toUpperCase()}
                          size="small"
                          color={u.subscription_tier === 'enterprise' ? 'secondary' : u.subscription_tier === 'pro' ? 'primary' : 'default'}
                        />
                      </TableCell>
                      <TableCell>
                        {u.is_banned ? (
                          <Chip label="Banned" color="error" size="small" />
                        ) : (
                          <Chip label="Active" color="success" size="small" />
                        )}
                      </TableCell>
                      <TableCell>
                        <Typography variant="caption" color="text.secondary">
                          {new Date(u.created_at).toLocaleDateString()}
                        </Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Button size="small" onClick={() => openDetail(u)}>Details</Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>

            {usersPages > 1 && (
              <Box sx={{ display: 'flex', justifyContent: 'center' }}>
                <Pagination count={usersPages} page={page} onChange={handlePageChange} color="primary" />
              </Box>
            )}
          </>
        )}
      </Box>

      <Dialog open={detailOpen} onClose={() => setDetailOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>User: {selectedUser?.email}</DialogTitle>
        <DialogContent>
          {selectedUser && (
            <Box>
              <Typography variant="body2" color="text.secondary" mb={2}>
                ID: {selectedUser.id} · Joined {new Date(selectedUser.created_at).toLocaleDateString()}
                · {selectedUser.bots?.length || 0} bots
              </Typography>

              <FormControl fullWidth sx={{ mb: 2 }}>
                <InputLabel>Subscription Tier</InputLabel>
                <Select value={subTier} label="Subscription Tier" onChange={(e) => setSubTier(e.target.value)}>
                  <MenuItem value="free">Free</MenuItem>
                  <MenuItem value="pro">Pro</MenuItem>
                  <MenuItem value="enterprise">Enterprise</MenuItem>
                </Select>
              </FormControl>

              <Button
                variant="outlined"
                fullWidth
                onClick={handleUpdateSub}
                disabled={actionLoading === 'sub'}
                sx={{ mb: 2 }}
              >
                {actionLoading === 'sub' ? <CircularProgress size={20} /> : 'Update Subscription'}
              </Button>

              <Grid container spacing={1}>
                {selectedUser.is_banned ? (
                  <Grid item xs={6}>
                    <Button
                      fullWidth
                      variant="outlined"
                      color="success"
                      startIcon={<CheckCircle />}
                      onClick={() => handleUnban(selectedUser)}
                      disabled={!!actionLoading}
                    >
                      Unban
                    </Button>
                  </Grid>
                ) : (
                  <Grid item xs={6}>
                    <Button
                      fullWidth
                      variant="outlined"
                      color="warning"
                      startIcon={<Block />}
                      onClick={() => handleBan(selectedUser)}
                      disabled={!!actionLoading}
                    >
                      Ban
                    </Button>
                  </Grid>
                )}
                <Grid item xs={6}>
                  <Button
                    fullWidth
                    variant="outlined"
                    color="error"
                    startIcon={<Delete />}
                    onClick={() => handleDelete(selectedUser)}
                    disabled={!!actionLoading}
                  >
                    Delete
                  </Button>
                </Grid>
              </Grid>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDetailOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
