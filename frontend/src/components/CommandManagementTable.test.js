import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import CommandManagementTable, { validSeconds } from './CommandManagementTable';

global.IS_REACT_ACT_ENVIRONMENT = true;

const rows = [
  { command: '/xp', scope: 'all_group', topic_ids: [], delete_command: true, delete_reply: true, seconds: 30, enabled: true },
  { command: '/rank', scope: 'specific_topics', topic_ids: [], delete_command: false, delete_reply: true, seconds: 45, enabled: true },
];
const limits = { min_seconds: 1, max_seconds: 86400, can_delete_command: true };
const mounted = [];

function render(ui) {
  const el = document.createElement('div');
  document.body.appendChild(el);
  const root = createRoot(el);
  act(() => { root.render(ui); });
  mounted.push([root, el]);
  return { el, rerender: (u) => act(() => { root.render(u); }) };
}
afterEach(() => { mounted.splice(0).forEach(([r, el]) => { act(() => r.unmount()); el.remove(); }); });

const q = (el, label) => el.querySelector(`[aria-label="${label}"]`);
// React tracks input values itself; set through the native setter so onChange fires.
function type(input, value) {
  const set = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
  act(() => { set.call(input, value); input.dispatchEvent(new Event('input', { bubbles: true })); });
}
const click = (node) => act(() => { node.click(); });

test('shows the approved columns and one independent row per command', () => {
  const { el } = render(<CommandManagementTable rows={rows} limits={limits} onChange={() => {}} onSave={() => {}} />);
  const heads = [...el.querySelectorAll('th')].map((h) => h.textContent.trim());
  expect(heads).toEqual(['Command', 'Who Can Access', 'Where', 'Delete Command', 'Delete Reply', 'Time (Seconds)', 'Status']);
  expect([...el.querySelectorAll('input[type=number]')].map((i) => i.value)).toEqual(['30', '45']);
});

test('editing one row reports only that command', () => {
  const onChange = jest.fn();
  const { el } = render(<CommandManagementTable rows={rows} limits={limits} onChange={onChange} onSave={() => {}} />);
  type(el.querySelectorAll('input[type=number]')[0], '10');
  expect(onChange).toHaveBeenLastCalledWith('/xp', { seconds: 10, _invalid: false });
  click(q(el, '/rank enabled'));
  expect(onChange).toHaveBeenLastCalledWith('/rank', { enabled: false });
  click(q(el, 'Delete /xp reply'));
  expect(onChange).toHaveBeenLastCalledWith('/xp', { delete_reply: false });
});

test('unsaved changes show a sticky save bar, an edited dot, and Discard', () => {
  const onSave = jest.fn();
  const onDiscard = jest.fn();
  const edited = [{ ...rows[0], _dirty: true }, rows[1]];
  const { el, rerender } = render(<CommandManagementTable rows={edited} limits={limits} dirty onChange={() => {}} onSave={onSave} onDiscard={onDiscard} />);
  expect(el.textContent).toContain('You have unsaved command changes');
  expect(el.querySelectorAll('[data-testid="row-dirty"]').length).toBe(1);
  click([...el.querySelectorAll('button')].find((b) => b.textContent.trim() === 'Save'));
  expect(onSave).toHaveBeenCalledTimes(1);
  click([...el.querySelectorAll('button')].find((b) => b.textContent.trim() === 'Discard'));
  expect(onDiscard).toHaveBeenCalledTimes(1);
  rerender(<CommandManagementTable rows={rows} limits={limits} dirty={false} onChange={() => {}} onSave={onSave} onDiscard={onDiscard} />);
  expect(el.textContent).not.toContain('unsaved command changes');
});

test('invalid seconds are flagged and block saving', () => {
  const onChange = jest.fn();
  const { el, rerender } = render(<CommandManagementTable rows={rows} limits={limits} onChange={onChange} onSave={() => {}} />);
  type(el.querySelectorAll('input[type=number]')[0], '0');
  expect(onChange).toHaveBeenLastCalledWith('/xp', { _invalid: true });
  rerender(<CommandManagementTable rows={rows} limits={limits} invalid onChange={onChange} onSave={() => {}} />);
  expect([...el.querySelectorAll('button')].find((b) => b.textContent.includes('Save commands')).disabled).toBe(true);
  expect(validSeconds('0', limits)).toBe(false);
  expect(validSeconds('1.5', limits)).toBe(false);
  expect(validSeconds('86400', limits)).toBe(true);
});

test('Discord mode: delete-command is disabled with an explanation, access is read-only', () => {
  const { el } = render(
    <CommandManagementTable
      rows={rows} accessMode="fixed" accessLabel={() => '2 channels'}
      limits={{ ...limits, can_delete_command: false, note: 'Discord cannot delete slash commands.' }}
      onChange={() => {}} onSave={() => {}}
    />,
  );
  expect(el.textContent).toContain('Discord cannot delete slash commands.');
  expect(q(el, 'Delete /xp message').disabled).toBe(true);
  expect(el.textContent.match(/2 channels/g)).toHaveLength(2);
});

test('selected-topics rows reveal the topic picker and a warning shows failed cleanups', () => {
  const { el } = render(<CommandManagementTable rows={rows} limits={limits} failures={3} topics={[{ thread_id: 7, name: 'Chat' }]} onChange={() => {}} onSave={() => {}} />);
  expect(el.textContent).toContain('Chat');
  expect(el.textContent).toContain('3 cleanups failed');
});

describe('Who Can Access roles', () => {
  const { nextRoles } = require('./CommandManagementTable');
  it('maps picks to a role restriction', () => {
    expect(nextRoles(['admins'])).toEqual(['admins']);
    expect(nextRoles(['everyone', 'admins'])).toEqual(['admins']);   // picking a role drops Everyone
    expect(nextRoles(['admins', 'everyone'])).toEqual([]);           // picking Everyone clears roles
    expect(nextRoles(['admins', 'members'])).toEqual([]);            // both = everyone
    expect(nextRoles([])).toEqual([]);
  });
});
