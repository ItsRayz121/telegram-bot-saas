import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import TaskFlowPreview, { taskButtonLabel, taskPanelKind } from './TaskFlowPreview';

global.IS_REACT_ACT_ENVIRONMENT = true;

const X = { title: 'Follow the official Elyon Chain X account:', type: 'social_task', platform: 'x', task_url: 'https://x.com/ElyonChain',
  verification_mode: 'manual', reward_xp: 5, custom_fields: [{ field_type: 'username' }], settings: { auto_verify_x: true, raid_goals: { follows: 1 } } };
const JOIN = { title: 'Join the official Elyon Chain Telegram channel:', type: 'social_task', platform: 'telegram', task_url: 'https://t.me/elyon',
  verification_mode: 'auto', reward_xp: 5, custom_fields: [], settings: {} };
const WALLET = { title: 'Submit your wallet address for the airdrop distribution list', type: 'proof_collection', platform: '', task_url: '',
  verification_mode: 'manual', reward_xp: 0, custom_fields: [{ label: 'Wallet', field_type: 'wallet' }], settings: {} };

function render(ui) {
  const el = document.createElement('div');
  document.body.appendChild(el);
  const root = createRoot(el);
  act(() => { root.render(ui); });
  return { el, unmount: () => act(() => root.unmount()) };
}
const click = (el, text) => {
  const b = [...el.querySelectorAll('button')].find((x) => x.textContent.includes(text));
  if (!b) throw new Error(`no button "${text}"`);
  act(() => { b.dispatchEvent(new MouseEvent('click', { bubbles: true })); });
};

describe('task button labels (same rules as the backend)', () => {
  it('are short, have no XP, and honour a custom label', () => {
    expect(taskButtonLabel(X)).toBe('🐦 Follow on X');
    expect(taskButtonLabel(JOIN)).toBe('✈️ Join Telegram channel');
    expect(taskButtonLabel(JOIN, 'discord')).toBe('Join Telegram channel');
    expect(taskButtonLabel({ ...X, settings: { button_label: 'Go!' } })).toBe('Go!');
    expect(taskButtonLabel({ title: 'Whatever', type: 'raid', platform: 'x', settings: { raid_goals: { retweets: 5, likes: 5 } } })).toBe('🐦 X task');
    const long = taskButtonLabel(WALLET);
    expect(long.length).toBeLessThanOrEqual(28);
    expect(long).not.toMatch(/XP/);
  });
  it('decides which tasks are button-verified', () => {
    expect(taskPanelKind(X)).toBe('x');
    expect(taskPanelKind(X, { isPaid: false })).toBeNull();
    expect(taskPanelKind(X, { keyReady: false })).toBeNull();
    expect(taskPanelKind({ ...X, settings: { auto_verify_x: true } })).toBeNull();      // no target to check
    expect(taskPanelKind(JOIN)).toBe('join');
    expect(taskPanelKind(WALLET)).toBeNull();
  });
});

describe('TaskFlowPreview', () => {
  it('walks a member through picker -> panel -> verify, and updates live', () => {
    const { el, unmount } = render(<TaskFlowPreview tasks={[X, JOIN, WALLET]} title="One time tasks" />);
    expect(el.textContent).toContain('Choose a task to complete');
    expect(el.textContent).not.toContain('(+5 XP)');
    click(el, 'Follow on X');
    expect(el.textContent).toContain('Open on X');
    click(el, '✅ Verify');
    expect(el.textContent).toContain('Verified! +5 XP added');
    unmount();
  });

  it('shows the retry counter and the hand-off to the admins when nothing is found', () => {
    const { el, unmount } = render(<TaskFlowPreview tasks={[X]} />);
    click(el, '⏳ finds nothing yet');
    click(el, 'Follow on X');
    click(el, '✅ Verify');
    expect(el.textContent).toContain('Not detected yet (1/3)');
    click(el, '✅ Verify');
    click(el, '✅ Verify');
    expect(el.textContent).toContain('sent to the admins');
    unmount();
  });

  it('shows what happens when the bot cannot see a join chat, and the typed-proof flow', () => {
    const { el, unmount } = render(<TaskFlowPreview tasks={[JOIN, WALLET]} />);
    click(el, "🤖 bot can't see the chat");
    click(el, 'Join Telegram channel');
    click(el, '✅ Verify');
    expect(el.textContent).toContain("can't check this one automatically");
    click(el, 'Start over');
    click(el, WALLET.title.slice(0, 20));
    expect(el.textContent).toContain('typed or uploaded proof');
    unmount();
  });

  it('re-renders from the edited task list (real time)', () => {
    const el = document.createElement('div');
    document.body.appendChild(el);
    const root = createRoot(el);
    act(() => { root.render(<TaskFlowPreview tasks={[X]} />); });
    expect(el.textContent).toContain('Follow on X');
    act(() => { root.render(<TaskFlowPreview tasks={[{ ...X, settings: { ...X.settings, button_label: 'Follow us' } }]} />); });
    expect(el.textContent).toContain('Follow us');
    act(() => { root.render(<TaskFlowPreview tasks={[]} />); });
    expect(el.textContent).toContain('Add a task');
    act(() => root.unmount());
  });
});
