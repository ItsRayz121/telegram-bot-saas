const setMatch = (matches) => { window.matchMedia = jest.fn().mockReturnValue({ matches }); };

describe('chart motion preference', () => {
  afterEach(() => { jest.resetModules(); });

  test('turns chart animation off when the OS asks for reduced motion', () => {
    setMatch(true);
    jest.isolateModules(() => {
      const { applyChartMotionPreference } = require('./rechartsMotion');
      const R = require('recharts');
      const applied = applyChartMotionPreference([R.Line, R.Area, R.Bar, R.Pie]);
      expect(applied).toBe(true);
      [R.Line, R.Area, R.Bar, R.Pie].forEach((C) => expect(C.defaultProps.isAnimationActive).toBe(false));
    });
  });

  test('leaves chart animation alone otherwise', () => {
    setMatch(false);
    const fake = { defaultProps: { isAnimationActive: true } };
    jest.isolateModules(() => {
      const { applyChartMotionPreference } = require('./rechartsMotion');
      expect(applyChartMotionPreference([fake])).toBe(false);
    });
    expect(fake.defaultProps.isAnimationActive).toBe(true);
  });

  test('re-exports the recharts components the app uses', () => {
    setMatch(false);
    const R = require('recharts');
    const m = require('./rechartsMotion');
    expect(m.Line).toBe(R.Line); expect(m.Area).toBe(R.Area); expect(m.Bar).toBe(R.Bar); expect(m.Pie).toBe(R.Pie);
    expect(m.ResponsiveContainer).toBe(R.ResponsiveContainer);
  });
});
