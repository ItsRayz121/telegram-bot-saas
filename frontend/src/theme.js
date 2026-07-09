import { createTheme, alpha } from '@mui/material/styles';

// ── Design tokens ─────────────────────────────────────────────────────────────

export const PALETTE = {
  // Backgrounds — 4-level elevation system
  bg0: '#07101f',          // deepest: page background
  bg1: '#0b1626',          // sidebar, surface 1
  bg2: '#0f1e35',          // cards, surface 2
  bg3: '#162540',          // elevated cards, modals
  bg4: '#1c2e4a',          // tooltip, dropdown surface

  // Brand
  blue:   '#3d8ef8',       // electric blue — more vivid than flat #2563eb
  blueDk: '#1d6fd4',
  blueLt: '#7ab8ff',
  purple: '#9d6cf7',       // AI / assistant accent
  purpleDk: '#6d3fd4',
  purpleLt: '#c4a8ff',
  cyan:   '#22d3ee',       // info / telemetry

  // Status
  green:  '#22c55e',
  amber:  '#f59e0b',
  red:    '#ef4444',

  // Text
  text1: '#e8edf5',        // primary text
  text2: '#8fa3bc',        // secondary
  text3: '#4d6380',        // disabled / label

  // Borders
  border1: '#1e3352',      // default divider
  border2: '#274060',      // elevated divider

  // Glow values (rgba strings for use in box-shadow)
  glowBlue:   'rgba(61,142,248,0.28)',
  glowPurple: 'rgba(157,108,247,0.28)',
  glowCyan:   'rgba(34,211,238,0.22)',
};

// ── MUI theme ─────────────────────────────────────────────────────────────────

