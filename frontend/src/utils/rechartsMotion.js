// Recharts animates with JavaScript, so the global `prefers-reduced-motion` CSS rule does not stop it.
// Import charts from here instead of 'recharts': same exports, but chart animation is switched off for
// users whose OS asks for reduced motion. Checked once at load (a changed OS setting applies on reload).
import { Line, Area, Bar, Pie } from 'recharts';

export * from 'recharts';

export function prefersReducedMotion() {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

export function applyChartMotionPreference(components = [Line, Area, Bar, Pie]) {
  if (!prefersReducedMotion()) return false;
  components.forEach((C) => { if (C && C.defaultProps) C.defaultProps.isAnimationActive = false; });
  return true;
}

applyChartMotionPreference();
