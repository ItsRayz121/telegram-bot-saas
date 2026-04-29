import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Card, CardContent, Button, Chip, Grid,
  TextField, InputAdornment, Select, MenuItem, FormControl,
  InputLabel, CircularProgress, Alert, Avatar, Stack, Divider,
  ToggleButton, ToggleButtonGroup, Tooltip,
} from '@mui/material';
import {
  Search, Explore, Campaign, Groups, Verified, OpenInNew,
  People, Shield, Add, TrendingUp,
} from '@mui/icons-material';
import { useNavigate, useLocation } from 'react-router-dom';
import { directory as dirApi } from '../services/api';

const CATEGORIES = [
  "All", "Technology & Dev", "Crypto & Web3", "News & Politics",
  "Business & Finance", "Education & Learning", "Entertainment",
  "Gaming", "Health & Wellness", "Sports", "Art & Design", "Other",
];

const SORT_OPTIONS = [
  { value: 'featured', label: 'Featured' },
  { value: 'members', label: 'Most Members' },
  { value: 'tcs', label: 'Highest TCS' },
  { value: 'newest', label: 'Newest' },
];

const GRADE_COLOR = { A: 'success', B: 'success', C: 'warning', D: 'warning', F: 'error' };

function ListingCard({ listing }) {
  const handleJoin = () => {
    dirApi.recordContact(listing.id).catch(() => {});
    window.open(listing.telegram_link, '_blank', 'noopener,noreferrer');
  };

  return (
    <Card
      sx={{ height: '100%', display: 'flex', flexDirection: 'column', position: 'relative',
        ...(listing.is_featured && { border: '1px solid', borderColor: 'primary.main' }) }}
      onMouseEnter={() => dirApi.recordView(listing.id).catch(() => {})}
    >
      {listing.is_featured && (
        <Chip
          label="Featured"
          color="primary"
          size="small"
          sx={{ position: 'absolute', top: 10, right: 10, height: 18, fontSize: '0.6rem', fontWeight: 700 }}
        />
      )}
      <CardContent sx={{ p: 2.5, flex: 1, display: 'flex', flexDirection: 'column' }}>
        {/* Header */}
        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1.5, mb: 1.5 }}>
          <Avatar sx={{
            bgcolor: listing.listing_type === 'channel' ? 'secondary.main' : 'primary.main',
            width: 44, height: 44, fontSize: '1.1rem', flexShrink: 0,
          }}>
            {listing.listing_type === 'channel'
              ? <Campaign sx={{ fontSize: 20 }} />
              : listing.title[0]?.toUpperCase()}
          </Avatar>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, flexWrap: 'wrap' }}>
              <Typography fontWeight={700} noWrap sx={{ maxWidth: 180 }}>{listing.title}</Typography>
              {listing.is_verified && (
                <Tooltip title="Verified community">
                  <Verified sx={{ fontSize: 16, color: 'primary.main' }} />
                </Tooltip>
              )}
            </Box>
            <Stack direction="row" spacing={0.75} flexWrap="wrap" mt={0.25}>
              <Chip
                label={listing.listing_type === 'channel' ? 'Channel' : 'Group'}
                size="small"
                icon={listing.listing_type === 'channel' ? <Campaign sx={{ fontSize: '0.7rem !important' }} /> : <Groups sx={{ fontSize: '0.7rem !important' }} />}
                sx={{ height: 18, fontSize: '0.6rem' }}
              />
              <Chip label={listing.category} size="small" sx={{ height: 18, fontSize: '0.6rem' }} />
              {listing.language !== 'English' && (
                <Chip label={listing.language} size="small" variant="outlined" sx={{ height: 18, fontSize: '0.6rem' }} />
              )}
            </Stack>
          </Box>
        </Box>

        {/* Description */}
        {listing.description && (
          <Typography variant="body2" color="text.secondary" mb={1.5}
            sx={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
            {listing.description}
          </Typography>
        )}

        {/* Stats row */}
        <Box sx={{ display: 'flex', gap: 2, mb: 1.5, flexWrap: 'wrap' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <People sx={{ fontSize: 14, color: 'text.disabled' }} />
            <Typography variant="caption" color="text.secondary">
              {(listing.member_count || 0).toLocaleString()} members
            </Typography>
          </Box>
          {listing.tcs_score != null && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
              <Shield sx={{ fontSize: 14, color: 'text.disabled' }} />
              <Typography variant="caption" color="text.secondary">
                TCS {listing.tcs_score}
              </Typography>
              <Chip
                label={listing.tcs_grade}
                color={GRADE_COLOR[listing.tcs_grade] || 'default'}
                size="small"
                sx={{ height: 16, fontSize: '0.58rem', fontWeight: 700 }}
              />
            </Box>
          )}
          {listing.country && listing.country !== 'Global' && (
            <Typography variant="caption" color="text.disabled">{listing.country}</Typography>
          )}
        </Box>

        <Box sx={{ mt: 'auto' }}>
          <Button
            fullWidth variant="contained" size="small"
            startIcon={<OpenInNew fontSize="small" />}
            onClick={handleJoin}
          >
            Join Community
          </Button>
        </Box>
      </CardContent>
    </Card>
  );
}

