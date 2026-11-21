import { clickableProps } from './a11y';

describe('clickableProps', () => {
  const make = (fn) => clickableProps(fn);
  const evt = (key, same = true) => {
    const el = {};
    return { key, target: el, currentTarget: same ? el : {}, preventDefault: jest.fn() };
  };

  test('exposes button semantics and is focusable', () => {
    const p = make(() => {});
    expect(p.role).toBe('button');
    expect(p.tabIndex).toBe(0);
  });

  test('Enter and Space activate, other keys do not', () => {
    const fn = jest.fn();
    const p = make(fn);
    p.onKeyDown(evt('Enter'));
    p.onKeyDown(evt(' '));
    p.onKeyDown(evt('a'));
    expect(fn).toHaveBeenCalledTimes(2);
  });

  test('keys bubbling from a nested control are ignored', () => {
    const fn = jest.fn();
    make(fn).onKeyDown(evt('Enter', false));
    expect(fn).not.toHaveBeenCalled();
  });

  test('extra props are merged', () => {
    expect(clickableProps(() => {}, { 'aria-expanded': true })['aria-expanded']).toBe(true);
  });
});
