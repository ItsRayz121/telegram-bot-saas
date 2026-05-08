import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App';
import posthog from 'posthog-js';

posthog.init(process.env.REACT_APP_POSTHOG_KEY || 'phc_placeholder', {
  api_host: process.env.REACT_APP_POSTHOG_HOST || 'https://app.posthog.com',
  loaded: (ph) => {
    if (process.env.NODE_ENV === 'development') ph.opt_out_capturing();
  },
});

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
