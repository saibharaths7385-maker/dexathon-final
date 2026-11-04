import { TWIN_API_BASE_URL } from '../api/config.js'

const BASE = TWIN_API_BASE_URL

class ApiRequestError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiRequestError'
    this.status = status
  }
}

export async function request(path, body, signal) {
  const response = await fetch(`${BASE}/api/v2${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: signal || AbortSignal.timeout(12000),
  })
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    const detail = Array.isArray(data.detail)
      ? data.detail.map((item) => item.msg).filter(Boolean).join(' ')
      : data.detail
    throw new ApiRequestError(
      typeof detail === 'string' && detail
        ? detail
        : `Request failed (${response.status}). Check your inputs and API connection.`,
      response.status,
    )
  }
  return response.json()
}
export function streamURL() {
  const url = new URL(`${BASE}/api/v2/stream`, window.location.origin)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  return url.toString()
}

export const recordCurrentRecommendation = () => request('/recommendations/current', {})
export const evaluateRecommendations = (signal) => request('/recommendations/evaluate', {}, signal)
export const getPendingRecommendations = (signal) => request('/recommendations/pending', undefined, signal)
export const getDecisionHistory = (signal) => request('/decisions/history', undefined, signal)
export const submitRecommendationDecision = (recommendationId, status, operatorComment) =>
  request(`/recommendations/${encodeURIComponent(recommendationId)}/decision`, {
    status,
    operator_comment: operatorComment,
  })

/** Submit an already-generated Phase 2–5 assessment bundle; raw telemetry is not accepted here. */
export const submitIntelligenceAssessment = (assessmentBundle) =>
  request('/recommendations/intelligence', assessmentBundle)

export const getTwinState = (signal) => request('/twin', undefined, signal)
export const getTwinHistory = (limit = 180, signal) => request(`/history?limit=${encodeURIComponent(limit)}`, undefined, signal)
export const getReplayState = (signal) => request('/replay', undefined, signal)
export const getTwinMissions = (limit = 24, signal) => request(`/missions?limit=${encodeURIComponent(limit)}`, undefined, signal)
export const getTwinFaultHistory = (limit = 180, signal) => request(`/fault-history?limit=${encodeURIComponent(limit)}`, undefined, signal)
