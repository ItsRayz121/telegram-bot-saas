import React, { useState, useCallback } from 'react';
import { Joyride, ACTIONS, STATUS } from 'react-joyride';

export const TOUR_KEY = 'onboarding_tour_v1';

export function resetTour() {
  localStorage.removeItem(TOUR_KEY);
}

const STEPS = [
  {
    target: 'body',
    placement: 'center',
    title: 'Welcome to Telegizer!',
    content: "Let's take a quick tour of the key features. Click Next or press → to continue.",
    disableBeacon: true,
  },
  {
    target: '#tour-groups',
    placement: 'right',
    title: 'Groups',
    content: 'Connect your Telegram groups here. Add the bot as admin, run /linkgroup in the group, then paste the code.',
    disableBeacon: true,
  },
  {
    target: '#tour-echo',
    placement: 'right',
    title: 'Echo — Your AI Layer',
    content: 'Echo surfaces daily digests, captured notes, smart reminders, and follow-ups from your connected groups — automatically.',
    disableBeacon: true,
  },
  {
    target: '#tour-automation',
    placement: 'right',
    title: 'Automation',
    content: 'Build auto-reply rules, set up message forwarding, and create visual workflow automations.',
    disableBeacon: true,
  },
  {
    target: '#tour-settings',
    placement: 'right',
    title: 'Settings & Billing',
    content: 'Manage your profile, subscription plan, API keys, and team members from here.',
    disableBeacon: true,
  },
  {
    target: 'body',
    placement: 'center',
    title: "You're all set!",
    content: 'Start by linking your first Telegram group — click Groups in the sidebar to get started.',
    disableBeacon: true,
  },
];

export default function OnboardingTour() {
  const [run] = useState(() => {
    try {
      if (localStorage.getItem(TOUR_KEY)) return false;
      return !!localStorage.getItem('token');
    } catch {
      return false;
    }
  });

  const handleCallback = useCallback(({ action, status }) => {
    if (
      [STATUS.FINISHED, STATUS.SKIPPED].includes(status) ||
      action === ACTIONS.CLOSE
    ) {
      try { localStorage.setItem(TOUR_KEY, '1'); } catch {}
    }
  }, []);

  if (!run) return null;

  return (
    <Joyride
      steps={STEPS}
      run={run}
      continuous
      showProgress
      showSkipButton
      disableScrolling
      callback={handleCallback}
      floaterProps={{ disableAnimation: true }}
      styles={{
        options: {
          primaryColor: '#3d8ef8',
          backgroundColor: '#162035',
          textColor: '#e2e8f0',
          arrowColor: '#162035',
          overlayColor: 'rgba(0,0,0,0.55)',
          zIndex: 10000,
        },
        buttonNext: {
          backgroundColor: '#3d8ef8',
          color: '#fff',
          borderRadius: 8,
          padding: '8px 18px',
          fontWeight: 600,
          fontSize: '0.82rem',
          border: 'none',
        },
        buttonBack: {
          color: '#94a3b8',
          marginRight: 8,
          fontSize: '0.8rem',
          backgroundColor: 'transparent',
          border: 'none',
        },
        buttonSkip: {
          color: '#64748b',
          fontSize: '0.78rem',
          backgroundColor: 'transparent',
          border: 'none',
        },
        tooltip: {
          borderRadius: 12,
          padding: '18px 22px',
          maxWidth: 310,
          border: '1px solid rgba(61,142,248,0.25)',
          boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
        },
        tooltipTitle: {
          fontWeight: 700,
          fontSize: '0.95rem',
          color: '#f1f5f9',
          marginBottom: 6,
        },
        tooltipContent: {
          fontSize: '0.85rem',
          color: '#94a3b8',
          lineHeight: 1.6,
          padding: 0,
        },
        tooltipFooter: {
          marginTop: 14,
        },
        spotlight: {
          borderRadius: 8,
        },
      }}
      locale={{
        back: '← Back',
        close: 'Close',
        last: 'Done!',
        next: 'Next →',
        skip: 'Skip tour',
      }}
    />
  );
}
