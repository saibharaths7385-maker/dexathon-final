export function AiStatus({ status, error }) {
  const labels = {
    loading: 'LOADING',
    ready: 'LIVE',
    stale: 'STALE',
    offline: 'DISCONNECTED',
  }
  return (
    <span className={`ai-status ai-status-${status || 'offline'}`} role="status">
      <i aria-hidden="true" />
      {labels[status] || 'UNAVAILABLE'}
      {error && <span className="ai-status-detail">{error}</span>}
    </span>
  )
}

export function ProvenanceLabel({ provenance = {}, className = '' }) {
  const synthetic = provenance.synthetic === true
  const label = synthetic ? 'SYNTHETIC DEMONSTRATION' : 'REAL-DATA PROVENANCE UNCONFIRMED'
  return <span className={`ai-provenance ${synthetic ? 'synthetic' : 'unconfirmed'} ${className}`}>{label}</span>
}

export function CalibrationLabel({ status, score }) {
  if (score != null && status !== 'NOT_CALIBRATED') return <span className="ai-calibration">CALIBRATED STATUS</span>
  return <span className="ai-calibration uncalibrated">NOT_CALIBRATED</span>
}
