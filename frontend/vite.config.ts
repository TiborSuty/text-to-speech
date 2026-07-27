// Imports the Vite plugin that enables React and TSX support.
import react from '@vitejs/plugin-react';
// Imports Vite's typed configuration helper.
import { defineConfig } from 'vite';

// Exports the Vite configuration used for development, tests, and builds.
export default defineConfig({
  // Enables React transformation and Fast Refresh support.
  plugins: [react()],
  // Configures the local development server.
  server: {
    // Proxies backend routes so the frontend can call FastAPI without CORS issues.
    proxy: {
      // Sends API requests to the local FastAPI server.
      '/api': 'http://127.0.0.1:8000',
      // Sends generated audio file requests to the local FastAPI server.
      '/audios': 'http://127.0.0.1:8000',
    },
  },
  // Configures Vitest for frontend unit and component tests.
  test: {
    // Uses a browser-like DOM environment for React Testing Library.
    environment: 'jsdom',
    // Exposes Vitest globals like describe, it, and expect.
    globals: true,
    // Loads shared test setup before running test files.
    setupFiles: './src/setupTests.ts',
  },
});
