import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import RaidAutoDialog from './RaidAutoDialog';

global.IS_REACT_ACT_ENVIRONMENT = true;

const payload = (over = {}) => ({
  automation: null, x_status: 'live', is_paid: true, can_edit: true,
  limits: { interval_hours: 12, max_per_day: 5, max_per_check: 2, manual_check_minutes: 60 }, ...over,
});

async function mount(ui) {
  const el = document.createElement('div');
  document.body.appendChild(el);
  const root = createRoot(el);
  await act(async () => { root.render(ui); });
  await act(async () => { await Promise.resolve(); });
  return { unmount: () => act(() => root.unmount()) };
}

const text = () => document.body.textContent;
const byLabel = (label) => [...document.body.querySelectorAll('label')].find((l) => l.textContent.startsWith(label));
const setInput = (input, value) => {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
  act(() => { setter.call(input, value); input.dispatchEvent(new Event('input', { bubbles: true })); });
};
const button = (label) => [...document.body.querySelectorAll('button')].find((b) => b.textContent.trim() === label);

describe('RaidAutoDialog', () => {
  it('sends fixed targets and random ranges in the shape the backend expects', async () => {
    const api = { get: jest.fn().mockResolvedValue({ data: payload() }), save: jest.fn().mockResolvedValue({ data: payload() }),
      remove: jest.fn(), check: jest.fn() };
    const { unmount } = await mount(<RaidAutoDialog open onClose={() => {}} api={api} />);
    expect(text()).toContain('Continuous raids');
    expect(text()).toContain('Start raids automatically');
    const handle = document.body.querySelector('input[placeholder="@YourProject"]');
    setInput(handle, '@Elyon');
    await act(async () => { button('Save').dispatchEvent(new MouseEvent('click', { bubbles: true })); });
    expect(api.save).toHaveBeenCalledTimes(1);
    const body = api.save.mock.calls[0][0];
    expect(body.x_handle).toBe('@Elyon');
    expect(body.template.goals.likes).toEqual({ min: 10, max: 20 });          // a random range per raid
    expect(body.template.goals.retweets).toEqual({ min: 5, max: 10 });
    expect(body.template.goals.comments).toBeUndefined();                      // empty row = skipped
    expect(body.template.duration_hours).toBe(24);
    unmount();
  });

  it('is locked with an upgrade note on a free plan, and warns when no X key works', async () => {
    const api = { get: jest.fn().mockResolvedValue({ data: payload({ is_paid: false, x_status: 'disabled' }) }), save: jest.fn(), remove: jest.fn(), check: jest.fn() };
    const { unmount } = await mount(<RaidAutoDialog open onClose={() => {}} api={api} />);
    expect(text()).toContain('need a Pro or Enterprise plan');
    expect(button('Save').disabled).toBe(true);
    unmount();
    const api2 = { get: jest.fn().mockResolvedValue({ data: payload({ x_status: 'disabled' }) }), save: jest.fn(), remove: jest.fn(), check: jest.fn() };
    const m2 = await mount(<RaidAutoDialog open onClose={() => {}} api={api2} />);
    expect(text()).toContain('No working Twitter API key');
    m2.unmount();
  });
});