const telegizer = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main:  PALETTE.blue,
      light: PALETTE.blueLt,
      dark:  PALETTE.blueDk,
    },
    secondary: {
      main:  PALETTE.purple,
      light: PALETTE.purpleLt,
      dark:  PALETTE.purpleDk,
    },
    info: { main: PALETTE.cyan },
    success: { main: PALETTE.green },
    warning: { main: PALETTE.amber },
    error:   { main: PALETTE.red },
    background: {
      default: PALETTE.bg0,
      paper:   PALETTE.bg1,
    },
    divider: PALETTE.border1,
    text: {
      primary:   PALETTE.text1,
      secondary: PALETTE.text2,
      disabled:  PALETTE.text3,
    },
  },

  typography: {
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    fontWeightLight: 300,
    fontWeightRegular: 400,
    fontWeightMedium: 500,
    fontWeightBold: 700,
    h1: { fontWeight: 800, letterSpacing: '-0.03em', lineHeight: 1.1 },
    h2: { fontWeight: 800, letterSpacing: '-0.025em', lineHeight: 1.15 },
    h3: {
      fontWeight: 700,
      letterSpacing: '-0.02em',
      lineHeight: 1.2,
      fontSize: '1.6rem',
      '@media (min-width:600px)': { fontSize: '2rem' },
      '@media (min-width:900px)': { fontSize: '3rem' },
    },
    h4: {
      fontWeight: 700,
      letterSpacing: '-0.018em',
      lineHeight: 1.25,
      fontSize: '1.35rem',
      '@media (min-width:600px)': { fontSize: '1.65rem' },
      '@media (min-width:900px)': { fontSize: '2.125rem' },
    },
    h5: {
      fontWeight: 600,
      letterSpacing: '-0.015em',
      lineHeight: 1.3,
      fontSize: '1.1rem',
      '@media (min-width:600px)': { fontSize: '1.25rem' },
      '@media (min-width:900px)': { fontSize: '1.5rem' },
    },
    h6: {
      fontWeight: 600,
      letterSpacing: '-0.01em',
      lineHeight: 1.35,
      fontSize: '0.975rem',
      '@media (min-width:600px)': { fontSize: '1.05rem' },
      '@media (min-width:900px)': { fontSize: '1.25rem' },
    },
    subtitle1: {
      fontWeight: 500,
      fontSize: '0.9rem',
      '@media (min-width:600px)': { fontSize: '1rem' },
    },
    subtitle2: { fontWeight: 500, fontSize: '0.82rem' },
    body1: { fontSize: '0.9rem', lineHeight: 1.65 },
    // Floor body text at a comfortable size for the Telegram WebView (iOS text
    // boosting is disabled app-wide), nudging up slightly on roomier screens.
    body2: { fontSize: '0.82rem', lineHeight: 1.6, '@media (min-width:600px)': { fontSize: '0.85rem' } },
    caption: { fontSize: '0.72rem', letterSpacing: '0.02em' },
    overline: { fontSize: '0.65rem', letterSpacing: '0.1em', fontWeight: 700 },
  },

  shape: { borderRadius: 12 },

  shadows: [
    'none',
    `0 1px 3px rgba(0,0,0,0.5)`,
    `0 2px 6px rgba(0,0,0,0.5)`,
    `0 4px 12px rgba(0,0,0,0.5)`,
    `0 6px 20px rgba(0,0,0,0.55)`,
    `0 8px 28px rgba(0,0,0,0.6)`,
    `0 10px 36px rgba(0,0,0,0.6)`,
    `0 12px 44px rgba(0,0,0,0.65)`,
    `0 14px 52px rgba(0,0,0,0.65)`,
    `0 16px 60px rgba(0,0,0,0.7)`,
    `0 18px 68px rgba(0,0,0,0.7)`,
    `0 20px 76px rgba(0,0,0,0.72)`,
    `0 22px 84px rgba(0,0,0,0.72)`,
    `0 24px 92px rgba(0,0,0,0.74)`,
    `0 26px 100px rgba(0,0,0,0.74)`,
    `0 28px 108px rgba(0,0,0,0.76)`,
    `0 30px 116px rgba(0,0,0,0.76)`,
    `0 32px 124px rgba(0,0,0,0.78)`,
    `0 34px 132px rgba(0,0,0,0.78)`,
    `0 36px 140px rgba(0,0,0,0.8)`,
    `0 38px 148px rgba(0,0,0,0.8)`,
    `0 40px 156px rgba(0,0,0,0.82)`,
    `0 42px 164px rgba(0,0,0,0.82)`,
    `0 44px 172px rgba(0,0,0,0.84)`,
    `0 46px 180px rgba(0,0,0,0.84)`,
  ],

  components: {
    // ── Button ───────────────────────────────────────────────────────────────
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: {
          textTransform: 'none',
          borderRadius: 10,
          fontWeight: 500,
          letterSpacing: '-0.01em',
          transition: 'all 0.18s ease',
        },
        contained: {
          background: `linear-gradient(135deg, ${PALETTE.blue} 0%, ${PALETTE.blueDk} 100%)`,
          boxShadow: `0 2px 12px ${PALETTE.glowBlue}`,
          '&:hover': {
            background: `linear-gradient(135deg, #4d9bff 0%, ${PALETTE.blue} 100%)`,
            boxShadow: `0 4px 20px ${PALETTE.glowBlue}`,
            transform: 'translateY(-1px)',
          },
          '&:active': { transform: 'translateY(0)' },
        },
        containedSecondary: {
          background: `linear-gradient(135deg, ${PALETTE.purple} 0%, ${PALETTE.purpleDk} 100%)`,
          boxShadow: `0 2px 12px ${PALETTE.glowPurple}`,
          '&:hover': {
            boxShadow: `0 4px 20px ${PALETTE.glowPurple}`,
            transform: 'translateY(-1px)',
          },
        },
        outlined: {
          borderColor: PALETTE.border2,
          '&:hover': {
            borderColor: PALETTE.blue,
            boxShadow: `0 0 0 1px ${alpha(PALETTE.blue, 0.35)}`,
            bgcolor: alpha(PALETTE.blue, 0.06),
          },
        },
      },
    },

    // ── Card ─────────────────────────────────────────────────────────────────
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 14,
          border: `1px solid ${PALETTE.border1}`,
          background: PALETTE.bg2,
          backgroundImage: 'none',
          boxShadow: `0 2px 8px rgba(0,0,0,0.4)`,
          transition: 'box-shadow 0.2s ease, transform 0.2s cubic-bezier(0.22,1,0.36,1), border-color 0.2s ease',
          '&:hover': {
            boxShadow: `0 8px 32px rgba(0,0,0,0.5), 0 0 0 1px ${PALETTE.border2}, 0 0 20px -4px rgba(61,142,248,0.12)`,
            transform: 'translateY(-2px)',
            borderColor: 'rgba(61,142,248,0.25)',
          },
        },
      },
    },

    // ── Paper ────────────────────────────────────────────────────────────────
    MuiPaper: {
      styleOverrides: {
        root: {
          borderRadius: 14,
          backgroundImage: 'none',
          background: PALETTE.bg1,
        },
        elevation1: { boxShadow: `0 2px 8px rgba(0,0,0,0.4)` },
        elevation2: { boxShadow: `0 4px 16px rgba(0,0,0,0.45)` },
        elevation3: { boxShadow: `0 6px 24px rgba(0,0,0,0.5)` },
      },
    },

    // ── CardContent ──────────────────────────────────────────────────────────
    MuiCardContent: {
      styleOverrides: {
        root: {
          padding: '14px',
          '&:last-child': { paddingBottom: '14px' },
          '@media (min-width:600px)': { padding: '20px', '&:last-child': { paddingBottom: '20px' } },
          '@media (min-width:900px)': { padding: '24px', '&:last-child': { paddingBottom: '24px' } },
        },
      },
    },

    // ── Toolbar ──────────────────────────────────────────────────────────────
    MuiToolbar: {
      styleOverrides: {
        root: {
          '@media (max-width:599px)': { minHeight: '52px !important' },
        },
      },
    },

    // ── AppBar ───────────────────────────────────────────────────────────────
    MuiAppBar: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
          // Fully opaque — a translucent header + backdrop-filter bleeds page
          // content through the sticky bar in WebViews that don't render
          // backdrop-filter (notably the Telegram Mini App), which made section
          // headers/banners look "half pushed above" the fixed boundary on scroll.
          backgroundColor: PALETTE.bg1,
          boxShadow: 'none',
          borderBottom: `1px solid ${PALETTE.border1}`,
        },
      },
    },

    // ── Dialog ───────────────────────────────────────────────────────────────
    MuiDialog: {
      styleOverrides: {
        paper: {
          background: PALETTE.bg3,
          border: `1px solid ${PALETTE.border2}`,
          boxShadow: `0 24px 80px rgba(0,0,0,0.7), 0 0 0 1px ${PALETTE.border2}`,
        },
      },
    },

    // ── Popover ──────────────────────────────────────────────────────────────
    MuiPopover: {
      styleOverrides: {
        paper: {
          background: PALETTE.bg3,
          border: `1px solid ${PALETTE.border2}`,
          boxShadow: `0 16px 60px rgba(0,0,0,0.7)`,
        },
      },
    },

    // ── Menu ─────────────────────────────────────────────────────────────────
    MuiMenu: {
      styleOverrides: {
        paper: {
          background: PALETTE.bg3,
          border: `1px solid ${PALETTE.border2}`,
          boxShadow: `0 12px 40px rgba(0,0,0,0.65)`,
        },
      },
    },

    // ── MenuItem ─────────────────────────────────────────────────────────────
    MuiMenuItem: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          mx: 0.5,
          transition: 'background 0.12s ease',
          '&:hover': { background: alpha(PALETTE.blue, 0.1) },
          '&.Mui-selected': {
            background: alpha(PALETTE.blue, 0.15),
            '&:hover': { background: alpha(PALETTE.blue, 0.2) },
          },
        },
      },
    },

    // ── TextField ────────────────────────────────────────────────────────────
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          borderRadius: 10,
          background: PALETTE.bg1,
          transition: 'box-shadow 0.18s ease, border-color 0.18s ease',
          '& .MuiOutlinedInput-notchedOutline': {
            borderColor: PALETTE.border1,
            transition: 'border-color 0.18s ease',
          },
          '&:hover .MuiOutlinedInput-notchedOutline': {
            borderColor: PALETTE.border2,
          },
          '&.Mui-focused': {
            boxShadow: `0 0 0 3px ${alpha(PALETTE.blue, 0.2)}`,
            '& .MuiOutlinedInput-notchedOutline': { borderColor: PALETTE.blue },
          },
        },
      },
    },

    // ── Chip ─────────────────────────────────────────────────────────────────
    MuiChip: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          fontWeight: 500,
          fontSize: '0.72rem',
        },
      },
    },

    // ── Tooltip ──────────────────────────────────────────────────────────────
    MuiTooltip: {
      styleOverrides: {
        tooltip: {
          background: PALETTE.bg4,
          border: `1px solid ${PALETTE.border2}`,
          boxShadow: `0 8px 32px rgba(0,0,0,0.6)`,
          fontSize: '0.72rem',
          borderRadius: 8,
          padding: '6px 10px',
        },
        arrow: { color: PALETTE.bg4 },
      },
    },

    // ── Tabs ─────────────────────────────────────────────────────────────────
    MuiTab: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          fontWeight: 500,
          fontSize: '0.85rem',
          letterSpacing: '-0.01em',
          minHeight: 40,
          transition: 'color 0.15s ease',
        },
      },
    },

    // ── Divider ──────────────────────────────────────────────────────────────
    MuiDivider: {
      styleOverrides: {
        root: { borderColor: PALETTE.border1 },
      },
    },

    // ── LinearProgress ────────────────────────────────────────────────────────
    MuiLinearProgress: {
      styleOverrides: {
        root: {
          borderRadius: 6,
          height: 6,
          background: alpha(PALETTE.blue, 0.12),
        },
        bar: {
          borderRadius: 6,
          background: `linear-gradient(90deg, ${PALETTE.blue}, ${PALETTE.cyan})`,
        },
      },
    },

    // ── Accordion ────────────────────────────────────────────────────────────
    MuiAccordion: {
      styleOverrides: {
        root: {
          background: PALETTE.bg2,
          border: `1px solid ${PALETTE.border1}`,
          borderRadius: '12px !important',
          '&:before': { display: 'none' },
          '&.Mui-expanded': { margin: 0 },
        },
      },
    },

    // ── Switch ───────────────────────────────────────────────────────────────
    MuiSwitch: {
      styleOverrides: {
        switchBase: {
          '&.Mui-checked + .MuiSwitch-track': {
            background: `linear-gradient(90deg, ${PALETTE.blue}, ${PALETTE.purple})`,
            opacity: 1,
          },
        },
        track: { borderRadius: 16 },
      },
    },

    // ── TableRow ─────────────────────────────────────────────────────────────
    MuiTableRow: {
      styleOverrides: {
        root: {
          transition: 'background 0.12s ease',
          '&:hover': { background: alpha(PALETTE.blue, 0.04) },
        },
      },
    },

    // ── TableCell ────────────────────────────────────────────────────────────
    MuiTableCell: {
      styleOverrides: {
        root: {
          borderColor: PALETTE.border1,
          fontSize: '0.82rem',
        },
        head: {
          fontWeight: 600,
          fontSize: '0.72rem',
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
          color: PALETTE.text3,
        },
      },
    },

    // ── Drawer ───────────────────────────────────────────────────────────────
    MuiDrawer: {
      styleOverrides: {
        paper: {
          background: PALETTE.bg1,
          borderRight: `1px solid ${PALETTE.border1}`,
        },
      },
    },

    // ── BottomNavigation ─────────────────────────────────────────────────────
    MuiBottomNavigation: {
      styleOverrides: {
        root: {
          background: alpha(PALETTE.bg1, 0.95),
          backdropFilter: 'blur(16px)',
        },
      },
    },

    // ── Alert ────────────────────────────────────────────────────────────────
    MuiAlert: {
      styleOverrides: {
        root: {
          borderRadius: 12,
          border: '1px solid',
          fontSize: '0.82rem',
        },
        standardInfo: {
          background: alpha(PALETTE.blue, 0.1),
          borderColor: alpha(PALETTE.blue, 0.3),
        },
        standardSuccess: {
          background: alpha(PALETTE.green, 0.1),
          borderColor: alpha(PALETTE.green, 0.3),
        },
        standardWarning: {
          background: alpha(PALETTE.amber, 0.1),
          borderColor: alpha(PALETTE.amber, 0.3),
        },
        standardError: {
          background: alpha(PALETTE.red, 0.1),
          borderColor: alpha(PALETTE.red, 0.3),
        },
      },
    },

    // ── Stepper ──────────────────────────────────────────────────────────────
    MuiStepLabel: {
      styleOverrides: {
        label: { fontSize: '0.85rem' },
      },
    },
  },
});

export default telegizer;
