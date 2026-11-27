import React from 'react';
import { Box } from '@mui/material';
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
    icon: <Telegram sx={{ fontSize: 18 }} />,
    to: '/',
    modes: [
      { key: 'group', label: 'Groups', product: 'Telegizer', to: '/' },
      { key: 'assistant', label: 'Assistant', product: 'Echo', to: '/echo' },
    ],
  },
  {
    key: 'discord',
    label: 'Discord',
    icon: <Forum sx={{ fontSize: 18 }} />,
    to: '/guildizer-landing',
    modes: [],
  },
];

const EASE = 'cubic-bezier(0.22,1,0.36,1)';

function Tab({ selected, onGo, children, size = 'md' }) {
  return (
    <Box
      role="tab"
      tabIndex={0}
      aria-selected={selected}
      onClick={onGo}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onGo(); } }}
      sx={{
        cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap',
        display: 'flex', alignItems: 'center', gap: 0.75,
        minHeight: size === 'md' ? 36 : 32, px: size === 'md' ? 1.5 : 1.25, borderRadius: '8px',
        fontWeight: 500, fontSize: size === 'md' ? '0.875rem' : '0.8125rem',
        color: selected ? 'text.primary' : 'text.secondary',
        bgcolor: selected ? '#27282d' : 'transparent',
        boxShadow: selected ? 'inset 0 1px 0 rgba(255,255,255,0.06)' : 'none',
        transition: `background-color 0.16s ${EASE}, color 0.16s ${EASE}`,
        '&:hover': { color: 'text.primary' },
      }}
    >
      {children}
    </Box>
  );
}

// active: 'telegram:group' | 'telegram:assistant' | 'discord:server'
export default function PlatformSwitcher({ active = 'telegram:group', align = 'center' }) {
  const navigate = useNavigate();
  const [activePlatform, activeMode] = active.split(':');
  const telegram = PLATFORMS[0];

  return (
    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, alignItems: 'center', justifyContent: align === 'left' ? 'flex-start' : 'center', mb: 4 }}>
      {/* Level 1 — platform */}
      <Box
        role="tablist"
        aria-label="Choose a platform"
        sx={{ display: 'inline-flex', gap: 0.5, p: 0.5, borderRadius: '12px', bgcolor: '#18191c', border: '1px solid #26272b' }}
      >
        {PLATFORMS.map((p) => (
          <Tab key={p.key} selected={activePlatform === p.key} onGo={() => navigate(p.to)}>
            {p.icon}{p.label}
          </Tab>
        ))}
      </Box>

      {/* Level 2 — Telegram product (Group management vs Assistant) */}
      {activePlatform === 'telegram' && (
        <Box role="tablist" aria-label="Telegram product" sx={{ display: 'inline-flex', gap: 0.5 }}>
          {telegram.modes.map((m) => (
            <Tab key={m.key} size="sm" selected={activeMode === m.key} onGo={() => navigate(m.to)}>
              {m.label}
              <Box component="span" sx={{ color: 'text.disabled', fontWeight: 400 }}>{m.product}</Box>
            </Tab>
          ))}
        </Box>
      )}
    </Box>
  );
}
