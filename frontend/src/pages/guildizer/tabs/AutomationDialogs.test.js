import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';

jest.mock('../../../services/guildizerApi', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn() },
}));
jest.mock('react-toastify', () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
// The collapsible card persists its open state through the API; render its children directly.
jest.mock('../../../components/guildizer/GuildizerCollapsibleCard', () => ({
  __esModule: true,
  default: ({ children }) => <div>{children}</div>,
}));

const guildizerApi = require('../../../services/guildizerApi').default;
const { toast } = require('react-toastify');
const { MirrorsCard, WebhooksCard } = require('./AutomationTab');

global.IS_REACT_ACT_ENVIRONMENT = true;

function render(ui) {
  const el = document.createElement('div');
  document.body.appendChild(el);
  const root = createRoot(el);
  act(() => { root.render(ui); });
  return { el, unmount: () => { act(() => root.unmount()); el.remove(); } };
}
const flush = () => act(async () => { await Promise.resolve(); await Promise.resolve(); });
const buttons = (root = document) => [...root.querySelectorAll('button')];
const byText = (text, root = document) => buttons(root).find((b) => b.textContent.trim() === text);
const click = (node) => act(() => { node.dispatchEvent(new MouseEvent('click', { bubbles: true })); });
const dialog = () => document.querySelector('[role="dialog"]');

const channels = [{ id: '1', name: 'general', type: 0 }, { id: '2', name: 'news', type: 0 }];

beforeEach(() => {
  jest.clearAllMocks();
  guildizerApi.put.mockResolvedValue({ data: {} });
});

describe('Webhook edit dialog', () => {
  const outbound = [{ id: 7, url: 'https://old.example/hook', enabled: true, events: [], delivered_count: 0 }];
  const mount = (onChanged = jest.fn()) => render(
    <WebhooksCard guildId={5} inbound={[]} outbound={outbound} channels={channels} onChanged={onChanged} />,
  );

  it('opens a dialog (no browser prompt), prefilled, and cancelling changes nothing', () => {
    window.prompt = jest.fn();
    const { unmount } = mount();
    click(byText('Edit'));
    expect(dialog()).not.toBeNull();
    expect(dialog().querySelector('input').value).toBe('https://old.example/hook');
    click(byText('Cancel', dialog()));
    expect(guildizerApi.put).not.toHaveBeenCalled();
    expect(window.prompt).not.toHaveBeenCalled();
    unmount();
  });

  it('saves the edited URL and refreshes the list', async () => {
    const onChanged = jest.fn();
    const { unmount } = mount(onChanged);
    click(byText('Edit'));
    const input = dialog().querySelector('input');
    const setValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    act(() => { setValue.call(input, 'https://new.example/hook'); input.dispatchEvent(new Event('input', { bubbles: true })); });
    click(byText('Save', dialog()));
    await flush();
    expect(guildizerApi.put).toHaveBeenCalledWith('/api/guilds/5/outbound-webhooks/7', { url: 'https://new.example/hook' });
    expect(toast.success).toHaveBeenCalled();
    expect(onChanged).toHaveBeenCalled();
    unmount();
  });

  it('refuses to enable Save for a non-http(s) address', () => {
    const { unmount } = mount();
    click(byText('Edit'));
    const input = dialog().querySelector('input');
    const setValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    act(() => { setValue.call(input, 'ftp://nope'); input.dispatchEvent(new Event('input', { bubbles: true })); });
    expect(byText('Save', dialog()).disabled).toBe(true);
    unmount();
  });

  it('shows a clear message when the server says the host is not public', async () => {
    guildizerApi.put.mockRejectedValueOnce({ response: { data: { error: 'url_not_public' } } });
    const { unmount } = mount();
    click(byText('Edit'));
    click(byText('Save', dialog()));
    await flush();
    expect(toast.error).toHaveBeenCalledWith('Webhook URLs must point to a public host.');
    expect(dialog()).not.toBeNull();            // stays open so nothing typed is lost
    unmount();
  });
});

describe('Mirror edit dialog', () => {
  const mirrors = [{ id: 3, source_channel_id: '1', dest_channel_id: '2', enabled: true, mirrored_count: 0 }];
  const mount = (onChanged = jest.fn()) => render(
    <MirrorsCard guildId={5} mirrors={mirrors} channels={channels} onChanged={onChanged} />,
  );

  it('opens with the current channels and saves them through the API', async () => {
    const onChanged = jest.fn();
    const { unmount } = mount(onChanged);
    click(byText('Edit'));
    expect(dialog()).not.toBeNull();
    click(byText('Save', dialog()));
    await flush();
    expect(guildizerApi.put).toHaveBeenCalledWith('/api/guilds/5/mirrors/3', { source_channel_id: '1', dest_channel_id: '2' });
    expect(onChanged).toHaveBeenCalled();
    unmount();
  });

  it('explains a server-side refusal instead of failing silently', async () => {
    guildizerApi.put.mockRejectedValueOnce({ response: { data: { error: 'source_not_in_server' } } });
    const { unmount } = mount();
    click(byText('Edit'));
    click(byText('Save', dialog()));
    await flush();
    expect(toast.error).toHaveBeenCalledWith('The source must be a channel of this server.');
    unmount();
  });
});
