import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';

/**
 * Application Entry Point
 *
 * Mounts the React app to the DOM.
 * StrictMode enables additional development warnings.
 */
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
