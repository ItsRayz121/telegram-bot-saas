import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import InviteRewardField, { clampInviteXp, MAX_INVITE_XP } from './InviteRewardField';

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

function type(input, value) {
  const set = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
  act(() => { set.call(input, value); input.dispatchEvent(new Event('input', { bubbles: true })); });
}

describe('clampInviteXp', () => {
  test('whole numbers pass through, limited to 0..1000', () => {
    expect(clampInviteXp('25')).toBe(25);
    expect(clampInviteXp('1000')).toBe(1000);
    expect(clampInviteXp('99999')).toBe(MAX_INVITE_XP);
    expect(clampInviteXp('-5')).toBe(0);
    expect(clampInviteXp('12.9')).toBe(12);
  });
  test('blank and junk mean off (0), never NaN', () => {
    ['', 'abc', null, undefined, NaN].forEach((v) => expect(clampInviteXp(v)).toBe(0));
  });
});

describe('InviteRewardField', () => {
  test('shows the saved amount, 0 when none is set', () => {
    expect(render(<InviteRewardField value={40} onChange={() => {}} />).querySelector('input').value).toBe('40');
    expect(render(<InviteRewardField onChange={() => {}} />).querySelector('input').value).toBe('0');
  });

  test('typing reports a clamped number, and the label explains the rules', () => {
    const onChange = vi.fn();
    const el = render(<InviteRewardField value={0} onChange={onChange} />);
    const input = el.querySelector('input');
    type(input, '30');
    expect(onChange).toHaveBeenLastCalledWith(30);
    type(input, '5000');
    expect(onChange).toHaveBeenLastCalledWith(1000);
    expect(el.textContent).toContain('/myinvite');
    expect(el.textContent).toContain('0 turns it off');
  });
});
