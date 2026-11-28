import * as R from 'recharts';

const setMatch = (matches) => { window.matchMedia = vi.fn().mockReturnValue({ matches }); };
// A fresh copy of the module per test: it reads the motion preference when it is first evaluated.
const load = async () => { vi.resetModules(); return import('./rechartsMotion'); };

describe('chart motion preference', () => {
  test('turns chart animation off when the OS asks for reduced motion', async () => {
    setMatch(true);
    const { applyChartMotionPreference } = await load();
    const parts = [R.Line, R.Area, R.Bar, R.Pie];
    expect(applyChartMotionPreference(parts)).toBe(true);
    parts.forEach((C) => expect(C.defaultProps.isAnimationActive).toBe(false));
  });

  test('leaves chart animation alone otherwise', async () => {
    setMatch(false);
    const fake = { defaultProps: { isAnimationActive: true } };
    const { applyChartMotionPreference } = await load();
    expect(applyChartMotionPreference([fake])).toBe(false);
    expect(fake.defaultProps.isAnimationActive).toBe(true);
  });

  test('re-exports the recharts components the app uses', async () => {
    setMatch(false);
    vi.resetModules();
    const [Rf, m] = await Promise.all([import('recharts'), import('./rechartsMotion')]);
    expect(m.Line).toBe(Rf.Line); expect(m.Area).toBe(Rf.Area); expect(m.Bar).toBe(Rf.Bar); expect(m.Pie).toBe(Rf.Pie);
    expect(m.ResponsiveContainer).toBe(Rf.ResponsiveContainer);
  });
});
