/**
 * Feature Registry — clone-sync tests
 *
 * Guarantees that custom bots automatically inherit all non-officialOnly
 * features from the registry, and that new entries added to FEATURE_TABS
 * appear for both bot types without any manual wiring.
 */

import {
  FEATURE_TABS,
  PLAN_GATES,
  PRO_GATED_SECTIONS,
  PRO_GATED_LABELS,
  ENTERPRISE_GATED_SECTIONS,
  buildCategories,
  getSubTabIndex,
} from './featureRegistry';

// ── Structural integrity ───────────────────────────────────────────────────────

test('every FEATURE_TABS entry has required fields', () => {
  for (const tab of FEATURE_TABS) {
    expect(tab).toHaveProperty('id');
    expect(tab).toHaveProperty('label');
    expect(tab).toHaveProperty('icon');
    expect(Array.isArray(tab.subTabs)).toBe(true);
    for (const sub of tab.subTabs) {
      expect(sub).toHaveProperty('label');
      expect(typeof sub.officialOnly).toBe('boolean');
    }
  }
});

test('all tab ids are unique', () => {
  const ids = FEATURE_TABS.map((t) => t.id);
  expect(new Set(ids).size).toBe(ids.length);
});

// ── buildCategories — custom bot (isOfficial = false) ─────────────────────────

test('custom bot includes all non-officialOnly tabs', () => {
  const cats = buildCategories(false);
  // Every tab from the registry must be present (tabs themselves are never officialOnly)
  expect(cats.map((c) => c.id)).toEqual(FEATURE_TABS.map((t) => t.id));
});

test('custom bot excludes officialOnly subtabs', () => {
  const officialOnlyLabels = FEATURE_TABS.flatMap((t) =>
    t.subTabs.filter((s) => s.officialOnly).map((s) => s.label)
  );
  const cats = buildCategories(false);
  const allCustomSubTabs = cats.flatMap((c) => c.subTabs);
  for (const label of officialOnlyLabels) {
    expect(allCustomSubTabs).not.toContain(label);
  }
});

test('custom bot includes all non-officialOnly subtabs', () => {
  const publicLabels = FEATURE_TABS.flatMap((t) =>
    t.subTabs.filter((s) => !s.officialOnly).map((s) => s.label)
  );
  const cats = buildCategories(false);
  const allCustomSubTabs = cats.flatMap((c) => c.subTabs);
  for (const label of publicLabels) {
    expect(allCustomSubTabs).toContain(label);
  }
});

// ── buildCategories — official bot (isOfficial = true) ────────────────────────

test('official bot includes all subtabs including officialOnly', () => {
  const allLabels = FEATURE_TABS.flatMap((t) => t.subTabs.map((s) => s.label));
  const cats = buildCategories(true);
  const allOfficialSubTabs = cats.flatMap((c) => c.subTabs);
  for (const label of allLabels) {
    expect(allOfficialSubTabs).toContain(label);
  }
});

// ── Auto-inheritance: adding a new module propagates automatically ─────────────

test('a new non-officialOnly subtab added to registry appears for custom bots', () => {
  // Simulate adding a new subtab to the analytics tab
  const originalSubTabs = FEATURE_TABS.find((t) => t.id === 'analytics').subTabs;
  const newSubTab = { label: 'Future Analytics Feature', officialOnly: false };
  originalSubTabs.push(newSubTab);

  try {
    const cats = buildCategories(false);
    const analyticsCat = cats.find((c) => c.id === 'analytics');
    expect(analyticsCat.subTabs).toContain('Future Analytics Feature');
  } finally {
    // Restore original state
    originalSubTabs.pop();
  }
});

test('a new officialOnly subtab does NOT appear for custom bots', () => {
  const originalSubTabs = FEATURE_TABS.find((t) => t.id === 'analytics').subTabs;
  const newSubTab = { label: 'Official-Exclusive Feature', officialOnly: true };
  originalSubTabs.push(newSubTab);

  try {
    const customCats = buildCategories(false);
    const officialCats = buildCategories(true);

    const customAnalytics = customCats.find((c) => c.id === 'analytics');
    const officialAnalytics = officialCats.find((c) => c.id === 'analytics');

    expect(customAnalytics.subTabs).not.toContain('Official-Exclusive Feature');
    expect(officialAnalytics.subTabs).toContain('Official-Exclusive Feature');
  } finally {
    originalSubTabs.pop();
  }
});

