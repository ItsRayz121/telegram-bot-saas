import { createTheme, alpha } from '@mui/material/styles';

// ── Design tokens ─────────────────────────────────────────────────────────────
// Graphite surfaces, one accent (Telegram sky blue), three text roles. Depth comes
// from surface steps and hairlines, not glows. Key names are kept stable because
// pages import PALETTE directly.

export const PALETTE = {
  // Surfaces — darkest to most raised
  bg0: '#0f1012',          // page background
  bg1: '#131416',          // sidebar, app bar, paper
  bg2: '#18191c',          // cards
  bg3: '#1f2024',          // raised: dialogs, menus, active rows, inputs
  bg4: '#27282d',          // tooltips

  // Accent — the only chrome colour. Used for selection, links and key figures.
  blue:   '#4a9ff5',
  blueDk: '#2a6fb8',       // filled chips / text-on-accent (white passes 5.2:1)
  blueLt: '#8cc2f7',
  // Secondary hue for AI / assistant and second chart series (was violet)
  purple:   '#4fb3a5',
  purpleDk: '#2a7d71',
  purpleLt: '#8fd3c8',
  cyan:     '#62b3cf',     // info / third chart series

  // Status — toned to sit inside the graphite ramp
  green:  '#4cc38a',
  amber:  '#e2a336',
  red:    '#eb5257',

  // Text
  text1: '#ececee',        // primary
  text2: '#a3a5ac',        // secondary
  text3: '#909299',        // muted (4.8:1+ on cards)

  // Hairlines (solid so they can be concatenated with alpha hex suffixes)
  border1: '#26272b',
  border2: '#323338',

  // Glows are retired. Kept as transparent so old box-shadow strings render nothing.
  glowBlue:   'rgba(0,0,0,0)',
  glowPurple: 'rgba(0,0,0,0)',
  glowCyan:   'rgba(0,0,0,0)',
};

export const FONT_SANS = "'IBM Plex Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
export const FONT_MONO = "'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";

const EASE = 'cubic-bezier(0.22, 1, 0.36, 1)';
const HIGHLIGHT = 'inset 0 1px 0 rgba(255,255,255,0.06)';

// ── MUI theme ─────────────────────────────────────────────────────────────────

