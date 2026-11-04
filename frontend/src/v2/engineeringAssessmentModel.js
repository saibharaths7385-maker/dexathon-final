const STATUS_KEYS = new Set(['NORMAL', 'WARNING', 'CRITICAL', 'NOT_ASSESSED'])

export function readingState(value) {
  if (value === undefined) return { state: 'MISSING', value: null }
  if (value === null) return { state: 'MISSING', value: null }
  if (typeof value !== 'number' || !Number.isFinite(value)) return { state: 'INVALID', value: null }
  return { state: 'VALID', value }
}

function timestampInfo(value) {
  if (value == null) return { value: null, valid: false }
  const parsed = Date.parse(value)
  return { value, valid: typeof value === 'string' && Number.isFinite(parsed) }
}

function normalizeFinding(finding) {
  if (!finding || typeof finding !== 'object' || Array.isArray(finding)) return null
  const statusValue = typeof finding.status === 'string' ? finding.status : null
  const statusKey = statusValue?.toUpperCase()
  const observed = Object.prototype.hasOwnProperty.call(finding, 'observed_value')
    ? finding.observed_value
    : Object.prototype.hasOwnProperty.call(finding, 'measurement')
      ? finding.measurement
      : finding.value
  return {
    parameter: finding.parameter ?? finding.parameter_name ?? null,
    status: statusValue,
    statusKey: STATUS_KEYS.has(statusKey) ? statusKey : null,
    observed: readingState(observed),
    unit: finding.unit ?? null,
    limit: finding.limit ?? finding.threshold ?? finding.configured_limit ?? null,
    referenceRange: finding.reference_range ?? null,
    ruleId: finding.rule_id ?? null,
    explanation: finding.explanation ?? null,
    evidence: finding.evidence ?? null,
    timestamp: timestampInfo(finding.timestamp),
    quality: finding.quality ?? finding.data_quality ?? null,
    provenance: finding.provenance ?? null,
  }
}

function summaryFromFindings(findings) {
  const summary = { totalAssessed: 0, normal: 0, warning: 0, critical: 0, notAssessed: 0 }
  for (const finding of findings) {
    if (finding.statusKey === 'NORMAL') summary.normal += 1
    if (finding.statusKey === 'WARNING') summary.warning += 1
    if (finding.statusKey === 'CRITICAL') summary.critical += 1
    if (finding.statusKey === 'NOT_ASSESSED') summary.notAssessed += 1
  }
  summary.totalAssessed = summary.normal + summary.warning + summary.critical
  return summary
}

export function normalizeAssessmentResponse(response) {
  if (response == null) return { available: false, state: 'MISSING', findings: [], summary: summaryFromFindings([]) }
  if (typeof response !== 'object' || Array.isArray(response)) {
    return { available: false, state: 'MALFORMED', findings: [], summary: summaryFromFindings([]) }
  }
  const rawFindings = response.findings
  if (rawFindings !== undefined && !Array.isArray(rawFindings)) {
    return { available: false, state: 'MALFORMED', findings: [], summary: summaryFromFindings([]) }
  }
  const findings = (rawFindings || []).map(normalizeFinding).filter(Boolean)
  const hasContent = Object.keys(response).length > 0
  return {
    available: hasContent,
    state: hasContent ? 'AVAILABLE' : 'EMPTY',
    findings,
    summary: response.summary && typeof response.summary === 'object'
      ? { ...summaryFromFindings(findings), supplied: response.summary }
      : summaryFromFindings(findings),
    quality: response.data_quality ?? response.quality ?? null,
    provenance: response.provenance ?? response.raw_telemetry ?? null,
    source: response.source ?? response.source_id ?? null,
    aircraftId: response.aircraft_id ?? response.engine_id ?? null,
    missionId: response.mission_id ?? response.mission?.mission_id ?? null,
    scenario: response.scenario ?? response.scenario_id ?? null,
    timestamp: timestampInfo(response.timestamp),
  }
}

export function assessmentState({ assessment, connection }) {
  if (connection === 'offline') return 'DISCONNECTED'
  if (connection === 'reconnecting' || connection === 'connecting') return 'CONNECTING'
  if (assessment?.available === false && assessment.state === 'MISSING') return 'ASSESSMENT NOT AVAILABLE'
  if (assessment?.available === false && assessment.state === 'MALFORMED') return 'ASSESSMENT NOT AVAILABLE'
  if (assessment?.available === false && assessment.state === 'EMPTY') return 'INSUFFICIENT DATA'
  if (assessment?.available) return 'ASSESSMENT AVAILABLE'
  return 'ASSESSMENT NOT AVAILABLE'
}

export function provenanceLabel(provenance) {
  if (!provenance || typeof provenance !== 'object') return 'PROVENANCE UNKNOWN'
  if (provenance.synthetic === true) return 'SYNTHETIC / DEMO DATA'
  const label = provenance.source ?? provenance.identifier
  return label ? String(label) : 'PROVENANCE UNKNOWN'
}
