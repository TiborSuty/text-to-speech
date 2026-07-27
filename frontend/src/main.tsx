// Imports StrictMode so React can surface development-only warnings.
import { StrictMode } from 'react';
// Imports React DOM's root creator for mounting the app into the page.
import { createRoot } from 'react-dom/client';

// Imports the top-level application component.
import App from './App';

// Finds the root DOM node and renders the React app into it.
createRoot(document.getElementById('root')!).render(
  // Wraps the app in StrictMode for extra development checks.
  <StrictMode>
    {/* Renders the text-to-speech application UI. */}
    <App />
  {/* Closes the StrictMode wrapper. */}
  </StrictMode>,
);
