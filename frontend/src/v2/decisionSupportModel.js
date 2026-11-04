const STATUS = new Set(['pending', 'approved', 'rejected'])
const PRIORITIES = new Set(['routine', 'low', 'info', 'warning', 'high', 'critical'])

const text = value => typeof value === 'string' && value.trim() ? value : null
const timestamp = value => ({ value: value ?? null, valid: typeof value === 'string' && Number.isFinite(Date.parse(value)) })

export function normalizeRecommendation(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const details = value.recommendation_details
  if (!details || typeof details !== 'object' || Array.isArray(details)) return null
  const status = text(value.status)
  return {
    id: text(value.recommendation_id),
    source: text(value.source),
    aircraftId: text(value.aircraft_id),
    missionId: text(value.mission_id),
    scenario: text(value.scenario),
    status,
    statusKnown: STATUS.has(status),
    details,
    title: text(details.title) || text(details.category) || text(details.failure_mode),
    action: text(details.recommended_action),
    severity: text(details.severity),
    severityKnown: PRIORITIES.has(text(details.severity)),
    reason: text(details.reason),
    evidence: details.evidence ?? null,
    provenance: details.provenance ?? null,
    createdAt: timestamp(value.created_at),
    decisionAt: timestamp(value.decision_at),
    operatorComment: value.operator_comment ?? null,
  }
}

export function normalizeRecommendationList(response) {
  if (!response || typeof response !== 'object' || !Array.isArray(response.recommendations)) return { valid: false, items: [] }
  return { valid: true, items: response.recommendations.map(normalizeRecommendation).filter(Boolean) }
}

export function normalizeDecisionHistory(response) {
  if (!response || typeof response !== 'object' || !Array.isArray(response.history)) return { valid: false, items: [] }
  return { valid: true, items: response.history.map(normalizeRecommendation).filter(Boolean) }
}

export function recommendationState({ status, hasData, error }) {
  if (error) return status === 'stale' ? 'STALE' : 'DECISION SUPPORT UNAVAILABLE'
  if (status === 'loading') return 'LOADING'
  if (!hasData) return 'NO PENDING RECOMMENDATIONS'
  return 'READY'
}

export function hasRecommendationId(recommendation) {
  return Boolean(recommendation?.id)
}