const telegizer = createTheme({
  palette: {
    mode: 'dark',
    primary: { main: PALETTE.blue, light: PALETTE.blueLt, dark: PALETTE.blueDk, contrastText: '#0f1012' },
    secondary: { main: PALETTE.purple, light: PALETTE.purpleLt, dark: PALETTE.purpleDk, contrastText: '#0f1012' },
    info: { main: PALETTE.cyan },
    success: { main: PALETTE.green },
    warning: { main: PALETTE.amber },
    error: { main: PALETTE.red },
    background: { default: PALETTE.bg0, paper: PALETTE.bg1 },
    divider: PALETTE.border1,
    text: { primary: PALETTE.text1, secondary: PALETTE.text2, disabled: PALETTE.text3 },
    action: {
      hover: 'rgba(236,236,238,0.05)',
      selected: 'rgba(236,236,238,0.08)',
      focus: 'rgba(236,236,238,0.10)',
    },
  },

  typography: {
    fontFamily: FONT_SANS,
    fontWeightLight: 400,
    fontWeightRegular: 400,
    fontWeightMedium: 500,
    fontWeightBold: 600,
    h1: { fontWeight: 500, letterSpacing: '-0.03em', lineHeight: 1.05 },
    h2: { fontWeight: 500, letterSpacing: '-0.025em', lineHeight: 1.1 },
    h3: {
      fontWeight: 500,
      letterSpacing: '-0.02em',
      lineHeight: 1.15,
      fontSize: '1.6rem',
      '@media (min-width:600px)': { fontSize: '2rem' },
      '@media (min-width:900px)': { fontSize: '2.5rem' },
    },
    h4: {
      fontWeight: 500,
      letterSpacing: '-0.015em',
      lineHeight: 1.2,
      fontSize: '1.4rem',
      '@media (min-width:600px)': { fontSize: '1.6rem' },
      '@media (min-width:900px)': { fontSize: '1.9rem' },
    },
    h5: {
      fontWeight: 500,
      letterSpacing: '-0.01em',
      lineHeight: 1.3,
      fontSize: '1.15rem',
      '@media (min-width:600px)': { fontSize: '1.25rem' },
      '@media (min-width:900px)': { fontSize: '1.375rem' },
    },
    h6: {
      fontWeight: 500,
      letterSpacing: 0,
      lineHeight: 1.35,
      fontSize: '1rem',
      '@media (min-width:600px)': { fontSize: '1.05rem' },
      '@media (min-width:900px)': { fontSize: '1.125rem' },
    },
    subtitle1: {
      fontWeight: 500,
      fontSize: '0.9375rem',
      '@media (min-width:600px)': { fontSize: '1rem' },
    },
    subtitle2: { fontWeight: 500, fontSize: '0.875rem' },
    body1: { fontSize: '0.9375rem', lineHeight: 1.6 },
    // Floor body text at a comfortable size for the Telegram WebView (iOS text
    // boosting is disabled app-wide).
    body2: { fontSize: '0.84rem', lineHeight: 1.55, '@media (min-width:600px)': { fontSize: '0.875rem' } },
    caption: { fontSize: '0.78rem', lineHeight: 1.4, letterSpacing: 0 },
    // Overlines were uppercase and tracked; now a quiet sentence-case label.
    overline: { fontSize: '0.8125rem', letterSpacing: 0, fontWeight: 500, textTransform: 'none', lineHeight: 1.5 },
    button: { fontWeight: 500, letterSpacing: 0 },
  },

  shape: { borderRadius: 8 },

  // Dark theme: depth comes from surfaces and hairlines. Shadows stay soft and neutral
  // for things that float (menus, dialogs).
  shadows: [
    'none',
    '0 1px 2px rgba(0,0,0,0.3)',
    '0 2px 4px rgba(0,0,0,0.3)',
    '0 4px 10px rgba(0,0,0,0.32)',
    ...Array.from({ length: 21 }, (_, i) => `0 ${6 + i * 2}px ${16 + i * 4}px rgba(0,0,0,0.36)`),
  ],

  transitions: {
    easing: { easeOut: EASE, easeInOut: EASE },
  },

  components: {
    // ── Button ───────────────────────────────────────────────────────────────
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: {
          textTransform: 'none',
          borderRadius: 8,
          fontWeight: 500,
          letterSpacing: 0,
          transition: `background-color 0.16s ${EASE}, border-color 0.16s ${EASE}, color 0.16s ${EASE}, transform 0.12s ${EASE}`,
          '&:active:not(.Mui-disabled)': { transform: 'scale(0.98)' },
          '&.Mui-disabled': { transform: 'none' },
          // Touch screens: keep small buttons at a comfortable tap height
          '@media (pointer: coarse)': { minHeight: 40 },
        },
        sizeLarge: { minHeight: 44, padding: '10px 20px', fontSize: '0.9375rem' },
        // Primary action: off-white with dark text. The accent is kept for selection and figures.
        containedPrimary: {
          backgroundColor: PALETTE.text1,
          color: '#111214',
          boxShadow: HIGHLIGHT,
          '@media (hover: hover)': { '&:hover': { backgroundColor: '#ffffff', boxShadow: HIGHLIGHT } },
          '&.Mui-disabled': { backgroundColor: alpha(PALETTE.text1, 0.12), color: alpha(PALETTE.text1, 0.4) },
        },
        containedSecondary: {
          backgroundColor: PALETTE.bg3,
          color: PALETTE.text1,
          border: `1px solid ${PALETTE.border2}`,
          '@media (hover: hover)': { '&:hover': { backgroundColor: PALETTE.bg4 } },
        },
        containedInherit: {
          backgroundColor: PALETTE.bg3,
          color: PALETTE.text1,
          '@media (hover: hover)': { '&:hover': { backgroundColor: PALETTE.bg4 } },
        },
        outlined: {
          borderColor: PALETTE.border2,
          '@media (hover: hover)': { '&:hover': { borderColor: alpha(PALETTE.text1, 0.24), backgroundColor: alpha(PALETTE.text1, 0.04) } },
        },
        outlinedPrimary: { color: PALETTE.text1 },
        text: { '@media (hover: hover)': { '&:hover': { backgroundColor: alpha(PALETTE.text1, 0.05) } } },
      },
    },

    // Every spinner / bar gets an accessible name by default (a specific aria-label on the element still wins).
    MuiCircularProgress: { defaultProps: { 'aria-label': 'Loading' } },

    // ── Card ─────────────────────────────────────────────────────────────────
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 12,
          border: `1px solid ${PALETTE.border1}`,
          background: PALETTE.bg2,
          backgroundImage: 'none',
          boxShadow: 'none',
          transition: `border-color 0.16s ${EASE}, background-color 0.16s ${EASE}`,
          // Only cards that are actually clickable react to hover.
          '@media (hover: hover)': {
            '&:has(> .MuiCardActionArea-root):hover': { borderColor: PALETTE.border2, backgroundColor: '#1b1c20' },
          },
        },
      },
    },

    // ── Paper ────────────────────────────────────────────────────────────────
    MuiPaper: {
      styleOverrides: {
        root: { borderRadius: 12, backgroundImage: 'none', background: PALETTE.bg1 },
        elevation0: { boxShadow: 'none' },
        elevation1: { boxShadow: 'none', border: `1px solid ${PALETTE.border1}` },
        elevation2: { boxShadow: 'none', border: `1px solid ${PALETTE.border1}` },
        elevation3: { boxShadow: 'none', border: `1px solid ${PALETTE.border1}` },
      },
    },

    // ── CardContent ──────────────────────────────────────────────────────────
    MuiCardContent: {
      styleOverrides: {
        root: {
          padding: '16px',
          '&:last-child': { paddingBottom: '16px' },
          '@media (min-width:600px)': { padding: '20px', '&:last-child': { paddingBottom: '20px' } },
          '@media (min-width:900px)': { padding: '24px', '&:last-child': { paddingBottom: '24px' } },
        },
      },
    },

    // ── Toolbar ──────────────────────────────────────────────────────────────
    MuiToolbar: {
      styleOverrides: {
        root: { '@media (max-width:599px)': { minHeight: '56px !important' } },
      },
    },

    // ── AppBar ───────────────────────────────────────────────────────────────
    MuiAppBar: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
          // Fully opaque: translucent headers bleed content through in WebViews
          // without backdrop-filter (notably the Telegram Mini App).
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
          borderRadius: 16,
          background: PALETTE.bg3,
          border: `1px solid ${PALETTE.border2}`,
          boxShadow: '0 24px 64px rgba(0,0,0,0.5)',
          animation: `dialogIn 0.24s ${EASE}`,
        },
      },
    },
    MuiDialogTitle: { styleOverrides: { root: { fontWeight: 500, fontSize: '1.125rem' } } },
    MuiBackdrop: { styleOverrides: { root: { '&:not(.MuiBackdrop-invisible)': { backgroundColor: 'rgba(8,8,10,0.66)' } } } },

    // ── Popover / Menu ───────────────────────────────────────────────────────
    MuiPopover: {
      styleOverrides: {
        paper: { background: PALETTE.bg3, border: `1px solid ${PALETTE.border2}`, boxShadow: '0 12px 32px rgba(0,0,0,0.45)' },
      },
    },
    MuiMenu: {
      styleOverrides: {
        paper: { background: PALETTE.bg3, border: `1px solid ${PALETTE.border2}`, boxShadow: '0 12px 32px rgba(0,0,0,0.45)' },
        list: { padding: 4 },
      },
    },
    MuiMenuItem: {
      styleOverrides: {
        root: {
          borderRadius: 6,
          minHeight: 36,
          fontSize: '0.875rem',
          transition: `background-color 0.12s ${EASE}`,
          '&:hover': { background: alpha(PALETTE.text1, 0.06) },
          '&.Mui-selected': {
            background: alpha(PALETTE.text1, 0.08),
            '&:hover': { background: alpha(PALETTE.text1, 0.1) },
          },
        },
      },
    },

    // ── TextField ────────────────────────────────────────────────────────────
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          background: PALETTE.bg1,
          transition: `box-shadow 0.16s ${EASE}`,
          '& .MuiOutlinedInput-notchedOutline': { borderColor: PALETTE.border2, transition: `border-color 0.16s ${EASE}` },
          '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: alpha(PALETTE.text1, 0.22) },
          '&.Mui-focused': {
            boxShadow: `0 0 0 3px ${alpha(PALETTE.blue, 0.18)}`,
            '& .MuiOutlinedInput-notchedOutline': { borderColor: PALETTE.blue, borderWidth: 1 },
          },
        },
      },
    },
    MuiInputLabel: { styleOverrides: { root: { '&.Mui-focused': { color: PALETTE.blueLt } } } },

    // ── Chip ─────────────────────────────────────────────────────────────────
    MuiChip: {
      styleOverrides: {
        root: { borderRadius: 6, fontWeight: 500, fontSize: '0.75rem' },
        // White on the accent is only 2.6:1; the darker accent passes WCAG AA.
        colorPrimary: { '&.MuiChip-filled': { backgroundColor: PALETTE.blueDk, color: '#fff' } },
        colorSecondary: { '&.MuiChip-filled': { backgroundColor: PALETTE.purpleDk, color: '#fff' } },
        // Status chips are quiet: tinted text on a faint wash, not a solid block.
        colorSuccess: { '&.MuiChip-filled': { backgroundColor: alpha(PALETTE.green, 0.14), color: PALETTE.green } },
        colorWarning: { '&.MuiChip-filled': { backgroundColor: alpha(PALETTE.amber, 0.14), color: PALETTE.amber } },
        colorError: { '&.MuiChip-filled': { backgroundColor: alpha(PALETTE.red, 0.14), color: '#f07c80' } },
        colorInfo: { '&.MuiChip-filled': { backgroundColor: alpha(PALETTE.cyan, 0.14), color: PALETTE.cyan } },
        outlined: { borderColor: PALETTE.border2 },
      },
    },

    // ── Link ─────────────────────────────────────────────────────────────────
    // Links inside body text must be recognisable without relying on colour alone.
    MuiLink: {
      styleOverrides: {
        root: { textUnderlineOffset: '3px' },
        underlineHover: { '.MuiTypography-root:not(a) &': { textDecoration: 'underline' } },
      },
    },

    // ── Tooltip ──────────────────────────────────────────────────────────────
    MuiTooltip: {
      styleOverrides: {
        tooltip: {
          background: PALETTE.bg4,
          border: `1px solid ${PALETTE.border2}`,
          boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
          fontSize: '0.75rem',
          fontWeight: 400,
          borderRadius: 6,
          padding: '6px 10px',
        },
        arrow: { color: PALETTE.bg4 },
      },
    },

    // ── Tabs ─────────────────────────────────────────────────────────────────
    MuiTabs: { styleOverrides: { indicator: { backgroundColor: PALETTE.text1, height: 2 } } },
    MuiTab: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          fontWeight: 500,
          fontSize: '0.875rem',
          letterSpacing: 0,
          minHeight: 44,
          color: PALETTE.text2,
          transition: `color 0.16s ${EASE}`,
          '&.Mui-selected': { color: PALETTE.text1 },
        },
      },
    },

    // ── ToggleButton ─────────────────────────────────────────────────────────
    MuiToggleButton: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          borderColor: PALETTE.border2,
          '&.Mui-selected, &.Mui-selected:hover': { backgroundColor: PALETTE.bg4, color: PALETTE.text1 },
        },
      },
    },

    // ── Divider ──────────────────────────────────────────────────────────────
    MuiDivider: { styleOverrides: { root: { borderColor: PALETTE.border1 } } },

    // ── Progress ─────────────────────────────────────────────────────────────
    MuiLinearProgress: {
      defaultProps: { 'aria-label': 'Loading' },
      styleOverrides: {
        root: { borderRadius: 4, height: 6, background: alpha(PALETTE.text1, 0.08) },
        bar: { borderRadius: 4 },
      },
    },

    // ── Accordion ────────────────────────────────────────────────────────────
    MuiAccordion: {
      styleOverrides: {
        root: {
          background: PALETTE.bg2,
          border: `1px solid ${PALETTE.border1}`,
          borderRadius: '12px !important',
          boxShadow: 'none',
          '&:before': { display: 'none' },
          '&.Mui-expanded': { margin: 0 },
        },
      },
    },

    // ── Switch ───────────────────────────────────────────────────────────────
    MuiSwitch: {
      styleOverrides: {
        switchBase: {
          '&.Mui-checked': { color: '#ffffff' },
          '&.Mui-checked + .MuiSwitch-track': { backgroundColor: PALETTE.blue, opacity: 1 },
        },
        track: { borderRadius: 16, backgroundColor: PALETTE.border2, opacity: 1 },
        thumb: { boxShadow: '0 1px 2px rgba(0,0,0,0.3)' },
      },
    },

    // ── Table ────────────────────────────────────────────────────────────────
    MuiTableRow: {
      styleOverrides: {
        root: { transition: `background-color 0.12s ${EASE}`, '&:hover': { background: alpha(PALETTE.text1, 0.03) } },
        head: { '&:hover': { background: 'transparent' } },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        root: { borderColor: PALETTE.border1, fontSize: '0.84rem' },
        head: { fontWeight: 500, fontSize: '0.78rem', color: PALETTE.text3, letterSpacing: 0 },
      },
    },

    // ── Drawer ───────────────────────────────────────────────────────────────
    MuiDrawer: {
      styleOverrides: { paper: { background: PALETTE.bg1, borderRight: `1px solid ${PALETTE.border1}`, borderRadius: 0 } },
    },

    // ── BottomNavigation ─────────────────────────────────────────────────────
    MuiBottomNavigation: {
      styleOverrides: { root: { background: PALETTE.bg1, borderTop: `1px solid ${PALETTE.border1}` } },
    },
    MuiBottomNavigationAction: {
      styleOverrides: {
        root: { color: PALETTE.text3, '&.Mui-selected': { color: PALETTE.text1 } },
        label: { fontSize: '0.72rem', '&.Mui-selected': { fontSize: '0.72rem' } },
      },
    },

    // Validation message fades in instead of popping, and icon buttons give a small press response.
    MuiFormHelperText: {
      styleOverrides: { root: { '&.Mui-error': { animation: 'stateIn 0.18s ease-out' } } },
    },
    MuiIconButton: {
      styleOverrides: {
        root: {
          transition: `background-color 0.16s ${EASE}, transform 0.12s ${EASE}, color 0.16s ${EASE}`,
          '&:active:not(.Mui-disabled)': { transform: 'scale(0.94)' },
        },
      },
    },

    // ── Alert ────────────────────────────────────────────────────────────────
    MuiAlert: {
      styleOverrides: {
        root: { borderRadius: 10, border: '1px solid', fontSize: '0.84rem', animation: 'stateIn 0.2s ease-out' },
        standardInfo: { background: alpha(PALETTE.blue, 0.08), borderColor: alpha(PALETTE.blue, 0.24) },
        standardSuccess: { background: alpha(PALETTE.green, 0.08), borderColor: alpha(PALETTE.green, 0.24) },
        standardWarning: { background: alpha(PALETTE.amber, 0.08), borderColor: alpha(PALETTE.amber, 0.24) },
        standardError: { background: alpha(PALETTE.red, 0.08), borderColor: alpha(PALETTE.red, 0.24) },
      },
    },

    // ── Avatar ───────────────────────────────────────────────────────────────
    MuiAvatar: { styleOverrides: { colorDefault: { backgroundColor: PALETTE.bg4, color: PALETTE.text1 } } },

    // ── Stepper ──────────────────────────────────────────────────────────────
    MuiStepLabel: { styleOverrides: { label: { fontSize: '0.875rem' } } },
    MuiStepIcon: { styleOverrides: { root: { '&.Mui-active, &.Mui-completed': { color: PALETTE.blue } } } },
  },
});

export default telegizer;
