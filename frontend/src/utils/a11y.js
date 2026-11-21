// Props that make a non-button element (a Box/div with an onClick) behave like a button
// for keyboard and assistive-tech users: focusable, announced as a button, and
// activated by Enter or Space. Prefer a real <button>/<a> where the markup allows;
// use this only for existing click-only containers.
export function clickableProps(onClick, extra = {}) {
  return {
    role: 'button',
    tabIndex: 0,
    onClick,
    onKeyDown: (e) => {
      if (e.target !== e.currentTarget) return; // ignore keys from nested controls
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        onClick(e);
      }
    },
    ...extra,
  };
}