test('a new tab added to registry appears for both official and custom bots', () => {
  const newTab = {
    id: 'future_module',
    label: 'Future Module',
    icon: null,
    subTabs: [
      { label: 'Overview', officialOnly: false },
      { label: 'Advanced', officialOnly: true },
    ],
  };
  FEATURE_TABS.push(newTab);

  try {
    const customCats = buildCategories(false);
    const officialCats = buildCategories(true);

    const customIds = customCats.map((c) => c.id);
    const officialIds = officialCats.map((c) => c.id);

    expect(customIds).toContain('future_module');
    expect(officialIds).toContain('future_module');

    const customFuture = customCats.find((c) => c.id === 'future_module');
    const officialFuture = officialCats.find((c) => c.id === 'future_module');

    expect(customFuture.subTabs).toEqual(['Overview']); // officialOnly 'Advanced' excluded
    expect(officialFuture.subTabs).toEqual(['Overview', 'Advanced']);
  } finally {
    FEATURE_TABS.pop();
  }
});

// ── getSubTabIndex ─────────────────────────────────────────────────────────────

test('getSubTabIndex returns correct index for existing subtab', () => {
  const cats = buildCategories(true);
  expect(getSubTabIndex(cats, 'analytics', 'Members')).toBe(0);
  expect(getSubTabIndex(cats, 'analytics', 'Leaderboard')).toBe(1);
  expect(getSubTabIndex(cats, 'analytics', 'Audit Log')).toBe(2);
  expect(getSubTabIndex(cats, 'analytics', 'Warnings')).toBe(3);
  expect(getSubTabIndex(cats, 'analytics', 'Digest')).toBe(4);
});

test('getSubTabIndex returns -1 for officialOnly subtab in custom-bot context', () => {
  const cats = buildCategories(false);
  expect(getSubTabIndex(cats, 'analytics', 'Leaderboard')).toBe(-1);
  expect(getSubTabIndex(cats, 'analytics', 'Warnings')).toBe(-1);
});

test('getSubTabIndex returns correct indices for custom bot analytics', () => {
  const cats = buildCategories(false);
  // custom: ['Members', 'Audit Log', 'Digest']
  expect(getSubTabIndex(cats, 'analytics', 'Members')).toBe(0);
  expect(getSubTabIndex(cats, 'analytics', 'Audit Log')).toBe(1);
  expect(getSubTabIndex(cats, 'analytics', 'Digest')).toBe(2);
});

test('getSubTabIndex returns -1 for unknown tab id', () => {
  const cats = buildCategories(false);
  expect(getSubTabIndex(cats, 'nonexistent', 'Members')).toBe(-1);
});

// ── Plan-gating registry ───────────────────────────────────────────────────────

test('PRO_GATED_SECTIONS matches PLAN_GATES.pro keys', () => {
  expect(PRO_GATED_SECTIONS).toEqual(new Set(Object.keys(PLAN_GATES.pro)));
});

test('PRO_GATED_LABELS matches PLAN_GATES.pro values', () => {
  expect(PRO_GATED_LABELS).toEqual(PLAN_GATES.pro);
});

test('ENTERPRISE_GATED_SECTIONS matches PLAN_GATES.enterprise keys', () => {
  expect(ENTERPRISE_GATED_SECTIONS).toEqual(new Set(Object.keys(PLAN_GATES.enterprise)));
});

test('pro and enterprise gated keys do not overlap', () => {
  const proKeys = new Set(Object.keys(PLAN_GATES.pro));
  const entKeys = new Set(Object.keys(PLAN_GATES.enterprise));
  const intersection = [...proKeys].filter((k) => entKeys.has(k));
  expect(intersection).toHaveLength(0);
});
