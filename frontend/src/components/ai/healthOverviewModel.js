export const SCENARIO_LABELS = {
  urban: 'Urban',
  volcanic: 'Volcanic',
  desert: 'Desert',
  forest: 'Forest',
  snow_mountain: 'Snow Mountain',
}

export function connectionLabel(connection, qualityStatus) {
  if (qualityStatus === 'stale') return 'STALE'
  if (connection === 'streaming' || connection === 'polling') return 'LIVE'
  if (connection === 'offline') return 'DISCONNECTED'
  return 'CONNECTING'
}

export function measurementState(value) {
  if (value == null) return { value: 'UNAVAILABLE', state: 'MISSING' }
  if (typeof value !== 'number' || !Number.isFinite(value)) return { value: 'INVALID', state: 'INVALID' }
  return { value, state: 'VALID' }
}

export function assessmentSummary() {
  return {
    status: 'ASSESSMENT NOT AVAILABLE',
    score: null,
    calibration: 'NOT_CALIBRATED',
    warningCount: null,
    criticalCount: null,
    trendRisk: null,
    coverage: null,
  }
}

export function provenanceLabel(provenance = {}) {
  return provenance.synthetic === true ? 'SYNTHETIC DEMONSTRATION' : 'UNCONFIRMED'
}
