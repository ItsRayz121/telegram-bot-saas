// ── FEATURE FLAG: Marketplace is temporarily hidden for future reactivation ───
// All backend routes, DB schema, and API calls below are fully preserved.
// To re-enable: set SHOW_MARKETPLACE = true or remove the feature flag block.
const SHOW_MARKETPLACE = false;

import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Card, CardContent, Button, Chip, Grid,
  TextField, InputAdornment, Select, MenuItem, FormControl,
  InputLabel, CircularProgress, Avatar, Stack, Divider,
  Dialog, DialogTitle, DialogContent, DialogActions,
  ToggleButton, ToggleButtonGroup, Alert, Tabs, Tab,
} from '@mui/material';
import {
  Handshake, Search, Campaign, Groups, People, Shield,
  AttachMoney, Add, OpenInNew, CheckCircle, Schedule,
  TrendingUp, Gavel,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { toast } from 'react-toastify';
import { marketplace as mktApi } from '../services/api';
import ComingSoonPage from '../components/ComingSoonPage';

const CATEGORIES = [
  "All", "Technology & Dev", "Crypto & Web3", "News & Politics",
  "Business & Finance", "Education & Learning", "Entertainment",
  "Gaming", "Health & Wellness", "Sports", "Art & Design", "Other",
];

const STATUS_COLOR = {
  pending: 'warning', accepted: 'info', in_progress: 'primary',
  delivered: 'secondary', completed: 'success',
  declined: 'error', disputed: 'error', cancelled: 'default',
};

// ── Deal request dialog ───────────────────────────────────────────────────────

function DealDialog({ listing, open, onClose }) {
  const navigate = useNavigate();
  const [form, setForm] = useState({ title: '', requirements: '', budget_usd: '', deadline_days: 7, currency: 'USDT' });
  const [loading, setLoading] = useState(false);
  const set = (k, v) => setForm(p => ({ ...p, [k]: v }));

  const handleSubmit = async () => {
    if (!form.title.trim() || !form.budget_usd) { toast.error('Title and budget are required'); return; }
    setLoading(true);
    try {
      const res = await mktApi.createDeal({ ...form, listing_id: listing.id, budget_usd: parseFloat(form.budget_usd) });
      toast.success('Deal request sent!');
      onClose();
      navigate(`/marketplace/deals/${res.data.id}`);
    } catch (e) {
      toast.error(e.response?.data?.error || 'Failed to send request');
    } finally { setLoading(false); }
  };

  if (!listing) return null;
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Send Partnership Request to {listing.title}</DialogTitle>
      <DialogContent>
        <Alert severity="info" icon={false} sx={{ mb: 2, fontSize: '0.75rem' }}>
          Platform fee: 10% · Min budget: $5 · Seller receives {listing.price_per_post ? `from $${listing.price_per_post}/post` : 'negotiable'}
        </Alert>
        <TextField fullWidth label="Campaign title *" value={form.title}
          onChange={e => set('title', e.target.value)} sx={{ mb: 2 }}
          placeholder="e.g. Sponsored post for our DeFi app launch" />
        <TextField fullWidth multiline rows={4} label="Brief / Requirements"
          value={form.requirements} onChange={e => set('requirements', e.target.value)} sx={{ mb: 2 }}
          placeholder="Describe what you need: post format, tone, timing, links to include…" />
        <Box sx={{ display: 'flex', gap: 2, mb: 2, flexWrap: 'wrap' }}>
          <TextField label="Budget (USD) *" type="number" value={form.budget_usd}
            onChange={e => set('budget_usd', e.target.value)}
            sx={{ flex: 1, minWidth: 130 }}
            InputProps={{ startAdornment: <InputAdornment position="start">$</InputAdornment> }}
            helperText={form.budget_usd ? `Seller gets $${(parseFloat(form.budget_usd || 0) * 0.9).toFixed(2)}` : ''} />
          <TextField label="Deadline (days)" type="number" value={form.deadline_days}
            onChange={e => set('deadline_days', parseInt(e.target.value) || 7)}
            sx={{ flex: 1, minWidth: 100 }} />
          <FormControl sx={{ flex: 1, minWidth: 100 }}>
            <InputLabel>Pay with</InputLabel>
            <Select value={form.currency} label="Pay with" onChange={e => set('currency', e.target.value)}>
              {['USDT', 'BTC', 'ETH', 'BNB', 'SOL'].map(c => <MenuItem key={c} value={c}>{c}</MenuItem>)}
            </Select>
          </FormControl>
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={handleSubmit} disabled={loading}>
          {loading ? <CircularProgress size={20} /> : 'Send Request'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// ── Listing card ──────────────────────────────────────────────────────────────

function ListingCard({ listing, onContact }) {
  const isLoggedIn = !!localStorage.getItem('token');
  return (
    <Card sx={{ height: '100%', display: 'flex', flexDirection: 'column',
      ...(listing.is_featured && { border: '1px solid', borderColor: 'primary.main' }) }}>
      <CardContent sx={{ p: 2.5, flex: 1, display: 'flex', flexDirection: 'column' }}>
        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1.5, mb: 1.5 }}>
          <Avatar sx={{ bgcolor: listing.listing_type === 'channel' ? 'secondary.main' : 'primary.main', width: 40, height: 40, fontSize: '1rem', flexShrink: 0 }}>
            {listing.listing_type === 'channel' ? <Campaign sx={{ fontSize: 18 }} /> : listing.title[0]?.toUpperCase()}
          </Avatar>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography fontWeight={700} noWrap>{listing.title}</Typography>
            <Stack direction="row" spacing={0.75} flexWrap="wrap" mt={0.25}>
              <Chip label={listing.listing_type === 'channel' ? 'Channel' : 'Group'} size="small" sx={{ height: 16, fontSize: '0.58rem' }} />
              <Chip label={listing.category} size="small" variant="outlined" sx={{ height: 16, fontSize: '0.58rem' }} />
            </Stack>
          </Box>
        </Box>

        {listing.description && (
          <Typography variant="body2" color="text.secondary" mb={1.5}
            sx={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
            {listing.description}
          </Typography>
        )}

        {/* Stats */}
        <Stack direction="row" spacing={2} mb={1.5} flexWrap="wrap">
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <People sx={{ fontSize: 13, color: 'text.disabled' }} />
            <Typography variant="caption" color="text.secondary">{(listing.member_count || 0).toLocaleString()}</Typography>
          </Box>
          {listing.tcs_score != null && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
              <Shield sx={{ fontSize: 13, color: 'text.disabled' }} />
              <Typography variant="caption" color="text.secondary">TCS {listing.tcs_score}</Typography>
              <Chip label={listing.tcs_grade} size="small" color="success" sx={{ height: 14, fontSize: '0.56rem', fontWeight: 700 }} />
            </Box>
          )}
        </Stack>

        {/* Pricing */}
        <Box sx={{ bgcolor: 'rgba(37,99,235,0.06)', borderRadius: 1.5, p: 1.25, mb: 1.5 }}>
          <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={0.5}>
            Pricing
          </Typography>
          <Stack direction="row" spacing={2}>
            {listing.price_per_post && (
              <Box>
                <Typography variant="body2" fontWeight={700} color="primary.main">${listing.price_per_post}</Typography>
                <Typography variant="caption" color="text.disabled">per post</Typography>
              </Box>
            )}
            {listing.price_per_week && (
              <Box>
                <Typography variant="body2" fontWeight={700} color="secondary.main">${listing.price_per_week}</Typography>
                <Typography variant="caption" color="text.disabled">per week</Typography>
              </Box>
            )}
            {!listing.price_per_post && !listing.price_per_week && (
              <Typography variant="caption" color="text.disabled">Contact for pricing</Typography>
            )}
          </Stack>
          {listing.pricing_notes && (
            <Typography variant="caption" color="text.disabled" display="block" mt={0.5}>{listing.pricing_notes}</Typography>
          )}
        </Box>

        <Box sx={{ mt: 'auto' }}>
          {isLoggedIn ? (
            <Button fullWidth variant="contained" size="small" startIcon={<Handshake fontSize="small" />} onClick={() => onContact(listing)}>
              Send Partnership Request
            </Button>
          ) : (
            <Button fullWidth variant="outlined" size="small" href="/login">
              Sign in to contact
            </Button>
          )}
        </Box>
      </CardContent>
    </Card>
  );
}

// ── My deals list ─────────────────────────────────────────────────────────────

function MyDeals() {
  const navigate = useNavigate();
  const [deals, setDeals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [role, setRole] = useState('all');

  const load = useCallback(() => {
    setLoading(true);
    mktApi.deals({ role }).then(r => setDeals(r.data)).catch(() => {}).finally(() => setLoading(false));
  }, [role]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <Box sx={{ py: 6, textAlign: 'center' }}><CircularProgress /></Box>;

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2, flexWrap: 'wrap', gap: 1 }}>
        <Typography variant="subtitle2" fontWeight={700}>My Deals</Typography>
        <ToggleButtonGroup value={role} exclusive size="small" onChange={(_, v) => v && setRole(v)}>
          <ToggleButton value="all">All</ToggleButton>
          <ToggleButton value="buyer">As Buyer</ToggleButton>
          <ToggleButton value="seller">As Seller</ToggleButton>
        </ToggleButtonGroup>
      </Box>

      {deals.length === 0 ? (
        <Box sx={{ py: 6, textAlign: 'center' }}>
          <Handshake sx={{ fontSize: 52, color: 'text.disabled', mb: 2 }} />
          <Typography variant="body2" color="text.disabled">No deals yet. Browse the marketplace to send your first request.</Typography>
        </Box>
      ) : (
        <Stack spacing={1.5}>
          {deals.map(d => (
            <Card key={d.id} sx={{ cursor: 'pointer', '&:hover': { borderColor: 'primary.main' } }}
              onClick={() => navigate(`/marketplace/deals/${d.id}`)}>
              <CardContent sx={{ p: 2 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 1 }}>
                  <Box>
                    <Typography fontWeight={700} variant="body2">{d.title}</Typography>
                    <Typography variant="caption" color="text.secondary">
                      {d.listing_title} · {d.is_buyer ? `To: ${d.seller_name}` : `From: ${d.buyer_name}`}
                    </Typography>
                  </Box>
                  <Stack direction="row" spacing={1} alignItems="center">
                    <Typography variant="body2" fontWeight={700} color="primary.main">${d.budget_usd}</Typography>
                    <Chip label={d.status.replace('_', ' ')} size="small"
                      color={STATUS_COLOR[d.status] || 'default'} sx={{ fontSize: '0.65rem' }} />
                  </Stack>
                </Box>
              </CardContent>
            </Card>
          ))}
        </Stack>
      )}
    </Box>
  );
}

