import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import { MessagePreview } from './MessagePreviewImpl';
import { PreviewPanel } from './MessagePreview';
import { WELCOME_VARS } from './previewText';

global.IS_REACT_ACT_ENVIRONMENT = true;

function render(ui) {
  const el = document.createElement('div');
  document.body.appendChild(el);
  const root = createRoot(el);
  act(() => { root.render(ui); });
  return { el, unmount: () => act(() => root.unmount()) };
}

describe('MessagePreview', () => {
  it('is labelled, fills sample values, flags unknown placeholders and renders nothing clickable', () => {
    jest.useFakeTimers();
    const { el, unmount } = render(
      <MessagePreview platform="telegram" syntax="python" vars={WELCOME_VARS}
        text={'Hi {first_name} <img src=x onerror=alert(1)> {nickname} [go](https://evil.example)'}
        buttons={[[{ text: 'Claim reward' }]]} />,
    );
    act(() => { jest.advanceTimersByTime(400); });
    const text = el.textContent;
    expect(text).toContain('Preview — not sent');
    expect(text).toContain('Hi Alex');                      // sample value
    expect(text).toContain('{nickname}');                   // unresolved placeholder kept visible
    expect(text).toContain('Unknown placeholder');
    expect(text).toContain('<img src=x onerror=alert(1)>'); // untrusted markup stays literal text
    expect(el.querySelector('img')).toBeNull();
    expect(el.querySelector('a[href], [role="button"], input, textarea')).toBeNull(); // no links or fields
    // the only control is the harmless "show source text" toggle: preview buttons / mentions are not controls
    expect([...el.querySelectorAll('button')].map((b) => b.textContent)).toEqual(['Show source text']);
    expect(text).toContain('Claim reward');                 // the button is shown, but inert
    unmount();
    jest.useRealTimers();
  });

  it('warns when a message is longer than the platform allows', () => {
    jest.useFakeTimers();
    const { el, unmount } = render(<MessagePreview platform="discord" syntax="none" text={'x'.repeat(2100)} />);
    act(() => { jest.advanceTimersByTime(400); });
    expect(el.textContent).toContain('over Discord');
    unmount();
    jest.useRealTimers();
  });
});

describe('PreviewPanel', () => {
  it('mounts its content only while open', () => {
    const child = jest.fn(() => <span>inside</span>);
    const Child = () => child();
    const { el, unmount } = render(<PreviewPanel><Child /></PreviewPanel>);
    expect(child).not.toHaveBeenCalled();                    // closed: no work at all
    act(() => { el.querySelector('button').click(); });
    expect(child).toHaveBeenCalled();
    unmount();
  });
});
