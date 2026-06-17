import React from 'react';
import { Box, Stack, Collapse } from '@mui/material';
import { Telegram, Forum } from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';

// Platform-first launcher. Lives at the top of every product landing page and
// ROUTES between them (it is not an in-place swapper):
//   /                  → Telegram · Group Management (Telegizer)
//   /echo              → Telegram · Personal Assistant (Echo)
//   /guildizer-landing → Discord  · Server Management (Guildizer)
const PLATFORMS = [
  {
    key: 'telegram',
    label: 'Telegram',
    icon: <Telegram fontSize="small" />,
    accent: '#2196f3',
    accentGlow: 'rgba(33,150,243,0.45)',
    to: '/',
    modes: [
      { key: 'group', label: 'Group Management', product: 'Telegizer', to: '/' },
      { key: 'assistant', label: 'Personal Assistant', product: 'Echo', to: '/echo' },
    ],
  },
  {
    key: 'discord',
    label: 'Discord',
    icon: <Forum fontSize="small" />,
    accent: '#5865F2', // Discord blurple (official brand color)
    accentGlow: 'rgba(88,101,242,0.45)',
    to: '/guildizer-landing',
    modes: [],
  },
];

// active: 'telegram:group' | 'telegram:assistant' | 'discord:server'
export default function PlatformSwitcher({ active = 'telegram:group' }) {
  const navigate = useNavigate();
  const [activePlatform, activeMode] = active.split(':');

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      {/* Level 1 — platform */}
      <Box
        role="tablist"
        aria-label="Choose a platform"
        sx={{
          display: 'inline-flex', alignItems: 'center', gap: 0.5, p: 0.5, mb: 2.5,
          borderRadius: '999px', bgcolor: 'rgba(255,255,255,0.05)',
          border: '1px solid rgba(255,255,255,0.08)',
        }}
      >
        {PLATFORMS.map((p) => {
          const selected = activePlatform === p.key;
          const go = () => navigate(p.to);
          return (
            <Box
              key={p.key}
              role="tab"
              tabIndex={0}
              aria-selected={selected}
              onClick={go}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } }}
              sx={{
                cursor: 'pointer', userSelect: 'none',
                display: 'flex', alignItems: 'center', gap: 0.75,
                minHeight: 44, px: { xs: 2, sm: 2.75 }, borderRadius: '999px',
                fontWeight: 700, fontSize: { xs: '0.85rem', sm: '0.95rem' },
                color: selected ? '#fff' : 'text.secondary',
                bgcolor: selected ? p.accent : 'transparent',
                boxShadow: selected ? `0 6px 22px ${p.accentGlow}` : 'none',
                transition: 'background-color 0.25s ease, color 0.25s ease, box-shadow 0.25s ease',
                '&:hover': { color: '#fff' },
              }}
            >
              {p.icon}{p.label}
            </Box>
          );
        })}
      </Box>

      {/* Level 2 — Telegram sub-mode (Group vs Assistant) */}
      <Collapse in={activePlatform === 'telegram'} unmountOnExit>
        <Stack direction="row" spacing={1} justifyContent="center" sx={{ mb: 3 }}>
          {PLATFORMS[0].modes.map((m) => {
            const selected = activePlatform === 'telegram' && activeMode === m.key;
            const go = () => navigate(m.to);
            return (
              <Box
                key={m.key}
                role="tab"
                tabIndex={0}
                aria-selected={selected}
                onClick={go}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } }}
                sx={{
                  cursor: 'pointer', userSelect: 'none',
                  display: 'flex', alignItems: 'center', gap: 0.5,
                  minHeight: 40, px: { xs: 1.5, sm: 2 }, borderRadius: '999px',
                  fontWeight: 600, fontSize: { xs: '0.76rem', sm: '0.82rem' },
                  border: '1px solid',
                  borderColor: selected ? 'rgba(33,150,243,0.6)' : 'rgba(255,255,255,0.12)',
                  bgcolor: selected ? 'rgba(33,150,243,0.12)' : 'transparent',
                  color: selected ? '#fff' : 'text.secondary',
                  transition: 'all 0.2s ease',
                  '&:hover': { borderColor: 'rgba(255,255,255,0.3)', color: '#fff' },
                }}
              >
                {m.label}
                <Box component="span" sx={{ opacity: 0.55, fontWeight: 500 }}>· {m.product}</Box>
              </Box>
            );
          })}
        </Stack>
      </Collapse>
    </Box>
  );
}