export default function Directory() {
  const navigate = useNavigate();
  const location = useLocation();

  const [listings, setListings] = useState([]);
  const [total, setTotal] = useState(0);
  const [pages, setPages] = useState(1);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('All');
  const [sort, setSort] = useState('featured');
  const [type, setType] = useState('all');

  // Debounced search
  const [searchInput, setSearchInput] = useState('');
  useEffect(() => {
    const t = setTimeout(() => setSearch(searchInput), 350);
    return () => clearTimeout(t);
  }, [searchInput]);

  const fetchListings = useCallback((p = 1) => {
    setLoading(true);
    const params = { page: p, sort };
    if (search) params.q = search;
    if (category !== 'All') params.category = category;
    if (type !== 'all') params.type = type;

    dirApi.list(params)
      .then(r => {
        setListings(r.data.listings);
        setTotal(r.data.total);
        setPages(r.data.pages);
        setPage(p);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [search, category, sort, type]);

  useEffect(() => { fetchListings(1); }, [fetchListings]);

  // Check if user is logged in (token present) for submit button
  const isLoggedIn = !!localStorage.getItem('token');

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      {/* Hero */}
      <Box sx={{ bgcolor: 'rgba(37,99,235,0.08)', borderBottom: '1px solid rgba(255,255,255,0.07)', py: { xs: 4, md: 6 }, px: 3 }}>
        <Box sx={{ maxWidth: 900, mx: 'auto', textAlign: 'center' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 1.5, mb: 2 }}>
            <Explore sx={{ fontSize: 36, color: 'primary.main' }} />
            <Typography variant="h4" fontWeight={800}>Community Directory</Typography>
          </Box>
          <Typography variant="body1" color="text.secondary" mb={3} maxWidth={560} mx="auto">
            Discover authentic Telegram channels and groups — verified by TCS, filtered by topic and language.
          </Typography>
          <Stack direction="row" spacing={1.5} justifyContent="center" flexWrap="wrap">
            {isLoggedIn ? (
              <Button variant="contained" startIcon={<Add />} onClick={() => navigate('/directory/submit')}>
                List Your Community
              </Button>
            ) : (
              <Button variant="contained" startIcon={<Add />} onClick={() => navigate('/login')}>
                Sign in to List Your Community
              </Button>
            )}
            <Button variant="outlined" startIcon={<TrendingUp />} onClick={() => navigate('/channels')}>
              Analyse Your Channel
            </Button>
          </Stack>
        </Box>
      </Box>

      <Box sx={{ maxWidth: 1100, mx: 'auto', px: { xs: 2, md: 3 }, py: 4 }}>
        {/* Filters */}
        <Card sx={{ mb: 3 }}>
          <CardContent sx={{ p: 2 }}>
            <Grid container spacing={2} alignItems="center">
              <Grid item xs={12} sm={5}>
                <TextField
                  fullWidth size="small"
                  placeholder="Search communities…"
                  value={searchInput}
                  onChange={e => setSearchInput(e.target.value)}
                  InputProps={{ startAdornment: <InputAdornment position="start"><Search fontSize="small" /></InputAdornment> }}
                />
              </Grid>
              <Grid item xs={6} sm={3}>
                <FormControl fullWidth size="small">
                  <InputLabel>Category</InputLabel>
                  <Select value={category} label="Category" onChange={e => setCategory(e.target.value)}>
                    {CATEGORIES.map(c => <MenuItem key={c} value={c}>{c}</MenuItem>)}
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={6} sm={2}>
                <FormControl fullWidth size="small">
                  <InputLabel>Sort</InputLabel>
                  <Select value={sort} label="Sort" onChange={e => setSort(e.target.value)}>
                    {SORT_OPTIONS.map(o => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={12} sm={2}>
                <ToggleButtonGroup
                  value={type} exclusive size="small" fullWidth
                  onChange={(_, v) => v && setType(v)}
                >
                  <ToggleButton value="all">All</ToggleButton>
                  <ToggleButton value="channel"><Campaign sx={{ fontSize: 16 }} /></ToggleButton>
                  <ToggleButton value="group"><Groups sx={{ fontSize: 16 }} /></ToggleButton>
                </ToggleButtonGroup>
              </Grid>
            </Grid>
          </CardContent>
        </Card>

        {/* Results header */}
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
          <Typography variant="body2" color="text.secondary">
            {loading ? 'Loading…' : `${total} ${total === 1 ? 'community' : 'communities'} found`}
          </Typography>
        </Box>

        {/* Grid */}
        {loading ? (
          <Box sx={{ py: 8, textAlign: 'center' }}><CircularProgress /></Box>
        ) : listings.length === 0 ? (
          <Box sx={{ py: 8, textAlign: 'center' }}>
            <Explore sx={{ fontSize: 52, color: 'text.disabled', mb: 2 }} />
            <Typography variant="h6" fontWeight={700} gutterBottom>No communities found</Typography>
            <Typography variant="body2" color="text.secondary" mb={3}>
              Try a different category or search term, or be the first to list yours.
            </Typography>
            {isLoggedIn && (
              <Button variant="contained" startIcon={<Add />} onClick={() => navigate('/directory/submit')}>
                List Your Community
              </Button>
            )}
          </Box>
        ) : (
          <Grid container spacing={2}>
            {listings.map(l => (
              <Grid item xs={12} sm={6} md={4} key={l.id}>
                <ListingCard listing={l} />
              </Grid>
            ))}
          </Grid>
        )}

        {/* Pagination */}
        {pages > 1 && (
          <Box sx={{ display: 'flex', justifyContent: 'center', gap: 1, mt: 4 }}>
            <Button size="small" disabled={page <= 1} onClick={() => fetchListings(page - 1)}>Prev</Button>
            <Typography variant="body2" color="text.secondary" sx={{ alignSelf: 'center' }}>
              Page {page} of {pages}
            </Typography>
            <Button size="small" disabled={page >= pages} onClick={() => fetchListings(page + 1)}>Next</Button>
          </Box>
        )}

        <Divider sx={{ my: 4 }} />
        <Box sx={{ textAlign: 'center' }}>
          <Typography variant="caption" color="text.disabled">
            TCS (Telegizer Community Score) measures channel authenticity based on engagement rate,
            view rate, post consistency, and forward rate.
          </Typography>
        </Box>
      </Box>
    </Box>
  );
}
