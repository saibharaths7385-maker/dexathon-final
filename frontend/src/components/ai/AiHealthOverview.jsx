import { Activity, Battery, Clock3, Gauge, Radio, Thermometer, WalletCards, Zap } from 'lucide-react'
import {
  SCENARIO_LABELS,
  assessmentSummary,
  connectionLabel,
  measurementState,
} from './healthOverviewModel'
import { CalibrationLabel, ProvenanceLabel } from './AiStatus'

const formatValue = (value, digits = 1) => typeof value === 'number' && Number.isFinite(value)
  ? value.toLocaleString('en-US', { maximumFractionDigits: digits })
  : value

function DataValue({ value, unit = '', digits = 1 }) {
  const reading = measurementState(value)
  return <><b className={`ai-overview-value-${reading.state.toLowerCase()}`}>{formatValue(reading.value, digits)}</b>{reading.state === 'VALID' && unit && <small>{unit}</small>}</>
}

function TelemetryCard({ icon: Icon, label, value, unit, note, digits, tone = '' }) {
  const reading = measurementState(value)
  return <article className={`ai-overview-telemetry ${tone}`}>
    <div className="ai-overview-card-head"><span>{label}</span><Icon size={16}/></div>
    <div className="ai-overview-reading"><DataValue value={value} unit={unit} digits={digits}/></div>
    <div className="ai-overview-card-foot"><span>{reading.state === 'VALID' ? note : `${reading.state} SENSOR VALUE`}</span></div>
  </article>
}

export default function AiHealthOverview({ data, connection }) {
  if (!data) return <section className="ai-overview ai-overview-loading"><Radio size={18}/><span>ASSESSMENT NOT AVAILABLE · ESTABLISHING TELEMETRY LINK</span></section>

  const assessment = assessmentSummary()
  const quality = data.quality || {}
  const status = connectionLabel(connection, quality.status)
  const provenance = data.source === 'simulation'
    ? { synthetic: true, source: data.source }
    : data.source ? { synthetic: false, source: data.source } : {}
  const scenario = SCENARIO_LABELS[data.controls?.scenario] || data.controls?.scenario || 'UNAVAILABLE'
  const missing = ['engine temperature', 'voltage', 'current', 'fuel level']
  const mission = data.controls?.mission || {}

  return <section className="ai-overview" aria-label="AI health overview">
    <div className="ai-overview-heading">
      <div>
        <span className="v-eyebrow">PHASE 7 · AI HEALTH CENTRE</span>
        <h2>AI health overview</h2>
        <p>Evidence status for the connected Digital Twin. No calibrated Phase 2–5 assessment is currently retrievable.</p>
      </div>
      <div className={`ai-overview-connection ${status.toLowerCase()}`}><i/><b>{status}</b><span>{quality.age_seconds == null ? 'FRESHNESS UNAVAILABLE' : `${formatValue(quality.age_seconds, 1)} s SINCE SAMPLE`}</span></div>
    </div>

    <div className="ai-overview-identity">
      <div><span>AIRCRAFT ID</span><b>{data.engine_id || 'UNAVAILABLE'}</b></div>
      <div><span>MISSION ID</span><b>{mission.mission_id || 'UNAVAILABLE'}</b></div>
      <div><span>ACTIVE SCENARIO</span><b>{scenario}</b></div>
      <div><span>LAST TELEMETRY UPDATE</span><b>{data.timestamp ? new Date(data.timestamp).toLocaleString('en-GB', { timeZone: 'UTC' }) : 'UNAVAILABLE'}</b></div>
      <div><span>DATA SOURCE</span><b><ProvenanceLabel provenance={provenance}/></b></div>
    </div>

    <div className="ai-overview-grid">
      <div className="ai-overview-panel">
        <div className="ai-overview-panel-title"><div><span className="v-eyebrow">OBSERVED CHANNELS</span><h3>Engine telemetry summary</h3></div><Badge text={quality.status === 'live' ? 'VALIDATED FRAME' : 'LAST KNOWN FRAME'}/></div>
        <div className="ai-overview-telemetry-grid">
          <TelemetryCard icon={Gauge} label="RPM" value={data.sensors?.rpm} unit="rpm" note="Engine speed" digits={0} tone="cyan"/>
          <TelemetryCard icon={Thermometer} label="ENGINE TEMPERATURE" value={undefined} note="Not supplied by current schema" tone="amber"/>
          <TelemetryCard icon={Battery} label="VOLTAGE" value={undefined} note="Not supplied by current schema" tone="purple"/>
          <TelemetryCard icon={Zap} label="CURRENT" value={undefined} note="Not supplied by current schema" tone="purple"/>
          <TelemetryCard icon={WalletCards} label="FUEL LEVEL" value={undefined} note="Not supplied by current schema" tone="amber"/>
        </div>
        <p className="ai-overview-note"><Thermometer size={14}/> EGT, CHT and oil temperature remain separately named engine channels in the Digital Twin; none is relabelled as generic engine temperature.</p>
      </div>

      <div className="ai-overview-panel ai-overview-assessment">
        <div className="ai-overview-panel-title"><div><span className="v-eyebrow">PHASE 2–5 EVIDENCE</span><h3>AI health assessment</h3></div><CalibrationLabel status={assessment.calibration} score={assessment.score}/></div>
        <div className="ai-overview-unavailable"><Activity size={21}/><strong>{assessment.status}</strong><p>No GET endpoint currently exposes persisted engineering, trend, or health assessments. This overview does not fabricate a status or score.</p></div>
        <div className="ai-overview-assessment-list"><span>WARNING FINDINGS <b>UNAVAILABLE</b></span><span>CRITICAL FINDINGS <b>UNAVAILABLE</b></span><span>TREND RISK <b>UNAVAILABLE</b></span><span>ASSESSMENT COVERAGE <b>UNAVAILABLE</b></span></div>
      </div>
    </div>

    <div className="ai-overview-footer">
      <div><span>DATA QUALITY</span><b>{quality.samples == null ? 'UNAVAILABLE' : `${quality.samples} samples · ${quality.status?.toUpperCase() || 'UNKNOWN'}`}</b></div>
      <div><span>NOT PROVIDED BY CURRENT FRAME</span><b>{missing.join(' · ')}</b></div>
      <div><span>SCENARIO CONTEXT</span><b>{SCENARIO_LABELS[data.controls?.scenario] ? scenario : 'Current Digital Twin scenario; environmental context not supplied'}</b></div>
    </div>
  </section>
}

function Badge({ text }) {
  return <span className="ai-overview-badge"><Clock3 size={12}/>{text}</span>
}
