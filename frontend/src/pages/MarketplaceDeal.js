import React, { useState, useEffect, useRef } from 'react';
import {
  Box, Typography, Card, CardContent, Button, Chip, Grid,
  CircularProgress, Alert, Stack, Divider, TextField,
  IconButton, Avatar, Stepper, Step, StepLabel, Dialog,
  DialogTitle, DialogContent, DialogActions,
} from '@mui/material';
import {
  ArrowBack, Send, CheckCircle, Cancel, Gavel,
  AttachMoney, LocalShipping, Handshake, Warning,
} from '@mui/icons-material';
import { useParams, useNavigate } from 'react-router-dom';
import { toast } from 'react-toastify';
import { marketplace as mktApi } from '../services/api';

const STATUS_STEPS = ['pending', 'accepted', 'in_progress', 'delivered', 'completed'];
const STATUS_LABEL = {
  pending: 'Request Sent', accepted: 'Accepted',
  in_progress: 'In Progress', delivered: 'Delivered', completed: 'Completed',
  declined: 'Declined', disputed: 'Disputed', cancelled: 'Cancelled',
};
const STATUS_COLOR = {
  pending: 'warning', accepted: 'info', in_progress: 'primary',
  delivered: 'secondary', completed: 'success',
  declined: 'error', disputed: 'error', cancelled: 'default',
};

function StatusStepper({ status }) {
  const terminalStatuses = ['declined', 'cancelled', 'disputed'];
  if (terminalStatuses.includes(status)) {
    return (
      <Alert severity={status === 'disputed' ? 'warning' : 'error'} sx={{ mb: 2 }}>
        Deal is <strong>{STATUS_LABEL[status]}</strong>.
        {status === 'disputed' && ' Telegizer support will review and resolve this.'}
      </Alert>
    );
  }
  const activeIdx = STATUS_STEPS.indexOf(status);
  return (
    <Stepper activeStep={activeIdx} alternativeLabel sx={{ mb: 3 }}>
      {STATUS_STEPS.map((s, i) => (
        <Step key={s} completed={i < activeIdx}>
          <StepLabel sx={{ '& .MuiStepLabel-label': { fontSize: '0.7rem' } }}>
            {STATUS_LABEL[s]}
          </StepLabel>
        </Step>
      ))}
    </Stepper>
  );
}

