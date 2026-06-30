import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import {
  Box, Grid, Card, CardContent, Typography, Button, IconButton, TextField,
  MenuItem, Chip, Stack, Divider, Tooltip, CircularProgress, Switch,
  FormControlLabel, LinearProgress, Table, TableBody, TableCell, TableHead,
  TableRow,
} from '@mui/material';
import {
  FormatBold, FormatItalic, FormatUnderlined, FormatListBulleted,
  FormatListNumbered, FormatQuote, Link as LinkIcon, Image as ImageIcon,
  OndemandVideo, FormatClear, Add, ArrowBack, Visibility, Delete,
  CheckCircle, Warning, RadioButtonUnchecked, Title as TitleIcon,
  Code, HorizontalRule, Schedule,
} from '@mui/icons-material';
import { admin } from '../../services/api';
import { toast } from 'react-toastify';
import { PALETTE } from '../../theme';

const CATEGORIES = ['Guides', 'Telegram', 'Discord', 'Growth', 'Product', 'Comparisons', 'Case studies', 'News'];

const slugify = (s) => (s || '')
  .toLowerCase().trim()
  .replace(/[^\w\s-]/g, '')
  .replace(/[\s_-]+/g, '-')
  .replace(/^-+|-+$/g, '')
  .slice(0, 200);

// ISO → value for <input type="datetime-local"> (local time, no seconds).
const toLocalInput = (iso) => {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
};

// Empty post template
const emptyPost = () => ({
  id: null, title: '', slug: '', excerpt: '', body_html: '',
  cover_image_url: '', author_name: 'Telegizer Team', category: 'Guides',
  tags: [], status: 'draft', focus_keyword: '', meta_title: '',
  meta_description: '', og_image_url: '', canonical_url: '', noindex: false,
});

