import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import { settings } from '../services/api';
import ScheduledMessages from './ScheduledMessages';

jest.mock('react-toastify', () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
jest.mock('../services/api', () => ({
  settings: {
    getScheduledMessages: jest.fn(),
    createScheduledMessage: jest.fn(),
    updateScheduledMessage: jest.fn(),
    deleteScheduledMessage: jest.fn(),
  },
}));

global.IS_REACT_ACT_ENVIRONMENT = true;

const SAVED = { id: 7, title: 'Weekly rules', message_text: 'be nice', send_at: '2099-01-01T09:00:00Z', timezone: 'UTC', repeat_interval: 1440, is_sent: false };
const mounted = [];
const flush = () => act(async () => { await Promise.resolve(); await Promise.resolve(); });

async function mount() {
  const el = document.createElement('div');
  document.body.appendChild(el);
  const root = createRoot(el);
  await act(async () => { root.render(<ScheduledMessages botId={1} groupId={2} defaultTimezone="UTC" />); });
  await flush();
  mounted.push([root, el]);
}
afterEach(() => {
  mounted.splice(0).forEach(([r, el]) => { act(() => r.unmount()); el.remove(); });
  document.body.innerHTML = '';
  jest.clearAllMocks();
});

const byLabel = (l) => document.querySelector(`[aria-label="${l}"]`);
const buttonByText = (t) => [...document.querySelectorAll('button')].find((b) => b.textContent.trim() === t);
const click = (n) => act(() => { n.click(); });
function type(input, value) {
  const proto = input.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
  act(() => { Object.getOwnPropertyDescriptor(proto, 'value').set.call(input, value); input.dispatchEvent(new Event('input', { bubbles: true })); });
}
const field = (label) => {
  const lab = [...document.querySelectorAll('label')].find((l) => l.textContent.startsWith(label));
  return document.getElementById(lab.getAttribute('for'));
};

test('shows the repeat in plain words and the timezone in the table', async () => {
  settings.getScheduledMessages.mockResolvedValue({ data: [SAVED] });
  await mount();
  expect(document.body.textContent).toContain('Every day');
  expect(document.body.textContent).toContain('(UTC)');
});

test('delete asks first and does not call the API until confirmed', async () => {
  settings.getScheduledMessages.mockResolvedValue({ data: [SAVED] });
  settings.deleteScheduledMessage.mockResolvedValue({});
  await mount();
  click(byLabel('Delete scheduled message'));
  await flush();
  expect(document.body.textContent).toContain('Delete this scheduled message?');
  expect(document.body.textContent).toContain('future repeats');
  expect(settings.deleteScheduledMessage).not.toHaveBeenCalled();
  click(buttonByText('Delete'));
  await flush();
  expect(settings.deleteScheduledMessage).toHaveBeenCalledTimes(1);
  expect(settings.deleteScheduledMessage).toHaveBeenCalledWith(1, 2, 7);
});

test('keeping the schedule never calls the delete API', async () => {
  settings.getScheduledMessages.mockResolvedValue({ data: [SAVED] });
  await mount();
  click(byLabel('Delete scheduled message'));
  await flush();
  click(buttonByText('Keep it'));
  await flush();
  expect(settings.deleteScheduledMessage).not.toHaveBeenCalled();
});

test('a past time blocks scheduling and explains why', async () => {
  settings.getScheduledMessages.mockResolvedValue({ data: [] });
  await mount();
  click(buttonByText('Schedule message'));
  await flush();
  type(field('Send at'), '2000-01-01T09:00');
  await flush();
  expect(document.body.textContent).toContain('This time is in the past');
  expect(buttonByText('Schedule').disabled).toBe(true);
});

test('double-clicking Schedule creates the message once', async () => {
  settings.getScheduledMessages.mockResolvedValue({ data: [] });
  let resolveCreate;
  settings.createScheduledMessage.mockReturnValue(new Promise((r) => { resolveCreate = r; }));
  await mount();
  click(buttonByText('Schedule message'));
  await flush();
  type(field('Title'), 'Hello');
  type(field('Message text'), 'Body');
  type(field('Send at'), '2099-01-01T09:00');
  await flush();
  expect(document.body.textContent).toContain('Next send:');
  const btn = buttonByText('Schedule');
  click(btn);
  click(btn);
  await flush();
  expect(settings.createScheduledMessage).toHaveBeenCalledTimes(1);
  await act(async () => { resolveCreate({}); });
});