function PaymentPanel({ deal, onUpdated }) {
  const [loading, setLoading] = useState(false);
  const [payInfo, setPayInfo] = useState(null);

  const handlePay = async () => {
    setLoading(true);
    try {
      const res = await mktApi.pay(deal.id, { currency: deal.payment_currency });
      setPayInfo(res.data);
      onUpdated(res.data);
      toast.success('Payment initiated');
    } catch (e) {
      toast.error(e.response?.data?.error || 'Payment failed');
    } finally { setLoading(false); }
  };

  if (deal.payment_status === 'released') {
    return <Alert severity="success" icon={<CheckCircle />} sx={{ mb: 2 }}>Payment released to seller.</Alert>;
  }
  if (deal.payment_status === 'paid') {
    return <Alert severity="info" sx={{ mb: 2 }}>Payment confirmed — deal is in progress.</Alert>;
  }
  if (deal.status !== 'accepted') return null;
  if (!deal.is_buyer) return (
    <Alert severity="info" sx={{ mb: 2 }}>Waiting for buyer to pay ${deal.budget_usd}.</Alert>
  );

  return (
    <Card sx={{ mb: 2, border: '1px solid', borderColor: 'primary.main', bgcolor: 'rgba(37,99,235,0.06)' }}>
      <CardContent sx={{ p: 2 }}>
        <Typography variant="subtitle2" fontWeight={700} mb={1}>
          <AttachMoney sx={{ fontSize: 18, verticalAlign: 'middle', mr: 0.5 }} />
          Pay to Start
        </Typography>
        <Stack direction="row" spacing={2} mb={1.5}>
          <Box>
            <Typography variant="h6" fontWeight={800} color="primary.main">${deal.budget_usd}</Typography>
            <Typography variant="caption" color="text.disabled">Total (incl. 10% fee)</Typography>
          </Box>
          <Box>
            <Typography variant="body2" fontWeight={700} color="success.main">${deal.net_seller_amount}</Typography>
            <Typography variant="caption" color="text.disabled">Seller receives</Typography>
          </Box>
        </Stack>
        {payInfo ? (
          <Alert severity="info" icon={false} sx={{ fontSize: '0.75rem' }}>
            Send <strong>{payInfo.pay_amount} {payInfo.pay_currency}</strong> to:<br />
            <code style={{ wordBreak: 'break-all', fontSize: '0.7rem' }}>{payInfo.pay_address}</code>
            <br />Payment ID: {payInfo.payment_id}
          </Alert>
        ) : (
          <Button variant="contained" startIcon={loading ? <CircularProgress size={16} /> : <AttachMoney />}
            onClick={handlePay} disabled={loading} fullWidth>
            Pay ${deal.budget_usd} in {deal.payment_currency}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

function DeliverDialog({ open, onClose, onDeliver }) {
  const [text, setText] = useState('');
  const [loading, setLoading] = useState(false);
  const handleSubmit = async () => {
    if (!text.trim()) { toast.error('Describe what you delivered'); return; }
    setLoading(true);
    try { await onDeliver(text); onClose(); }
    finally { setLoading(false); }
  };
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Mark as Delivered</DialogTitle>
      <DialogContent>
        <TextField fullWidth multiline rows={4} autoFocus
          label="Describe what was delivered"
          placeholder="Post link, screenshot, performance notes…"
          value={text} onChange={e => setText(e.target.value)} />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={handleSubmit} disabled={loading}>
          {loading ? <CircularProgress size={18} /> : 'Submit'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function DisputeDialog({ open, onClose, onDispute }) {
  const [reason, setReason] = useState('');
  const [loading, setLoading] = useState(false);
  const handleSubmit = async () => {
    setLoading(true);
    try { await onDispute(reason); onClose(); }
    finally { setLoading(false); }
  };
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Raise a Dispute</DialogTitle>
      <DialogContent>
        <Alert severity="warning" sx={{ mb: 2, fontSize: '0.75rem' }}>
          Disputes are reviewed by Telegizer support. Only raise if the seller did not deliver as agreed.
        </Alert>
        <TextField fullWidth multiline rows={3} autoFocus
          label="Reason (optional)"
          value={reason} onChange={e => setReason(e.target.value)} />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" color="error" onClick={handleSubmit} disabled={loading}>
          {loading ? <CircularProgress size={18} /> : 'Raise Dispute'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function ChatPanel({ deal, currentUserId, onMessage }) {
  const [body, setBody] = useState('');
  const [sending, setSending] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [deal.messages]);

  const handleSend = async () => {
    if (!body.trim()) return;
    setSending(true);
    try {
      const res = await mktApi.sendMessage(deal.id, body.trim());
      onMessage(res.data);
      setBody('');
    } catch { toast.error('Failed to send'); }
    finally { setSending(false); }
  };

  return (
    <Card>
      <CardContent sx={{ p: 2 }}>
        <Typography variant="subtitle2" fontWeight={700} mb={2}>Deal Messages</Typography>
        <Box sx={{ maxHeight: 320, overflowY: 'auto', mb: 2, pr: 0.5 }}>
          {(deal.messages || []).length === 0 && (
            <Typography variant="caption" color="text.disabled">No messages yet. Start the conversation.</Typography>
          )}
          {(deal.messages || []).map(m => {
            const isMe = m.sender_user_id === currentUserId;
            return (
              <Box key={m.id} sx={{ display: 'flex', justifyContent: isMe ? 'flex-end' : 'flex-start', mb: 1.5 }}>
                {!isMe && (
                  <Avatar sx={{ width: 28, height: 28, fontSize: '0.7rem', mr: 1, mt: 0.25, bgcolor: 'secondary.main', flexShrink: 0 }}>
                    {deal.is_buyer ? deal.seller_name?.[0] : deal.buyer_name?.[0]}
                  </Avatar>
                )}
                <Box sx={{
                  maxWidth: '75%', bgcolor: isMe ? 'primary.main' : 'rgba(255,255,255,0.07)',
                  borderRadius: isMe ? '12px 12px 2px 12px' : '12px 12px 12px 2px',
                  px: 1.5, py: 1,
                }}>
                  <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                    {m.body}
                  </Typography>
                  <Typography variant="caption" color={isMe ? 'rgba(255,255,255,0.6)' : 'text.disabled'}
                    display="block" mt={0.25} textAlign="right" fontSize="0.6rem">
                    {new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </Typography>
                </Box>
              </Box>
            );
          })}
          <div ref={bottomRef} />
        </Box>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <TextField fullWidth size="small" placeholder="Type a message…"
            value={body} onChange={e => setBody(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !e.shiftKey && (e.preventDefault(), handleSend())}
            multiline maxRows={3} />
          <IconButton color="primary" onClick={handleSend} disabled={sending || !body.trim()}>
            {sending ? <CircularProgress size={20} /> : <Send />}
          </IconButton>
        </Box>
      </CardContent>
    </Card>
  );
}

export default function MarketplaceDeal() {
  const { did } = useParams();
  const navigate = useNavigate();
  const [deal, setDeal] = useState(null);
  const [loading, setLoading] = useState(true);
  const [deliverOpen, setDeliverOpen] = useState(false);
  const [disputeOpen, setDisputeOpen] = useState(false);

  const user = (() => { try { return JSON.parse(localStorage.getItem('user') || '{}'); } catch { return {}; } })();

  useEffect(() => {
    mktApi.getDeal(did).then(r => setDeal(r.data)).catch(() => {}).finally(() => setLoading(false));
  }, [did]);

  const handleAction = async (fn, ...args) => {
    try {
      const res = await fn(...args);
      setDeal(res.data);
    } catch (e) {
      toast.error(e.response?.data?.error || 'Action failed');
    }
  };

  const handleMessage = (msg) => {
    setDeal(prev => ({ ...prev, messages: [...(prev.messages || []), msg] }));
  };

  if (loading) return <Box sx={{ py: 8, textAlign: 'center' }}><CircularProgress /></Box>;
  if (!deal) return <Alert severity="error" sx={{ m: 3 }}>Deal not found.</Alert>;

  const canAccept = deal.is_seller && deal.status === 'pending';
  const canDecline = deal.is_seller && deal.status === 'pending';
  const canDeliver = deal.is_seller && deal.status === 'in_progress';
  const canComplete = deal.is_buyer && deal.status === 'delivered';
  const canDispute = deal.is_buyer && ['in_progress', 'delivered'].includes(deal.status);
  const canCancel = ['pending', 'accepted'].includes(deal.status);

  return (
    <Box sx={{ p: { xs: 2, md: 4 }, maxWidth: 860, mx: 'auto' }}>
      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 3, flexWrap: 'wrap' }}>
        <IconButton size="small" onClick={() => navigate('/marketplace')}><ArrowBack /></IconButton>
        <Box sx={{ flex: 1 }}>
          <Typography variant="h6" fontWeight={700}>{deal.title}</Typography>
          <Typography variant="caption" color="text.secondary">
            {deal.listing_title} · {deal.is_buyer ? `Seller: ${deal.seller_name}` : `Buyer: ${deal.buyer_name}`}
          </Typography>
        </Box>
        <Chip label={STATUS_LABEL[deal.status] || deal.status}
          color={STATUS_COLOR[deal.status] || 'default'} />
      </Box>

      {/* Status stepper */}
      <StatusStepper status={deal.status} />

      <Grid container spacing={2}>
        <Grid item xs={12} md={7}>
          {/* Payment panel */}
          <PaymentPanel deal={deal} onUpdated={setDeal} />

          {/* Brief */}
          <Card sx={{ mb: 2 }}>
            <CardContent sx={{ p: 2 }}>
              <Typography variant="subtitle2" fontWeight={700} mb={1.5}>Deal Details</Typography>
              <Grid container spacing={1.5} mb={1.5}>
                {[
                  { label: 'Budget', value: `$${deal.budget_usd}` },
                  { label: 'Seller gets', value: `$${deal.net_seller_amount}` },
                  { label: 'Payment', value: deal.payment_status.replace('_', ' ') },
                  { label: 'Deadline', value: deal.deadline_at ? new Date(deal.deadline_at).toLocaleDateString() : '—' },
                ].map(s => (
                  <Grid item xs={6} key={s.label}>
                    <Box sx={{ bgcolor: 'rgba(255,255,255,0.04)', borderRadius: 1.5, p: 1.25 }}>
                      <Typography variant="caption" color="text.secondary" display="block">{s.label}</Typography>
                      <Typography variant="body2" fontWeight={700}>{s.value}</Typography>
                    </Box>
                  </Grid>
                ))}
              </Grid>

              {deal.requirements && (
                <>
                  <Typography variant="caption" fontWeight={600} color="text.secondary" display="block" mb={0.5}>Brief</Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: 'pre-wrap' }}>{deal.requirements}</Typography>
                </>
              )}

              {deal.deliverable && (
                <>
                  <Divider sx={{ my: 1.5 }} />
                  <Alert severity="success" icon={<LocalShipping fontSize="small" />} sx={{ fontSize: '0.75rem' }}>
                    <strong>Delivered:</strong> {deal.deliverable}
                  </Alert>
                </>
              )}
            </CardContent>
          </Card>

          {/* Action buttons */}
          <Stack spacing={1} mb={2}>
            {canAccept && (
              <Button fullWidth variant="contained" color="success" startIcon={<CheckCircle />}
                onClick={() => handleAction(() => mktApi.accept(deal.id))}>
                Accept Deal
              </Button>
            )}
            {canDeliver && (
              <Button fullWidth variant="contained" startIcon={<LocalShipping />} onClick={() => setDeliverOpen(true)}>
                Mark as Delivered
              </Button>
            )}
            {canComplete && (
              <Button fullWidth variant="contained" color="success" startIcon={<Handshake />}
                onClick={() => handleAction(() => mktApi.complete(deal.id))}>
                Confirm & Release Payment
              </Button>
            )}
            {canDecline && (
              <Button fullWidth variant="outlined" color="error" startIcon={<Cancel />}
                onClick={() => handleAction(() => mktApi.decline(deal.id, {}))}>
                Decline
              </Button>
            )}
            {canDispute && (
              <Button fullWidth variant="outlined" color="warning" startIcon={<Warning />}
                onClick={() => setDisputeOpen(true)}>
                Raise Dispute
              </Button>
            )}
            {canCancel && (
              <Button fullWidth variant="text" color="error" startIcon={<Cancel />}
                onClick={() => handleAction(() => mktApi.cancel(deal.id))}>
                Cancel Deal
              </Button>
            )}
          </Stack>
        </Grid>

        <Grid item xs={12} md={5}>
          <ChatPanel deal={deal} currentUserId={user?.id} onMessage={handleMessage} />
        </Grid>
      </Grid>

      <DeliverDialog open={deliverOpen} onClose={() => setDeliverOpen(false)}
        onDeliver={async (text) => { const r = await mktApi.deliver(deal.id, { deliverable: text }); setDeal(r.data); toast.success('Marked as delivered'); }} />

      <DisputeDialog open={disputeOpen} onClose={() => setDisputeOpen(false)}
        onDispute={async (reason) => { const r = await mktApi.dispute(deal.id, { reason }); setDeal(r.data); toast.success('Dispute raised'); }} />
    </Box>
  );
}
