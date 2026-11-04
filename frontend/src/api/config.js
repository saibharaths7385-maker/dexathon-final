// Centralized build-time API configuration. The separate twin fallback preserves
// the existing local Digital Twin development workflow.
export const API_BASE_URL = (import.meta.env?.VITE_API_BASE_URL || 'https://sih26054-phm-v2.onrender.com').replace(/\/$/, '')
export const TWIN_API_BASE_URL = (
  import.meta.env?.VITE_TWIN_API_BASE_URL
  || import.meta.env?.VITE_API_BASE_URL
  || 'http://127.0.0.1:8000'
).replace(/\/$/, '')