// ── Main page (preserved in full for future reactivation) ────────────────────

function MarketplaceFull({ tab: initialTab }) {
  const navigate = useNavigate();
  const [tab, setTab] = useState(initialTab === 'deals' ? 1 : 0);
  const [listings, setListings] = useState([]);
  const [total, setTotal] = useState(0);
  const [pages, setPages] = useState(1);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('All');
  const [type, setType] = useState('all');
  const [contactListing, setContactListing] = useState(null);

  useEffect(() => { const t = setTimeout(() => setSearch(searchInput), 350); return () => clearTimeout(t); }, [searchInput]);

  const fetchListings = useCallback((p = 1) => {
    setLoading(true);
    const params = { page: p };
    if (search) params.q = search;
    if (category !== 'All') params.category = category;
    if (type !== 'all') params.type = type;
    mktApi.browse(params)
      .then(r => { setListings(r.data.listings); setTotal(r.data.total); setPages(r.data.pages); setPage(p); })
      .catch(() => {}).finally(() => setLoading(false));
  }, [search, category, type]);

  useEffect(() => { if (tab === 0) fetchListings(1); }, [fetchListings, tab]);

  const isLoggedIn = !!localStorage.getItem('token');

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      {/* Hero */}
      <Box sx={{ bgcolor: 'rgba(124,58,237,0.08)', borderBottom: '1px solid rgba(255,255,255,0.07)', py: { xs: 4, md: 5 }, px: 3 }}>
        <Box sx={{ maxWidth: 900, mx: 'auto', textAlign: 'center' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 1.5, mb: 1.5 }}>
            <Handshake sx={{ fontSize: 36, color: 'secondary.main' }} />
            <Typography variant="h4" fontWeight={800}>Partnership Marketplace</Typography>
          </Box>
          <Typography variant="body1" color="text.secondary" mb={3} maxWidth={520} mx="auto">
            Connect brands with authentic Telegram communities. TCS-verified channels, crypto escrow, zero trust required.
          </Typography>
          <Stack direction="row" spacing={1.5} justifyContent="center" flexWrap="wrap">
            {isLoggedIn ? (
              <Button variant="contained" color="secondary" startIcon={<Add />}
                onClick={() => navigate('/directory/submit')}>
                List Your Community
              </Button>
            ) : (
              <Button variant="contained" color="secondary" onClick={() => navigate('/login')}>
                Sign in to List
              </Button>
            )}
            {isLoggedIn && (
              <Button variant="outlined" onClick={() => setTab(1)}>
                My Deals
              </Button>
            )}
          </Stack>

          {/* Value props */}
          <Stack direction="row" spacing={3} justifyContent="center" mt={3} flexWrap="wrap">
            {[
              { icon: <Shield sx={{ fontSize: 16 }} />, text: 'TCS-verified channels' },
              { icon: <AttachMoney sx={{ fontSize: 16 }} />, text: 'Crypto escrow' },
              { icon: <Gavel sx={{ fontSize: 16 }} />, text: '10% platform fee' },
            ].map(v => (
              <Box key={v.text} sx={{ display: 'flex', alignItems: 'center', gap: 0.5, color: 'text.secondary' }}>
                {v.icon}
                <Typography variant="caption">{v.text}</Typography>
              </Box>
            ))}
          </Stack>
        </Box>
      </Box>

      <Box sx={{ maxWidth: 1100, mx: 'auto', px: { xs: 2, md: 3 }, py: 3 }}>
        <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 3 }}>
          <Tab label="Browse Communities" />
          {isLoggedIn && <Tab label="My Deals" />}
        </Tabs>

        {tab === 0 && (
          <>
            {/* Filters */}
            <Card sx={{ mb: 3 }}>
              <CardContent sx={{ p: 2 }}>
                <Grid container spacing={2} alignItems="center">
                  <Grid item xs={12} sm={5}>
                    <TextField fullWidth size="small" placeholder="Search communities…"
                      value={searchInput} onChange={e => setSearchInput(e.target.value)}
                      InputProps={{ startAdornment: <InputAdornment position="start"><Search fontSize="small" /></InputAdornment> }} />
                  </Grid>
                  <Grid item xs={6} sm={4}>
                    <FormControl fullWidth size="small">
                      <InputLabel>Category</InputLabel>
                      <Select value={category} label="Category" onChange={e => setCategory(e.target.value)}>
                        {CATEGORIES.map(c => <MenuItem key={c} value={c}>{c}</MenuItem>)}
                      </Select>
                    </FormControl>
                  </Grid>
                  <Grid item xs={6} sm={3}>
                    <ToggleButtonGroup value={type} exclusive size="small" fullWidth onChange={(_, v) => v && setType(v)}>
                      <ToggleButton value="all">All</ToggleButton>
                      <ToggleButton value="channel"><Campaign sx={{ fontSize: 16 }} /></ToggleButton>
                      <ToggleButton value="group"><Groups sx={{ fontSize: 16 }} /></ToggleButton>
                    </ToggleButtonGroup>
                  </Grid>
                </Grid>
              </CardContent>
            </Card>

            <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
              <Typography variant="body2" color="text.secondary">
                {loading ? 'Loading…' : `${total} communities available for partnership`}
              </Typography>
            </Box>

            {loading ? (
              <Box sx={{ py: 8, textAlign: 'center' }}><CircularProgress /></Box>
            ) : listings.length === 0 ? (
              <Box sx={{ py: 8, textAlign: 'center' }}>
                <Handshake sx={{ fontSize: 52, color: 'text.disabled', mb: 2 }} />
                <Typography variant="h6" fontWeight={700} gutterBottom>No communities available yet</Typography>
                <Typography variant="body2" color="text.secondary" mb={3}>
                  List your channel or group and enable partnerships to appear here.
                </Typography>
                <Button variant="contained" onClick={() => navigate('/directory/submit')}>List Your Community</Button>
              </Box>
            ) : (
              <Grid container spacing={2}>
                {listings.map(l => (
                  <Grid item xs={12} sm={6} md={4} key={l.id}>
                    <ListingCard listing={l} onContact={setContactListing} />
                  </Grid>
                ))}
              </Grid>
            )}

            {pages > 1 && (
              <Box sx={{ display: 'flex', justifyContent: 'center', gap: 1, mt: 4 }}>
                <Button size="small" disabled={page <= 1} onClick={() => fetchListings(page - 1)}>Prev</Button>
                <Typography variant="body2" color="text.secondary" sx={{ alignSelf: 'center' }}>Page {page} of {pages}</Typography>
                <Button size="small" disabled={page >= pages} onClick={() => fetchListings(page + 1)}>Next</Button>
              </Box>
            )}
          </>
        )}

        {tab === 1 && isLoggedIn && <MyDeals />}
      </Box>

      <DealDialog listing={contactListing} open={!!contactListing} onClose={() => setContactListing(null)} />
    </Box>
  );
}

// ── Feature-flagged export ────────────────────────────────────────────────────
// Temporarily hidden for future reactivation. Swap to MarketplaceFull when ready.
export default function Marketplace(props) {
  if (SHOW_MARKETPLACE) return <MarketplaceFull {...props} />;
  return (
    <ComingSoonPage
      icon={Handshake}
      title="Partnership Marketplace"
      subtitle="Connect brands with authentic Telegram communities. TCS-verified channels, crypto escrow, and transparent partnership deals — coming soon."
      features={[
        { icon: Shield, title: 'TCS-Verified Listings', desc: 'Only authentic, score-verified communities' },
        { icon: AttachMoney, title: 'Crypto Escrow Payments', desc: 'USDT, BTC, ETH, BNB, SOL supported' },
        { icon: Gavel, title: 'Deal Management', desc: 'Track negotiations, deliverables, and completion' },
      ]}
    />
  );
}
