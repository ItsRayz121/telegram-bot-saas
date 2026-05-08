export const track = (event, properties = {}) => {
  if (window.posthog) window.posthog.capture(event, properties);
};

export const identify = (userId, traits = {}) => {
  if (window.posthog) window.posthog.identify(String(userId), traits);
};

export const reset = () => {
  if (window.posthog) window.posthog.reset();
};
