import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import CompactSubmissionsTable, { firstUrl } from './CompactSubmissionsTable';

global.IS_REACT_ACT_ENVIRONMENT = true;

const mounted = [];
function render(ui) {
  const el = document.createElement('div');
  document.body.appendChild(el);
  const root = createRoot(el);
  act(() => { root.render(ui); });
  mounted.push([root, el]);
  return el;
}
afterEach(() => { while (mounted.length) { const [r, e] = mounted.pop(); act(() => r.unmount()); e.remove(); } });

const mk = (i, o = {}) => ({
  id: i, userName: `@user${i}`, userId: 1000 + i, taskTitle: i % 2 ? 'Follow on X' : 'Quote post',
  proofUrl: `https://x.com/u${i}/status/${i}`, proofText: '', proofExtra: 0,
  status: 'pending', xp: null, createdAt: `2026-11-0${(i % 8) + 1}T10:00:00Z`,
  reviewedBy: 1, reviewedAt: '2026-11-08T10:00:00Z', notifyStatus: 'sent', raw: {}, ...o,
});
const click = (n) => act(() => { n.dispatchEvent(new MouseEvent('click', { bubbles: true })); });
const noop = () => {};

test('two-line user, status+XP on one line, no "by 1"/"user notified" in row', () => {
  const el = render(<CompactSubmissionsTable rows={[mk(1, { status: 'verified', xp: 40 })]} showTask onApprove={noop} onReject={noop} />);
  expect(el.textContent).toContain('@user1');
  expect(el.textContent).toContain('ID: 1001');
  expect(el.textContent).toContain('Verified');
  expect(el.textContent).toContain('+40 XP');
  expect(el.textContent).not.toMatch(/by 1/);
  expect(el.textContent).not.toMatch(/user notified/i);
});

test('proof link keeps full href; clicking it does not expand the row', () => {
  const el = render(<CompactSubmissionsTable rows={[mk(2)]} showTask renderDetail={() => <div>DETAIL</div>} onApprove={noop} onReject={noop} />);
  const a = el.querySelector('a');
  expect(a.getAttribute('href')).toBe('https://x.com/u2/status/2');
  click(a);
  expect(el.textContent).not.toContain('DETAIL');
  click([...el.querySelectorAll('p,span')].find((n) => n.textContent === '@user2'));
  expect(el.textContent).toContain('DETAIL');
});

test('paginates at 50 by default', () => {
  const rows = Array.from({ length: 60 }, (_, i) => mk(i + 1));
  const el = render(<CompactSubmissionsTable rows={rows} showTask onApprove={noop} onReject={noop} />);
  expect(el.querySelectorAll('a')).toHaveLength(50);
  expect(el.textContent).toContain('60 submissions');
});

test('approve needs confirmation; reject delegates to parent', () => {
  const onApprove = jest.fn(); const onReject = jest.fn();
  const el = render(<CompactSubmissionsTable rows={[mk(3)]} showTask onApprove={onApprove} onReject={onReject} />);
  click(el.querySelector('button[aria-label="Approve"], span[aria-label="Approve"] button') || el.querySelectorAll('td button')[0]);
  expect(onApprove).not.toHaveBeenCalled();
  const confirmBtn = [...document.querySelectorAll('[role="dialog"] button')].find((b) => b.textContent === 'Approve');
  click(confirmBtn);
  expect(onApprove).toHaveBeenCalledTimes(1);
  click(el.querySelectorAll('td button')[1]);
  expect(onReject).toHaveBeenCalledTimes(1);
});

test('firstUrl extracts links', () => {
  expect(firstUrl('see https://a.co/x now')).toBe('https://a.co/x');
  expect(firstUrl('nothing', undefined)).toBe('');
});