// ───────────────────────── Rich text editor (zero-dependency) ─────────────────
function RichEditor({ initialHTML, onChange, onImageUpload }) {
  const ref = useRef(null);
  const fileRef = useRef(null);

  // Set the editable content once (uncontrolled, so the caret never jumps).
  useEffect(() => {
    if (ref.current) ref.current.innerHTML = initialHTML || '';
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const emit = useCallback(() => onChange?.(ref.current?.innerHTML || ''), [onChange]);

  const exec = (cmd, val = null) => {
    ref.current?.focus();
    document.execCommand(cmd, false, val);
    emit();
  };

  const escHtml = (t) => (t || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  const onFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    try {
      const url = await onImageUpload(file);
      const alt = (window.prompt('Image alt text (helps SEO & accessibility):') || '')
        .replace(/"/g, '&quot;');
      const caption = (window.prompt('Optional caption shown under the image (leave blank for none):') || '').trim();
      const img = `<img src="${url}" alt="${alt}" loading="lazy">`;
      const html = caption
        ? `<figure>${img}<figcaption>${escHtml(caption)}</figcaption></figure><p><br></p>`
        : `${img}<p><br></p>`;
      ref.current?.focus();
      document.execCommand('insertHTML', false, html);
      emit();
    } catch {
      toast.error('Image upload failed.');
    }
  };

  const addEmbed = () => {
    const url = window.prompt('Paste a video link (YouTube, Vimeo, Google Drive or Telegram post):');
    if (!url) return;
    const title = (window.prompt('Optional video title / caption (leave blank for none):') || '').trim();
    const safeUrl = url.replace(/"/g, '&quot;');
    const label = title ? escHtml(title) : 'Embedded video';
    const placeholder = `<div class="tg-embed" data-embed="${safeUrl}">📹 ${label} — plays on the published page</div>`;
    const html = title
      ? `<figure>${placeholder}<figcaption>${escHtml(title)}</figcaption></figure><p><br></p>`
      : `${placeholder}<p><br></p>`;
    ref.current?.focus();
    document.execCommand('insertHTML', false, html);
    emit();
  };

  const addLink = () => {
    const url = window.prompt('Link URL (https://…):');
    if (url) exec('createLink', url);
  };

  // Paste as clean paragraphs — turns a pasted AI/Docs draft into tidy <p> blocks
  // (no inherited fonts/colours), so formatting stays consistent.
  const onPaste = (e) => {
    e.preventDefault();
    const text = (e.clipboardData || window.clipboardData).getData('text/plain') || '';
    const esc = (t) => t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const html = text.split(/\n{2,}/).map((para) => {
      const lines = para.split(/\n/).map(esc).join('<br>');
      return lines.trim() ? `<p>${lines}</p>` : '';
    }).join('');
    document.execCommand('insertHTML', false, html || esc(text));
    emit();
  };

  const Btn = ({ title, onClick, children, label }) => (
    <Tooltip title={title}>
      <IconButton size="small" onMouseDown={(e) => e.preventDefault()} onClick={onClick}
        sx={{ color: 'text.secondary', borderRadius: 1, '&:hover': { color: 'text.primary', bgcolor: 'rgba(255,255,255,0.06)' } }}>
        {label ? <Typography sx={{ fontWeight: 800, fontSize: '0.78rem', px: 0.3 }}>{label}</Typography> : children}
      </IconButton>
    </Tooltip>
  );

  return (
    <Box>
      <Box sx={{
        display: 'flex', flexWrap: 'wrap', gap: 0.25, p: 0.5, mb: 0,
        border: `1px solid ${PALETTE.border1}`, borderBottom: 'none',
        borderRadius: '8px 8px 0 0', bgcolor: PALETTE.bg2, position: 'sticky', top: 0, zIndex: 2,
      }}>
        <Btn title="Heading" label="H2" onClick={() => exec('formatBlock', 'h2')} />
        <Btn title="Subheading" label="H3" onClick={() => exec('formatBlock', 'h3')} />
        <Btn title="Normal text" onClick={() => exec('formatBlock', 'p')}><TitleIcon fontSize="small" sx={{ opacity: 0.6 }} /></Btn>
        <Divider orientation="vertical" flexItem sx={{ mx: 0.5 }} />
        <Btn title="Bold (Ctrl+B)" onClick={() => exec('bold')}><FormatBold fontSize="small" /></Btn>
        <Btn title="Italic (Ctrl+I)" onClick={() => exec('italic')}><FormatItalic fontSize="small" /></Btn>
        <Btn title="Underline" onClick={() => exec('underline')}><FormatUnderlined fontSize="small" /></Btn>
        <Divider orientation="vertical" flexItem sx={{ mx: 0.5 }} />
        <Btn title="Bulleted list" onClick={() => exec('insertUnorderedList')}><FormatListBulleted fontSize="small" /></Btn>
        <Btn title="Numbered list" onClick={() => exec('insertOrderedList')}><FormatListNumbered fontSize="small" /></Btn>
        <Btn title="Quote" onClick={() => exec('formatBlock', 'blockquote')}><FormatQuote fontSize="small" /></Btn>
        <Btn title="Code block" onClick={() => exec('formatBlock', 'pre')}><Code fontSize="small" /></Btn>
        <Btn title="Divider line" onClick={() => exec('insertHorizontalRule')}><HorizontalRule fontSize="small" /></Btn>
        <Divider orientation="vertical" flexItem sx={{ mx: 0.5 }} />
        <Btn title="Insert link" onClick={addLink}><LinkIcon fontSize="small" /></Btn>
        <Btn title="Upload image" onClick={() => fileRef.current?.click()}><ImageIcon fontSize="small" /></Btn>
        <Btn title="Embed video (YouTube / Vimeo / Drive / Telegram)" onClick={addEmbed}><OndemandVideo fontSize="small" /></Btn>
        <Btn title="Clear formatting" onClick={() => exec('removeFormat')}><FormatClear fontSize="small" /></Btn>
        <input ref={fileRef} type="file" hidden accept="image/*" onChange={onFile} />
      </Box>
      <Box
        ref={ref}
        contentEditable
        suppressContentEditableWarning
        onInput={emit}
        onBlur={emit}
        onPaste={onPaste}
        sx={{
          minHeight: 380, p: 2, outline: 'none', fontSize: '1rem', lineHeight: 1.7,
          border: `1px solid ${PALETTE.border1}`, borderRadius: '0 0 8px 8px',
          bgcolor: PALETTE.bg1, color: 'text.primary',
          '& h2': { fontSize: '1.5rem', mt: 2, mb: 1, fontWeight: 700 },
          '& h3': { fontSize: '1.2rem', mt: 1.5, mb: 0.75, fontWeight: 700 },
          '& p': { my: 1 },
          '& img': { maxWidth: '100%', height: 'auto', display: 'block', my: 1.5, borderRadius: 1 },
          '& figure': { m: 0, my: 1.5 },
          '& figcaption': { fontSize: '0.85rem', color: 'text.secondary', textAlign: 'center', mt: 0.5 },
          '& blockquote': { borderLeft: `3px solid ${PALETTE.purpleLt}`, pl: 2, ml: 0, color: 'text.secondary', fontStyle: 'italic' },
          '& pre': { bgcolor: PALETTE.bg2, border: `1px solid ${PALETTE.border1}`, borderRadius: 1, p: 1.5, overflowX: 'auto', fontFamily: 'monospace', fontSize: '0.9rem' },
          '& hr': { border: 'none', borderTop: `1px solid ${PALETTE.border1}`, my: 2 },
          '& ul, & ol': { pl: 3 },
          '& a': { color: PALETTE.blueLt },
          '& .tg-embed': {
            border: `1px dashed ${PALETTE.border1}`, borderRadius: 1, p: 1.5, my: 1.5,
            color: 'text.secondary', bgcolor: PALETTE.bg2, fontSize: '0.9rem', textAlign: 'center',
          },
          '&:empty:before': { content: '"Write your article here… (paste a draft, then style with the toolbar)"', color: 'text.disabled' },
        }}
      />
    </Box>
  );
}

// ───────────────────────── Real-time SEO analyzer (deterministic) ─────────────
function analyzeSeo({ title, metaDescription, focusKeyword, html, slug }) {
  const text = (html || '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
  const words = (text.match(/\w+/g) || []).length;
  const kw = (focusKeyword || '').trim().toLowerCase();
  const has = (s) => kw && (s || '').toLowerCase().includes(kw);
  const headings = (html.match(/<h[23][^>]*>(.*?)<\/h[23]>/gi) || []).join(' ');
  const h2count = (html.match(/<h2/gi) || []).length;
  const imgs = html.match(/<img[^>]*>/gi) || [];
  const imgsWithAlt = imgs.filter((i) => /alt="[^"]+"/i.test(i)).length;
  const links = (html.match(/<a\s/gi) || []).length;
  const intro = text.slice(0, 320);

  const checks = [
    { state: title.length >= 40 && title.length <= 60 ? 'ok' : (title.length === 0 ? 'todo' : 'warn'),
      label: `Title length: ${title.length} chars (aim 40–60)` },
    { state: metaDescription.length >= 120 && metaDescription.length <= 160 ? 'ok' : (metaDescription.length === 0 ? 'todo' : 'warn'),
      label: `Meta description: ${metaDescription.length} chars (aim 120–160)` },
    { state: kw ? 'ok' : 'todo', label: kw ? `Focus keyword set: “${focusKeyword}”` : 'Set a focus keyword' },
    { state: !kw ? 'todo' : (has(title) ? 'ok' : 'warn'), label: 'Keyword appears in the title' },
    { state: !kw ? 'todo' : (has(intro) ? 'ok' : 'warn'), label: 'Keyword appears in the intro' },
    { state: !kw ? 'todo' : (has(headings) ? 'ok' : 'warn'), label: 'Keyword appears in a subheading' },
    { state: !kw ? 'todo' : (has(metaDescription) ? 'ok' : 'warn'), label: 'Keyword in meta description' },
    { state: !kw ? 'todo' : (has(slug) ? 'ok' : 'warn'), label: 'Keyword in the URL slug' },
    { state: h2count >= 1 ? 'ok' : 'warn', label: `Subheadings: ${h2count} H2 (use 2+)` },
    { state: words >= 600 ? 'ok' : (words >= 300 ? 'warn' : 'todo'), label: `Length: ${words} words (aim 600+, min 300)` },
    { state: imgs.length === 0 ? 'warn' : (imgsWithAlt === imgs.length ? 'ok' : 'warn'),
      label: imgs.length ? `Image alt text: ${imgsWithAlt}/${imgs.length} have alt` : 'Add at least one image' },
    { state: links >= 1 ? 'ok' : 'warn', label: `Links: ${links} (add internal/external links)` },
  ];
  const scored = checks.filter((c) => c.state !== 'todo');
  const passed = scored.filter((c) => c.state === 'ok').length;
  const score = scored.length ? Math.round((passed / scored.length) * 100) : 0;
  return { checks, score };
}

function SeoChecklist({ result }) {
  const color = result.score >= 80 ? '#22c55e' : result.score >= 50 ? '#f59e0b' : '#ef4444';
  const ICONS = {
    ok: <CheckCircle sx={{ fontSize: 16, color: '#22c55e' }} />,
    warn: <Warning sx={{ fontSize: 16, color: '#f59e0b' }} />,
    todo: <RadioButtonUnchecked sx={{ fontSize: 16, color: 'text.disabled' }} />,
  };
  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
        <Box sx={{ position: 'relative', display: 'inline-flex' }}>
          <CircularProgress variant="determinate" value={result.score} size={42} thickness={5} sx={{ color }} />
          <Box sx={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center' }}>
            <Typography fontSize="0.7rem" fontWeight={800}>{result.score}</Typography>
          </Box>
        </Box>
        <Typography variant="body2" color="text.secondary">
          Live SEO score — fixes update as you type. Aim for green before publishing.
        </Typography>
      </Box>
      <Stack spacing={0.5}>
        {result.checks.map((c, i) => (
          <Box key={i} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            {ICONS[c.state]}
            <Typography variant="caption" color={c.state === 'todo' ? 'text.disabled' : 'text.secondary'}>{c.label}</Typography>
          </Box>
        ))}
      </Stack>
    </Box>
  );
}

// ───────────────────────────────── Main tab ───────────────────────────────────
export default function BlogAdminTab({ onAdminError }) {
  const [view, setView] = useState('list');      // list | edit
  const [posts, setPosts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [post, setPost] = useState(emptyPost());
  const [bodyHtml, setBodyHtml] = useState('');
  const [slugTouched, setSlugTouched] = useState(false);
  const [tagInput, setTagInput] = useState('');
  const [saving, setSaving] = useState(false);
  const [scheduleAt, setScheduleAt] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    admin.listBlogPosts()
      .then(({ data }) => setPosts(data.posts || []))
      .catch((e) => onAdminError?.(e, 'Failed to load posts'))
      .finally(() => setLoading(false));
  }, [onAdminError]);

  useEffect(() => { load(); }, [load]);

  const uploadImage = async (file) => {
    const fd = new FormData();
    fd.append('file', file);
    const { data } = await admin.uploadBlogMedia(fd);
    return data.url;
  };

  const openNew = () => {
    setPost(emptyPost()); setBodyHtml(''); setSlugTouched(false);
    setScheduleAt(''); setView('edit');
  };
  const openEdit = async (id) => {
    try {
      const { data } = await admin.getBlogPost(id);
      setPost({ ...emptyPost(), ...data.post });
      setBodyHtml(data.post.body_html || '');
      setSlugTouched(true);
      setScheduleAt(data.post.status === 'scheduled' ? toLocalInput(data.post.published_at) : '');
      setView('edit');
    } catch (e) { onAdminError?.(e, 'Failed to open post'); }
  };

  const set = (patch) => setPost((p) => ({ ...p, ...patch }));

  const effectiveSlug = slugTouched ? post.slug : slugify(post.title);

  const save = async (status) => {
    if (!post.title.trim()) { toast.error('Add a title first.'); return; }
    let publishedAt = post.published_at;
    if (status === 'scheduled') {
      if (!scheduleAt) { toast.error('Pick a date & time to schedule.'); return; }
      const when = new Date(scheduleAt);
      if (isNaN(when.getTime()) || when <= new Date()) {
        toast.error('Pick a future date & time.'); return;
      }
      publishedAt = when.toISOString();
    }
    setSaving(true);
    const payload = {
      ...post, body_html: bodyHtml, slug: effectiveSlug,
      status: status || post.status, published_at: publishedAt,
    };
    try {
      let saved;
      if (post.id) {
        ({ data: saved } = await admin.updateBlogPost(post.id, payload));
      } else {
        ({ data: saved } = await admin.createBlogPost(payload));
      }
      setPost({ ...emptyPost(), ...saved.post });
      setBodyHtml(saved.post.body_html || '');
      setSlugTouched(true);
      setScheduleAt(saved.post.status === 'scheduled' ? toLocalInput(saved.post.published_at) : '');
      toast.success(
        saved.post.status === 'published' ? 'Published!'
          : saved.post.status === 'scheduled' ? `Scheduled for ${new Date(saved.post.published_at).toLocaleString()}.`
            : status === 'draft' ? 'Saved as draft.' : 'Saved.');
      load();
    } catch (e) { onAdminError?.(e, 'Save failed'); }
    finally { setSaving(false); }
  };

  const remove = async (id) => {
    if (!window.confirm('Delete this post permanently?')) return;
    try { await admin.deleteBlogPost(id); toast.success('Deleted.'); load(); }
    catch (e) { onAdminError?.(e, 'Delete failed'); }
  };

  const addTag = () => {
    const t = tagInput.trim();
    if (t && !(post.tags || []).includes(t)) set({ tags: [...(post.tags || []), t] });
    setTagInput('');
  };

  const seo = useMemo(() => analyzeSeo({
    title: post.meta_title || post.title, metaDescription: post.meta_description,
    focusKeyword: post.focus_keyword, html: bodyHtml, slug: effectiveSlug,
  }), [post.meta_title, post.title, post.meta_description, post.focus_keyword, bodyHtml, effectiveSlug]);

  // ── List view ──
  if (view === 'list') {
    return (
      <Box sx={{ p: { xs: 2, md: 3 } }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2, flexWrap: 'wrap', gap: 1 }}>
          <Box>
            <Typography variant="h5" fontWeight={800}>Blog</Typography>
            <Typography variant="body2" color="text.secondary">
              One blog for the whole site — published posts go live instantly at telegizer.com/blog.
            </Typography>
          </Box>
          <Button variant="contained" startIcon={<Add />} onClick={openNew}>New post</Button>
        </Box>
        <Card sx={{ bgcolor: PALETTE.bg1, border: `1px solid ${PALETTE.border1}` }}>
          {loading ? (
            <Box sx={{ display: 'grid', placeItems: 'center', py: 6 }}><CircularProgress /></Box>
          ) : posts.length === 0 ? (
            <Box sx={{ py: 6, textAlign: 'center' }}>
              <Typography color="text.secondary" mb={2}>No posts yet. Write your first one.</Typography>
              <Button variant="outlined" startIcon={<Add />} onClick={openNew}>New post</Button>
            </Box>
          ) : (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Title</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Category</TableCell>
                  <TableCell align="right">Views</TableCell>
                  <TableCell>Updated</TableCell>
                  <TableCell align="right">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {posts.map((p) => (
                  <TableRow key={p.id} hover>
                    <TableCell sx={{ maxWidth: 320 }}>
                      <Typography variant="body2" fontWeight={600} noWrap>{p.title}</Typography>
                      <Typography variant="caption" color="text.disabled">/blog/{p.slug}</Typography>
                    </TableCell>
                    <TableCell>
                      <Chip size="small" label={p.status}
                        color={p.status === 'published' ? 'success' : p.status === 'scheduled' ? 'warning' : 'default'}
                        variant={p.status === 'draft' ? 'outlined' : 'filled'} />
                    </TableCell>
                    <TableCell><Typography variant="caption">{p.category || '—'}</Typography></TableCell>
                    <TableCell align="right"><Typography variant="caption">{p.views}</Typography></TableCell>
                    <TableCell><Typography variant="caption" color="text.secondary">
                      {p.updated_at ? new Date(p.updated_at).toLocaleDateString() : '—'}</Typography></TableCell>
                    <TableCell align="right">
                      {p.status === 'published' && (
                        <Tooltip title="View live">
                          <IconButton size="small" component="a" href={`/blog/${p.slug}`} target="_blank" rel="noopener">
                            <Visibility fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      )}
                      <Button size="small" onClick={() => openEdit(p.id)}>Edit</Button>
                      <Tooltip title="Delete">
                        <IconButton size="small" color="error" onClick={() => remove(p.id)}>
                          <Delete fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Card>
      </Box>
    );
  }

  // ── Editor view ──
  return (
    <Box sx={{ p: { xs: 1.5, md: 3 } }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2, gap: 1, flexWrap: 'wrap' }}>
        <Button startIcon={<ArrowBack />} onClick={() => { setView('list'); load(); }}>All posts</Button>
        <Stack direction="row" spacing={1} alignItems="center">
          {post.id && post.status === 'published' && (
            <Button size="small" startIcon={<Visibility />} component="a"
              href={`/blog/${post.slug}`} target="_blank" rel="noopener">Preview</Button>
          )}
          <Button variant="outlined" disabled={saving} onClick={() => save('draft')}>Save draft</Button>
          <Button variant="contained" disabled={saving} onClick={() => save('published')}>
            {saving ? <CircularProgress size={18} /> : post.status === 'published' ? 'Update' : 'Publish'}
          </Button>
        </Stack>
      </Box>

      <Grid container spacing={2}>
        {/* Main column */}
        <Grid item xs={12} md={8}>
          <TextField fullWidth variant="standard" placeholder="Post title"
            value={post.title}
            onChange={(e) => set({ title: e.target.value })}
            InputProps={{ disableUnderline: true, sx: { fontSize: '1.8rem', fontWeight: 800 } }}
            sx={{ mb: 1 }} />
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 2 }}>
            <Typography variant="caption" color="text.disabled">telegizer.com/blog/</Typography>
            <TextField variant="standard" value={effectiveSlug}
              onChange={(e) => { setSlugTouched(true); set({ slug: slugify(e.target.value) }); }}
              InputProps={{ disableUnderline: true, sx: { fontSize: '0.8rem', color: PALETTE.blueLt } }} />
          </Box>
          <RichEditor initialHTML={post.body_html} onChange={setBodyHtml} onImageUpload={uploadImage} />
        </Grid>

        {/* Sidebar */}
        <Grid item xs={12} md={4}>
          <Stack spacing={2}>
            {/* Publishing / schedule */}
            <Card sx={{ bgcolor: PALETTE.bg1, border: `1px solid ${PALETTE.border1}` }}>
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                  <Schedule fontSize="small" sx={{ color: 'text.secondary' }} />
                  <Typography variant="subtitle2" fontWeight={700}>Publishing</Typography>
                </Box>
                <Chip size="small" label={post.status}
                  color={post.status === 'published' ? 'success' : post.status === 'scheduled' ? 'warning' : 'default'}
                  variant={post.status === 'draft' ? 'outlined' : 'filled'} sx={{ mb: 1 }} />
                {post.published_at && (
                  <Typography variant="caption" color="text.secondary" display="block" mb={1}>
                    {post.status === 'scheduled' ? 'Goes live: ' : 'Published: '}
                    {new Date(post.published_at).toLocaleString()}
                  </Typography>
                )}
                <TextField type="datetime-local" size="small" fullWidth label="Schedule for later"
                  value={scheduleAt} onChange={(e) => setScheduleAt(e.target.value)}
                  InputLabelProps={{ shrink: true }} sx={{ mt: 1 }} />
                <Button fullWidth variant="outlined" sx={{ mt: 1 }} disabled={!scheduleAt || saving}
                  onClick={() => save('scheduled')}>Schedule</Button>
                <Typography variant="caption" color="text.disabled" display="block" mt={1}>
                  The post auto-goes-live at that time — no need to come back.
                </Typography>
              </CardContent>
            </Card>

            {/* Cover image */}
            <Card sx={{ bgcolor: PALETTE.bg1, border: `1px solid ${PALETTE.border1}` }}>
              <CardContent>
                <Typography variant="subtitle2" fontWeight={700} mb={1}>Cover image</Typography>
                {post.cover_image_url ? (
                  <Box>
                    <Box component="img" src={post.cover_image_url} alt=""
                      sx={{ width: '100%', borderRadius: 1, mb: 1, display: 'block' }} />
                    <Button size="small" color="error" onClick={() => set({ cover_image_url: '' })}>Remove</Button>
                  </Box>
                ) : (
                  <Button variant="outlined" component="label" startIcon={<ImageIcon />} fullWidth>
                    Upload cover
                    <input type="file" hidden accept="image/*" onChange={async (e) => {
                      const f = e.target.files?.[0]; e.target.value = '';
                      if (!f) return;
                      try { set({ cover_image_url: await uploadImage(f) }); }
                      catch { toast.error('Upload failed'); }
                    }} />
                  </Button>
                )}
              </CardContent>
            </Card>

            {/* Organize */}
            <Card sx={{ bgcolor: PALETTE.bg1, border: `1px solid ${PALETTE.border1}` }}>
              <CardContent>
                <Typography variant="subtitle2" fontWeight={700} mb={1.5}>Organize</Typography>
                <TextField select size="small" fullWidth label="Category" value={post.category || ''}
                  onChange={(e) => set({ category: e.target.value })} sx={{ mb: 2 }}>
                  {CATEGORIES.map((c) => <MenuItem key={c} value={c}>{c}</MenuItem>)}
                </TextField>
                <TextField size="small" fullWidth label="Add a tag (Enter)" value={tagInput}
                  onChange={(e) => setTagInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addTag(); } }} />
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mt: 1 }}>
                  {(post.tags || []).map((t) => (
                    <Chip key={t} label={t} size="small" onDelete={() => set({ tags: post.tags.filter((x) => x !== t) })} />
                  ))}
                </Box>
                <TextField size="small" fullWidth label="Author" value={post.author_name || ''}
                  onChange={(e) => set({ author_name: e.target.value })} sx={{ mt: 2 }} />
                <TextField size="small" fullWidth multiline minRows={2} label="Excerpt (summary)" value={post.excerpt || ''}
                  onChange={(e) => set({ excerpt: e.target.value })} sx={{ mt: 2 }}
                  helperText="Shown on the blog index + used as the meta description if you leave that blank." />
              </CardContent>
            </Card>

            {/* SEO */}
            <Card sx={{ bgcolor: PALETTE.bg1, border: `1px solid ${PALETTE.border1}` }}>
              <CardContent>
                <Typography variant="subtitle2" fontWeight={700} mb={1.5}>SEO</Typography>
                <TextField size="small" fullWidth label="Focus keyword" value={post.focus_keyword || ''}
                  onChange={(e) => set({ focus_keyword: e.target.value })}
                  helperText="The phrase you want this post to rank for." sx={{ mb: 2 }} />
                <TextField size="small" fullWidth label="Meta title (optional)" value={post.meta_title || ''}
                  onChange={(e) => set({ meta_title: e.target.value })}
                  helperText={`${(post.meta_title || '').length} chars · defaults to the post title`} sx={{ mb: 2 }} />
                <TextField size="small" fullWidth multiline minRows={2} label="Meta description"
                  value={post.meta_description || ''}
                  onChange={(e) => set({ meta_description: e.target.value })}
                  helperText={`${(post.meta_description || '').length} / 160 chars`} sx={{ mb: 2 }} />
                <Divider sx={{ my: 1.5 }} />
                <SeoChecklist result={seo} />
                <Divider sx={{ my: 1.5 }} />
                <TextField size="small" fullWidth label="Canonical URL (optional)" value={post.canonical_url || ''}
                  onChange={(e) => set({ canonical_url: e.target.value })} sx={{ mb: 1 }} />
                <FormControlLabel
                  control={<Switch checked={!!post.noindex} onChange={(e) => set({ noindex: e.target.checked })} />}
                  label={<Typography variant="body2">Hide from search engines (noindex)</Typography>} />
              </CardContent>
            </Card>

            {post.id && (
              <Typography variant="caption" color="text.disabled">
                Status: {post.status}{post.published_at ? ` · published ${new Date(post.published_at).toLocaleDateString()}` : ''}
              </Typography>
            )}
            {saving && <LinearProgress />}
          </Stack>
        </Grid>
      </Grid>
    </Box>
  );
}
