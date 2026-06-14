/**
 * API base — points at the coordinator.
 *
 * Uses the same host the page was loaded from, so:
 *   - open http://localhost:5173      → talks to localhost:8000
 *   - open http://10.0.50.69:5173     → talks to 10.0.50.69:8000
 * This lets the UI be opened from another PC (e.g. the worker) without edits.
 *
 * Override anytime with a Vite env var: VITE_API_URL=http://1.2.3.4:8000
 */
const HOST = (typeof window !== 'undefined' && window.location && window.location.hostname)
  ? window.location.hostname
  : 'localhost'

export const API = import.meta.env?.VITE_API_URL || `http://${HOST}:8000`
