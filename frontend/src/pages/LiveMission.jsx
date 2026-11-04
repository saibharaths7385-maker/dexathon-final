import {
  Activity,
  AlertTriangle,
  Battery,
  CheckCircle2,
  Check,
  Clock3,
  Compass,
  Crosshair,
  Fuel,
  Gauge,
  MapPin,
  MessageSquare,
  Navigation,
  Radio,
  RefreshCw,
  ShieldCheck,
  Thermometer,
  Wind,
  X,
  Zap,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import {
  getDecisionHistory,
  getPendingRecommendations,
  evaluateRecommendations,
  request,
  submitRecommendationDecision,
} from '../v2/api'
import { useTwin } from '../v2/useTwin'
import ScenarioReplay from '../components/ScenarioReplay'
import { evaluationMatchesSource } from '../lib/replay'
import './live-mission.css'

const engineChannels = [
  { key: 'rpm', label: 'RPM', unit: 'rpm', digits: 0 },
  { key: 'egt', label: 'EGT', unit: '°C', digits: 1 },
  { key: 'cht', label: 'CHT', unit: '°C', digits: 1 },
  { key: 'oil_temperature', label: 'OIL TEMPERATURE', unit: '°C', digits: 1 },
  { key: 'oil_pressure', label: 'OIL PRESSURE', unit: 'bar', digits: 2 },
  { key: 'fuel_flow', label: 'FUEL FLOW', unit: 'L/h', digits: 2 },
  { key: 'vibration', label: 'VIBRATION', unit: 'mm/s RMS', digits: 2 },
]

function flattenValues(value, prefix = '') {
  if (!value || typeof value !== 'object') return []
  return Object.entries(value).flatMap(([key, child]) => {
    const path = prefix ? `${prefix}.${key}` : key
    return child && typeof child === 'object'
      ? flattenValues(child, path)
      : [{ key: key.toLowerCase().replace(/[^a-z0-9]/g, ''), path, value: child }]
  })
}

function findSourceValue(source, aliases) {
  const keys = new Set(aliases.map((key) => key.toLowerCase().replace(/[^a-z0-9]/g, '')))
  return flattenValues(source).find(({ key }) => keys.has(key))
}

function readMetric(source, key) {
  const value = source && Object.prototype.hasOwnProperty.call(source, key)
    ? source[key]
    : undefined
  const available = value !== undefined && value !== null && value !== ''
    && (typeof value !== 'number' || Number.isFinite(value))
  return available ? { key, path: key, value } : undefined
}

function readFrameMetric(frame, section, key, fallbackKey) {
  const values = frame?.[section]
  const sample = readMetric(values, key) || (fallbackKey ? readMetric(values, fallbackKey) : undefined)
  if (!sample) return undefined
  const sourcePath = frame?.normalization?.fields?.[`${section}.${key}`]
  return { ...sample, path: sourcePath || `${section}.${sample.path}` }
}

function formatValue(value, digits = 1) {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return new Intl.NumberFormat(undefined, {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    }).format(value)
  }
  if (typeof value === 'string' || typeof value === 'boolean') return String(value)
  return 'N/A'
}

function formatTimestamp(value) {
  if (typeof value !== 'string' || !value) return 'N/A'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

function MetricCard({ label, value, unit, icon: Icon, source, progress, compact = false, digits }) {
  const hasValue = value !== undefined && value !== null && value !== ''
  const numeric = typeof value === 'number' && Number.isFinite(value)
  const barWidth = numeric && Number.isFinite(progress) ? `${Math.max(0, Math.min(100, progress))}%` : null
  const precision = digits ?? (compact ? 1 : 2)

  return (
    <article className={`lm-metric-card ${compact ? 'compact' : ''} ${hasValue ? 'has-value' : 'unavailable'}`}>
      <div className="lm-metric-top">
        <span>{label}</span>
        {Icon && <Icon size={16} aria-hidden="true" />}
      </div>
      <strong key={`${label}-${value}`}>
        {hasValue ? formatValue(value, precision) : 'N/A'}{unit && <small> {unit}</small>}
      </strong>
      {barWidth !== null && (
        <div className="lm-meter" aria-label={`${label} ${formatValue(value)} percent`}>
          <span style={{ width: barWidth }} />
        </div>
      )}
      <em>{source || (hasValue ? 'LIVE SAMPLE' : 'UNAVAILABLE')}</em>
    </article>
  )
}

function SectionHeader({ eyebrow, title, detail }) {
  return (
    <div className="lm-section-header">
      <div>
        <span className="lm-eyebrow">{eyebrow}</span>
        <h3>{title}</h3>
      </div>
      {detail && <span className="lm-section-detail">{detail}</span>}
    </div>
  )
}

function DisabledControls() {
  return (
    <section className="lm-panel" aria-label="Mission controls">
      <SectionHeader
        eyebrow="SIMULATOR ONLY · COMMAND LINK NOT VERIFIED"
        title="Mission controls"
        detail="Controls are disabled until Laptop 1 exposes a confirmed simulator-only command interface."
      />
      <div className="lm-controls-grid">
        <div className="lm-command-buttons">
          {['Start', 'Pause', 'Resume', 'Reset', 'Abort'].map((command) => (
            <button type="button" disabled key={command}>{command}</button>
          ))}
        </div>
        <label className="lm-control-field">
          <span>Throttle adjustment</span>
          <input type="range" min="0" max="100" value="0" disabled readOnly aria-label="Throttle adjustment unavailable" />
          <small>Unavailable</small>
        </label>
        <label className="lm-control-field">
          <span>Scenario selection</span>
          <select disabled defaultValue=""><option value="">Unavailable</option></select>
        </label>
        <label className="lm-control-field">
          <span>Simulated fault injection</span>
          <select disabled defaultValue=""><option value="">Unavailable</option></select>
        </label>
      </div>
      <p className="lm-control-note">
        No controls on this page call SKYNEX twin controls. Virtual-simulator commands require a verified Laptop 1 protocol.
      </p>
    </section>
  )
}

function SimulatorViewport({ status, frame, offline = false, replayState }) {
  const hasPosition = Boolean(
    readMetric(frame?.flight, 'latitude') && readMetric(frame?.flight, 'longitude')
  )
  const hasFlightData = flattenValues(frame?.flight).length > 0

  return (
    <section className="lm-viewport" aria-label="Simulator integration viewport">
      <div className="lm-viewport-grid" aria-hidden="true" />
      <div className="lm-viewport-topline">
        <span><Crosshair size={14} /> SIMULATOR VIEWPORT</span>
        <span className={`lm-disconnected ${status}`}>
          <i /> {offline ? `OFFLINE REPLAY ${replayState?.toUpperCase()}` : `LAPTOP 1 ${status.toUpperCase()}`}
        </span>
      </div>
      <div className="lm-viewport-message">
        <div className="lm-viewport-icon"><Radio size={25} /></div>
        <span className="lm-eyebrow">EAGLE EYE MINI INTEGRATION</span>
        <h3>Simulator view unavailable</h3>
        <p>
          Telemetry is received separately from the simulator video/3D view. This panel remains an honest placeholder
          and does not render a fabricated aircraft.
        </p>
      </div>
      <div className="lm-viewport-footer">
        <span><MapPin size={13} /> POSITION {hasPosition ? 'DATA RECEIVED' : 'UNAVAILABLE'}</span>
        <span><Wind size={13} /> {hasFlightData ? 'FLIGHT DATA RECEIVED' : 'FLIGHT DATA UNAVAILABLE'}</span>
      </div>
    </section>
  )
}

function LiveEngineHealth({ frame, offline = false }) {
  const rpmKind = frame?.normalization?.rpm_kind
  const temperatureKind = frame?.normalization?.temperature_kind
  const propulsionKind = rpmKind || temperatureKind
  const channels = [
    { key: 'rpm', label: rpmKind === 'motor' ? 'Motor RPM' : rpmKind === 'engine' ? 'Engine RPM' : 'RPM', unit: 'rpm', icon: Gauge, digits: 0 },
    { key: 'temperature_c', fallbackKey: 'engine_temp_c', label: temperatureKind === 'motor' ? 'Motor temperature' : temperatureKind === 'engine' ? 'Engine temperature' : 'Propulsion temperature', unit: '°C', icon: Thermometer, digits: 1 },
    { key: 'battery_voltage', label: 'Battery voltage', unit: 'V', icon: Battery },
    { key: 'current_a', label: 'Current', unit: 'A', icon: Zap },
    { key: 'fuel_percent', label: 'Fuel level', unit: '%', icon: Fuel, progress: true, digits: 0 },
  ]

  return (
    <section className="lm-panel" aria-label={offline ? 'Replay propulsion telemetry' : 'Laptop 1 propulsion telemetry'}>
      <SectionHeader eyebrow="SIMULATED DEMO DATA · PROPULSION" title={propulsionKind === 'motor' ? 'Motor health' : propulsionKind === 'engine' ? 'Engine health' : 'Propulsion health'} />
      <div className="lm-metric-grid lm-engine-health-grid">
        {channels.map(({ key, fallbackKey, label, unit, icon, progress, digits }) => {
          const sample = readFrameMetric(frame, 'propulsion', key, fallbackKey)
          return (
            <MetricCard
              key={label}
              label={label}
              unit={unit}
              icon={icon}
              value={sample?.value}
              source={sample ? `SOURCE · ${sample.path}` : `FIELD · propulsion.${key}`}
              progress={progress && typeof sample?.value === 'number' ? sample.value : null}
              digits={digits}
            />
          )
        })}
      </div>
      <p className="lm-muted">
        Values are shown only when supplied in the Protocol 1 propulsion frame. Motor and engine channels remain distinct; temperature is never treated as EGT or CHT.
      </p>
    </section>
  )
}

function HeadingIndicator({ value }) {
  const heading = typeof value === 'number' && Number.isFinite(value) ? value : null
  return (
    <div className={`lm-heading-indicator ${heading === null ? 'no-heading' : ''}`}
      aria-label={heading === null ? 'Heading N/A' : `Heading ${formatValue(heading)} degrees`}>
      <span>N</span><span>E</span><span>S</span><span>W</span>
      <div className="lm-compass-needle" style={{ transform: `rotate(${heading ?? 0}deg)` }}>
        <i />
      </div>
      <strong>{heading === null ? 'N/A' : formatValue(heading, 1)}<small>°</small></strong>
    </div>
  )
}

function FlightTelemetry({ frame }) {
  const flight = frame?.flight
  const values = [
    { key: 'altitude_m', label: 'Altitude', unit: 'm', icon: Navigation },
    { key: 'airspeed_mps', label: 'Airspeed', unit: 'm/s', icon: Activity },
    { key: 'pitch_deg', label: 'Pitch', unit: '°', icon: Crosshair },
    { key: 'roll_deg', label: 'Roll', unit: '°', icon: Crosshair },
    { key: 'latitude', label: 'Latitude', unit: '°', icon: MapPin },
    { key: 'longitude', label: 'Longitude', unit: '°', icon: MapPin },
  ]
  const heading = readFrameMetric(frame, 'flight', 'heading_deg')

  return (
    <section className="lm-panel" aria-label="Flight telemetry">
      <SectionHeader eyebrow="SIMULATED DEMO DATA · FLIGHT" title="Flight telemetry" />
      <div className="lm-flight-layout">
        <div className="lm-metric-grid lm-flight-grid">
          {values.map(({ key, label, unit, icon }) => {
            const sample = readFrameMetric(frame, 'flight', key)
            return (
              <MetricCard
                compact
                key={label}
                label={label}
                unit={unit}
                icon={icon}
                value={sample?.value}
                source={sample ? `SOURCE · ${sample.path}` : `FIELD · flight.${key}`}
              />
            )
          })}
        </div>
        <div className="lm-heading-card">
          <span><Compass size={15} /> HEADING</span>
          <HeadingIndicator value={heading?.value} />
          <small>{heading?.path || 'Heading unavailable'}</small>
        </div>
      </div>
    </section>
  )
}

function EnvironmentMonitoring({ frame }) {
  const channels = [
    { key: 'temperature_c', label: 'Ambient temperature', unit: '°C', icon: Thermometer },
    { key: 'humidity_percent', label: 'Humidity', unit: '%', icon: Activity },
    { key: 'wind_speed_mps', label: 'Wind speed', unit: 'm/s', icon: Wind },
    { key: 'wind_direction_deg', label: 'Wind direction', unit: '°', icon: Compass },
    { key: 'turbulence', label: 'Turbulence', unit: '', icon: Activity },
    { key: 'visibility_m', label: 'Visibility', unit: 'm', icon: Crosshair },
    { key: 'dust_level', label: 'Dust', unit: '', icon: Activity },
    { key: 'ash_level', label: 'Ash', unit: '', icon: Activity },
  ]

  return (
    <section className="lm-panel" aria-label="Environment monitoring">
      <SectionHeader eyebrow="SIMULATED DEMO DATA · ENVIRONMENT" title="Environment monitoring" />
      <div className="lm-metric-grid lm-environment-grid">
        {channels.map(({ key, label, unit, icon }) => {
          const sample = readFrameMetric(frame, 'environment', key)
          return (
            <MetricCard
              compact
              key={label}
              label={label}
              unit={unit}
              icon={icon}
              value={sample?.value}
              source={sample ? `SOURCE · ${sample.path}` : `FIELD · environment.${key}`}
            />
          )
        })}
      </div>
    </section>
  )
}

function FaultCentre({ frame, status, offline = false }) {
  const faults = frame?.faults
  const available = Array.isArray(faults) || (faults && typeof faults === 'object')
  const entries = Array.isArray(faults) ? faults : faults && typeof faults === 'object' ? Object.values(faults) : []

  return (
    <section className="lm-panel" aria-label="Fault and alert centre">
      <SectionHeader
        eyebrow={offline ? 'OFFLINE REPLAY / SYNTHETIC DATA · PROTOCOL 1' : 'SIMULATED DEMO DATA · LAPTOP 1 PROTOCOL 1'}
        title="Fault & alert centre"
        detail={frame?.timestamp ? `Frame time · ${formatTimestamp(frame.timestamp)}` : 'Frame time · N/A'}
      />
      {status !== 'connected' ? (
        <p className="lm-muted">Current fault status unavailable: telemetry is {status}. Retained frame data is historical.</p>
      ) : !available ? (
        <p className="lm-muted">Fault status unavailable in the latest frame.</p>
      ) : entries.length === 0 ? (
        <div className="lm-system-normal"><CheckCircle2 size={20} /><div><b>NO SOURCE-REPORTED FAULTS</b><span>No faults reported in the latest frame; aircraft condition is not verified.</span></div></div>
      ) : (
        <div className="lm-fault-list">
          {entries.map((fault, index) => {
            const item = typeof fault === 'string' ? { description: fault } : fault || {}
            const code = findSourceValue(item, ['code', 'fault_code', 'id'])
            const description = typeof fault === 'string'
              ? { value: fault }
              : findSourceValue(item, ['description', 'message', 'name', 'fault'])
            const severity = findSourceValue(item, ['severity', 'priority', 'level'])
            const timestamp = typeof item.timestamp === 'string' ? item.timestamp : frame?.timestamp
            const source = offline ? 'Offline replay · synthetic fixture' : typeof item.source === 'string' && item.source
              ? item.source
              : 'Laptop 1 · Protocol 1'
            const severityName = typeof severity?.value === 'string' ? severity.value.toLowerCase() : ''
            const tone = ['critical', 'high', 'medium', 'low', 'warning', 'info'].includes(severityName)
              ? severityName
              : 'unknown'
            return (
              <article className={`lm-fault-card ${tone}`} key={`${code?.value || 'fault'}-${index}`}>
                <AlertTriangle size={18} />
                <div>
                  <b>{code?.value || 'Fault code unavailable'}</b>
                  <p>{description?.value || 'Description unavailable'}</p>
                  <small className="lm-fault-meta">
                    {source} · {formatTimestamp(timestamp)}
                  </small>
                </div>
                <span>{severity?.value || 'Severity unavailable'}</span>
              </article>
            )
          })}
        </div>
      )}
    </section>
  )
}

function MissionProgress({ mission }) {
  const sample = readMetric(mission, 'progress')
  const progress = sample?.value
  const percent = typeof progress === 'number' && Number.isFinite(progress)
    ? (progress >= 0 && progress <= 1 ? progress * 100 : progress >= 0 && progress <= 100 ? progress : null)
    : null

  return (
    <div className="lm-mission-progress">
      <div><span>MISSION PROGRESS</span><b>{percent === null ? 'Unavailable' : `${formatValue(percent, 0)}%`}</b></div>
      <div className="lm-progress-track" role={percent === null ? undefined : 'progressbar'}
        aria-valuemin={percent === null ? undefined : 0} aria-valuemax={percent === null ? undefined : 100}
        aria-valuenow={percent === null ? undefined : percent}>
        {percent !== null && <span style={{ width: `${percent}%` }} />}
      </div>
      {sample && <small>SOURCE · {sample.path}</small>}
    </div>
  )
}

function MissionStatus({ frame, status, lastReceivedAt, twinScenario, offline = false }) {
  const mission = frame?.mission
  const waypoint = readFrameMetric(frame, 'mission', 'current_waypoint')
  const waypointTotal = readFrameMetric(frame, 'mission', 'total_waypoints')
  const elapsed = readFrameMetric(frame, 'mission', 'elapsed_seconds')
  const missionState = readFrameMetric(frame, 'mission', 'state')

  return (
    <section className="lm-panel lm-mission-status" aria-label="Mission status">
      <SectionHeader eyebrow={offline ? 'OFFLINE REPLAY / SYNTHETIC DATA' : 'SIMULATED DEMO DATA · LAPTOP 1'} title="Mission status" />
      <dl className="lm-status-list">
        <div><dt>Aircraft identity</dt><dd>{frame?.aircraft_id || 'N/A'}</dd></div>
        <div><dt>Mission ID</dt><dd>{frame?.mission_id || 'N/A'}</dd></div>
        <div><dt>Scenario</dt><dd>{frame?.scenario || 'N/A'}</dd></div>
        <div><dt>Flight phase</dt><dd>{frame?.phase || 'N/A'}</dd></div>
        <div><dt>Mission state</dt><dd>{missionState?.value ?? 'N/A'}</dd></div>
        <div><dt>Current waypoint</dt><dd>{waypoint ? formatValue(waypoint.value, 0) : 'N/A'}{waypointTotal ? ` / ${formatValue(waypointTotal.value, 0)}` : ''}</dd></div>
        <div><dt>Mission elapsed</dt><dd>{elapsed ? `${formatValue(elapsed.value)} s` : 'N/A'}</dd></div>
        <div><dt>{offline ? 'Replay input quality' : 'Simulator connection'}</dt><dd className={`lm-connection-state ${status}`}>{offline && status === 'connected' ? 'fresh on replay clock' : status}</dd></div>
        <div><dt>Frame timestamp</dt><dd>{formatTimestamp(frame?.timestamp)}</dd></div>
        <div><dt>Last received</dt><dd>{formatTimestamp(lastReceivedAt)}</dd></div>
      </dl>
      <MissionProgress mission={mission} />
      {twinScenario && (
        <p className="lm-twin-scenario">
          SKYNEX twin scenario: <b>{twinScenario.replaceAll('_', ' ')}</b> · not the Laptop 1 mission scenario
        </p>
      )}
    </section>
  )
}

function Evidence({ items }) {
  return <div className="lm-evidence"><b>Supporting evidence</b><div>
    {(items || []).map((item) => <span key={item.key}>
      {item.label || item.key}: {item.value !== null && typeof item.value === 'object' ? JSON.stringify(item.value) : formatValue(item.value, 2)}{item.unit ? ` ${item.unit}` : ''}
      {item.expected !== undefined && <small> · expected {formatValue(item.expected, 2)} {item.unit}</small>}
      {item.normal_min !== undefined && <small> · demo envelope {item.normal_min}–{item.normal_max} {item.unit}</small>}
      {item.status && <small> · {item.status}</small>}
    </span>)}
  </div></div>
}

function ReviewCard({ recommendation, busy, busyStatus, onDecision, unavailable = false }) {
  const [comment, setComment] = useState('')
  const [commentError, setCommentError] = useState('')
  const details = recommendation.current_details || recommendation.recommendation_details
  const severity = String(details.severity || 'unknown').toLowerCase()

  async function submit(status) {
    const operatorComment = comment.trim()
    if (!operatorComment) {
      setCommentError('Enter an operator comment before approving or rejecting.')
      return
    }
    setCommentError('')
    const result = await onDecision(recommendation.recommendation_id, status, operatorComment)
    if (result) setComment('')
  }

  return (
    <article className="lm-review-card">
      <div className="lm-review-top">
        <div>
          <span className="lm-review-source">{recommendation.source.replaceAll('_', ' ')}</span>
          <h4>{details.failure_mode}</h4>
        </div>
        <span className={`lm-severity ${severity}`}>{severity}</span>
      </div>
      <p className="lm-review-recommendation">{details.recommended_action}</p>
      <p className="lm-review-reason">{details.reason}</p>
      <dl className="lm-review-meta">
        <div><dt>Decision</dt><dd>{details.decision}</dd></div>
        <div><dt>Aircraft</dt><dd>{recommendation.aircraft_id}</dd></div>
        <div><dt>Mission</dt><dd>{recommendation.mission_id}</dd></div>
        <div><dt>Scenario</dt><dd>{recommendation.scenario}</dd></div>
        {details.replay_session_id && <>
          <div><dt>Replay session</dt><dd>{details.replay_session_id}</dd></div>
          <div><dt>Replay scenario</dt><dd>{details.replay_scenario}</dd></div>
          <div><dt>Data provenance</dt><dd>OFFLINE REPLAY / SYNTHETIC DATA</dd></div>
        </>}
        {details.phase && <div><dt>Phase</dt><dd>{details.phase}</dd></div>}
        <div><dt>Approval status</dt><dd className={`lm-decision-status ${recommendation.status}`}>{recommendation.status}</dd></div>
        <div><dt>Created</dt><dd>{new Date(recommendation.created_at).toLocaleString()}</dd></div>
        {details.sample_timestamp && <div><dt>Evidence time</dt><dd>{formatTimestamp(details.sample_timestamp)}</dd></div>}
      </dl>
      {details.rule_id && <p className="lm-muted">Rule {details.rule_id} · {details.ruleset_version}<br />{details.rule_basis}</p>}
      {details.limitation && <p className="lm-review-integrity">{details.limitation}</p>}
      {details.identity_basis && <p className="lm-muted">{details.identity_basis}</p>}
      {details.provenance && <p className="lm-muted">{details.provenance}</p>}
      <Evidence items={details.evidence} />
      {recommendation.current_details && <details className="lm-recorded-evidence">
        <summary>Original recorded evidence · {formatTimestamp(recommendation.created_at)}</summary>
        <p className="lm-muted">Operator decisions refer to this original record. Current evidence above does not amend a prior decision.</p>
        <Evidence items={recommendation.recommendation_details.evidence} />
      </details>}
      {recommendation.status !== 'pending' ? <p className="lm-review-confirmation">
        {recommendation.status} · {formatTimestamp(recommendation.decision_at)} · {recommendation.operator_comment}
      </p> : <>
      <label className="lm-review-comment">
        <span><MessageSquare size={13} /> Operator comment <em>required</em></span>
        <textarea
          value={comment}
          onChange={(event) => {
            setComment(event.target.value)
            if (event.target.value.trim()) setCommentError('')
          }}
          required
          minLength={1}
          maxLength={2000}
          rows={3}
          placeholder="Record the reason for your decision…"
          disabled={busy || unavailable}
          aria-invalid={Boolean(commentError)}
          aria-describedby={commentError ? `comment-error-${recommendation.recommendation_id}` : undefined}
        />
      </label>
      {commentError && (
        <p
          className="lm-review-comment-error"
          id={`comment-error-${recommendation.recommendation_id}`}
          role="alert"
        >
          {commentError}
        </p>
      )}
      <div className="lm-review-actions">
        <button type="button" className="lm-approve" disabled={busy || unavailable} onClick={() => submit('approved')}>
          <Check size={15} /> {busyStatus === 'approved' ? 'Submitting approval…' : 'Approve recommendation'}
        </button>
        <button type="button" className="lm-reject" disabled={busy || unavailable} onClick={() => submit('rejected')}>
          <X size={15} /> {busyStatus === 'rejected' ? 'Submitting rejection…' : 'Reject recommendation'}
        </button>
      </div>
      </>}
    </article>
  )
}

function RecommendationReviewCentre({ sourceMode, replaySessionId, sourceUnavailable }) {
  const [current, setCurrent] = useState([])
  const [pending, setPending] = useState([])
  const [history, setHistory] = useState([])
  const [busyId, setBusyId] = useState('')
  const [busyStatus, setBusyStatus] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const refreshSequence = useRef(0)
  const refreshing = useRef(false)
  const lastEvaluated = useRef(0)

  async function refreshReview(signal) {
    if (refreshing.current) return
    refreshing.current = true
    const sequence = ++refreshSequence.current
    try {
      const requestSignal = signal ? AbortSignal.any([signal, AbortSignal.timeout(12000)]) : AbortSignal.timeout(12000)
      const evaluation = await evaluateRecommendations(requestSignal)
      if (!evaluationMatchesSource(evaluation, sourceMode, replaySessionId)) {
        throw new Error('Evaluation source/session changed. Waiting for the selected source.')
      }
      const [pendingResult, historyResult] = await Promise.all([
        getPendingRecommendations(requestSignal),
        getDecisionHistory(requestSignal),
      ])
      if (sequence !== refreshSequence.current) return
      setCurrent(evaluation.recommendations)
      setPending(pendingResult.recommendations)
      setHistory(historyResult.history)
      lastEvaluated.current = Date.now()
      setError('')
    } catch (requestError) {
      if (sequence === refreshSequence.current && requestError.name !== 'AbortError') {
        setError(requestError.message || 'Unable to load operator decision records.')
      }
    } finally {
      refreshing.current = false
      if (sequence === refreshSequence.current) setLoading(false)
    }
  }

  useEffect(() => {
    const abort = new AbortController()
    refreshReview(abort.signal)
    const interval = setInterval(() => refreshReview(abort.signal), 2000)
    const watchdog = setInterval(() => {
      if (lastEvaluated.current && Date.now() - lastEvaluated.current > 5000) {
        setError('No successful decision evaluation within the 5 s display freshness window.')
      }
    }, 1000)
    return () => {
      abort.abort()
      clearInterval(interval)
      clearInterval(watchdog)
    }
  }, [])

  async function decide(recommendationId, status, operatorComment) {
    setBusyId(recommendationId)
    setBusyStatus(status)
    setError('')
    setConfirmation('')
    try {
      const result = await submitRecommendationDecision(recommendationId, status, operatorComment)
      if (
        result?.recommendation_id !== recommendationId
        || result.status !== status
        || !result.decision_at
      ) {
        throw new Error('The server did not confirm this recommendation decision.')
      }
      setCurrent((records) => records.map((record) => record.recommendation_id === recommendationId ? { ...record, ...result } : record))
      await refreshReview()
      setConfirmation(`Recommendation ${status} and recorded at ${new Date(result.decision_at).toLocaleString()}.`)
      return result
    } catch (requestError) {
      const message = requestError.message || 'Unable to record this decision.'
      if (requestError.status === 409) {
        await refreshReview()
      }
      setError(message)
      return null
    } finally {
      setBusyId('')
      setBusyStatus('')
    }
  }

  return (
    <section className="lm-panel lm-review-centre" aria-label="Recommendation Review Centre">
      <SectionHeader
        eyebrow="SCENARIO DECISION SUPPORT · DETERMINISTIC RULES"
        title="Recommendation Review Centre"
        detail="Approval records an operator decision only; no simulator or aircraft command is sent."
      />
      <div className="lm-review-integrity">
        Recommendations identify their source and scenario. V2 rules use synthetic demonstration limits.
        Laptop 1 advice reviews data quality and source-reported faults; scenario engineering limits are unverified.
        Approval records the original evidence only and sends no aircraft command.
      </div>
      {error && <p className="lm-review-error" role="alert">{error} Current evaluation is unavailable; retained cards may be out of date.</p>}
      {confirmation && <p className="lm-review-confirmation" role="status"><CheckCircle2 size={15} /> {confirmation}</p>}
      {loading && <p className="lm-muted">Loading pending recommendations and decision history…</p>}
      {!loading && pending.length === 0 && (
        <div className="lm-review-empty"><ShieldCheck size={18} /> No pending recommendations for operator review.</div>
      )}
      <div className="lm-review-list" aria-label="Current recommendations">
        {current.map((recommendation) => (
          <ReviewCard
            key={recommendation.recommendation_id}
            recommendation={recommendation}
            busy={Boolean(busyId)}
            busyStatus={busyId === recommendation.recommendation_id ? busyStatus : ''}
            onDecision={decide}
            unavailable={Boolean(error) || sourceUnavailable}
          />
        ))}
      </div>
      {pending.some((record) => !current.some((active) => active.recommendation_id === record.recommendation_id)) && (
        <details className="lm-recorded-evidence">
          <summary>Review earlier pending recommendations</summary>
          <p className="lm-muted">These are historical records, not current condition advice. Decisions apply to the recorded evidence below.</p>
          {pending.filter((record) => !current.some((active) => active.recommendation_id === record.recommendation_id)).map((recommendation) => (
            <ReviewCard key={recommendation.recommendation_id} recommendation={recommendation}
              busy={Boolean(busyId)} busyStatus={busyId === recommendation.recommendation_id ? busyStatus : ''}
              onDecision={decide} unavailable={Boolean(error) || sourceUnavailable} />
          ))}
        </details>
      )}
      <div className="lm-decision-history">
        <div className="lm-history-heading">
          <h4><Clock3 size={15} /> Decision history</h4>
          <span>{history.length} record{history.length === 1 ? '' : 's'}</span>
        </div>
        {history.length === 0
          ? <p className="lm-muted">No operator decision records yet.</p>
          : history.map((record) => (
            <article className="lm-history-row" key={record.recommendation_id}>
              <div className="lm-history-status">
                <span className={`lm-decision-status ${record.status}`}>{record.status}</span>
                <b>{record.recommendation_details.failure_mode}</b>
                <small>{record.source.replaceAll('_', ' ')} · {record.aircraft_id} · {record.mission_id}</small>
                {record.recommendation_details.replay_session_id && <small>
                  SYNTHETIC DATA · Replay session {record.recommendation_details.replay_session_id} · {record.recommendation_details.replay_scenario}
                </small>}
              </div>
              <p>{record.operator_comment || (record.status === 'pending' ? 'Awaiting operator review.' : 'No comment recorded.')}</p>
              <time dateTime={record.decision_at || record.created_at}>
                {record.decision_at
                  ? `Decision · ${new Date(record.decision_at).toLocaleString()}`
                  : `Created · ${new Date(record.created_at).toLocaleString()}`}
              </time>
              <details className="lm-history-evidence"><summary>Recorded recommendation and evidence</summary>
                <p>{record.scenario} · {record.recommendation_details.severity} · {record.recommendation_details.recommended_action}</p>
                <p>{record.recommendation_details.reason}</p>
                <Evidence items={record.recommendation_details.evidence} />
              </details>
            </article>
          ))}
      </div>
      <button type="button" className="lm-history-refresh" onClick={() => refreshReview()} disabled={Boolean(busyId)}>
        <RefreshCw size={13} /> Refresh records
      </button>
    </section>
  )
}

function TwinIntelligence({ data }) {
  if (!data) {
    return (
      <section className="lm-panel">
        <SectionHeader eyebrow="SKYNEX ENGINE MODEL" title="Digital Twin & intelligence" />
        <p className="lm-muted">Waiting for the SKYNEX twin snapshot.</p>
      </section>
    )
  }

  const firstAlert = data.maintenance?.[0]
  const alerts = (data.maintenance || []).filter((item) => item.priority !== 'routine')
  const modelHealth = data.hybrid?.fused_health ?? data.health_index

  return (
    <section className="lm-panel" aria-label="Digital Twin and intelligence">
      <SectionHeader
        eyebrow="MODEL OUTPUTS · NOT VALIDATED AI PREDICTIONS"
        title="Digital Twin & intelligence"
        detail={data.hybrid?.method || 'SKYNEX reduced-order twin and residual rules'}
      />
      <div className="lm-intelligence-grid">
        <article className="lm-intelligence-card">
          <span>DIGITAL TWIN HEALTH ESTIMATE</span>
          <strong>{Number.isFinite(modelHealth) ? `${modelHealth.toFixed(1)} / 100` : '—'}</strong>
          <small>Model-derived condition estimate; not flight clearance.</small>
        </article>
        <article className="lm-intelligence-card">
          <span>DIGITAL TWIN RUL ESTIMATE</span>
          <strong>{Number.isFinite(data.rul?.hours) ? `${data.rul.hours.toFixed(1)} h` : '—'}</strong>
          <small>{data.rul?.interval_kind || 'Model estimate; not a validated prediction.'}</small>
        </article>
        <article className="lm-intelligence-card">
          <span>MODEL MISSION ASSESSMENT</span>
          <strong>{data.mission?.decision || 'Unavailable'}</strong>
          <small>SKYNEX twin output; not an aircraft mission command.</small>
        </article>
      </div>
      <div className={`lm-alert-summary ${alerts.length ? 'has-alerts' : ''}`}>
        {alerts.length ? <AlertTriangle size={17} /> : <ShieldCheck size={17} />}
        <div>
          <b>{alerts.length ? `${alerts.length} rule-based alert${alerts.length === 1 ? '' : 's'}` : 'No active rule-based alerts'}</b>
          <p>
            {alerts.length
              ? alerts.map((item) => `${item.failure_mode} (${item.priority})`).join(' · ')
              : firstAlert?.failure_mode || 'No current maintenance rule triggered.'}
          </p>
        </div>
      </div>
      <p className="lm-ai-note">
        Validated AI prediction: <b>not available</b>. The displayed SKYNEX estimates and rules are demonstrator outputs,
        not independently validated predictions or flight recommendations.
      </p>
      <p className="lm-ai-note">
        These existing twin outputs are not computed from Laptop 1's raw Protocol 1 frame.
      </p>
      {data.disclaimer && <p className="lm-disclaimer">{data.disclaimer}</p>}
    </section>
  )
}

function TwinEngineTelemetry({ data, connection }) {
  const sensors = data?.sensors
  const external = data?.source === 'telemetry'
  const fresh = data?.quality?.status === 'live' && ['streaming', 'polling'].includes(connection)
  const sourceLabel = external ? 'EXTERNAL FEED RECEIVED BY SKYNEX' : 'SKYNEX BUILT-IN SIMULATION'

  return (
    <section className="lm-panel" aria-label="Engine sensor values">
      <SectionHeader
        eyebrow="SEVEN-CHANNEL ENGINE SENSOR SCHEMA"
        title="Engine telemetry"
        detail={data ? sourceLabel : 'Waiting for SKYNEX twin snapshot'}
      />
      {data && (
        <div className="lm-feed-meta">
          <span className={fresh ? 'fresh' : 'stale'}><i /> {fresh ? 'FRESH TWIN SNAPSHOT' : 'STALE / NOT LIVE'}</span>
          <span>Sample time: {data.timestamp ? new Date(data.timestamp).toLocaleString() : 'Unavailable'}</span>
          <span>Sequence: {Number.isInteger(data.sequence) ? data.sequence : '—'}</span>
        </div>
      )}
      <div className="lm-engine-grid">
        {engineChannels.map(({ key, label, unit, digits }) => {
          const value = sensors?.[key]
          return (
            <article className={`lm-value-card ${Number.isFinite(value) ? '' : 'unavailable'}`} key={key}>
              <span>{label}</span>
              <strong>{Number.isFinite(value) ? value.toFixed(digits) : '—'}<small>{unit}</small></strong>
              <em>{Number.isFinite(value) ? (external ? 'EXTERNAL SAMPLE' : 'TWIN SIMULATION') : 'UNAVAILABLE'}</em>
            </article>
          )
        })}
      </div>
      <p className="lm-muted">
        This panel shows the existing SKYNEX twin schema only. Laptop 1 propulsion data remains separate and unmapped.
      </p>
    </section>
  )
}

export default function LiveMission() {
  const { snapshot, connection, error } = useTwin()
  const [laptop1, setLaptop1] = useState({
    mode: null,
    status: 'connecting',
    latest_frame: null,
    last_received_at: null,
    last_error: null,
  })
  const [sourceBusy, setSourceBusy] = useState(false)
  const [sourceError, setSourceError] = useState('')
  const sourceRevision = useRef(0)
  const sourceAction = useRef(false)
  const offline = laptop1.mode === 'OFFLINE_REPLAY'
  const twinScenario = snapshot?.controls?.scenario

  async function sourceCommand(path, body) {
    if (sourceAction.current) return
    sourceAction.current = true
    sourceRevision.current += 1
    setSourceBusy(true)
    setSourceError('')
    try {
      const next = await request(path, body)
      setLaptop1(next)
    } catch (error) {
      setSourceError(error.message)
      setLaptop1(current => ({ ...current, status: 'unavailable', latest_frame: null }))
    } finally {
      sourceAction.current = false
      setSourceBusy(false)
    }
  }

  useEffect(() => {
    let stopped = false
    let refreshing = false
    const abort = new AbortController()
    async function refreshLaptop1() {
      if (refreshing || sourceAction.current) return
      refreshing = true
      const revision = sourceRevision.current
      try {
        const status = await request('/telemetry/source', undefined, AbortSignal.any([abort.signal, AbortSignal.timeout(12000)]))
        if (!stopped && revision === sourceRevision.current) setLaptop1(status)
      } catch {
        if (!stopped && revision === sourceRevision.current) setLaptop1((current) => ({ ...current, status: 'unavailable' }))
      } finally {
        refreshing = false
      }
    }

    refreshLaptop1()
    const interval = setInterval(refreshLaptop1, 1000)
    return () => {
      stopped = true
      abort.abort()
      clearInterval(interval)
    }
  }, [])

  const frame = sourceBusy ? null : laptop1.latest_frame
  const liveWarning = !offline && laptop1.status !== 'connected'

  return (
    <div className="live-mission">
      <section className="page-title lm-page-title">
        <div>
          <span className="eyebrow">SKYNEX 3.0 · LIVE / OFFLINE VALIDATION</span>
          <h2>Live Mission</h2>
          <p>{offline ? 'Offline Protocol 1 fixture playback; synthetic data only.' : 'Read-only telemetry from the Eagle Eye Mini simulator; no remote controls are enabled.'}</p>
        </div>
        <div className="lm-connection-badges">
          <span className="lm-demo-badge"><Activity size={13} /> {offline ? 'OFFLINE REPLAY / SYNTHETIC DATA' : 'SIMULATED DATA'}</span>
          <span className={`lm-status-offline ${laptop1.status === 'connected' || laptop1.status === 'stale' ? laptop1.status : ''}`}>
            <i /> {offline ? `OFFLINE REPLAY · ${laptop1.replay?.state?.toUpperCase()}` : `LIVE LAPTOP 1 · ${laptop1.status.toUpperCase()}`}
          </span>
          <span className={`lm-status-twin ${connection === 'streaming' ? 'online' : ''}`}>
            <i /> SKYNEX BACKEND {connection.toUpperCase()}
          </span>
          <span className="lm-last-updated">
            <Clock3 size={12} /> LAST RECEIVED {formatTimestamp(laptop1.last_received_at)}
            {Number.isInteger(frame?.seq) && ` · SEQ ${frame.seq}`}
          </span>
        </div>
      </section>

      {error && <div className="lm-link-warning" role="status">{error}</div>}
      {liveWarning && <div className="lm-link-warning" role="alert">
        Live Laptop 1 telemetry is {laptop1.status}. {laptop1.last_error ? `Diagnostic: ${laptop1.last_error}.` : 'Waiting for the first valid Protocol 1 frame.'}
        {frame && ' Retained values below are historical.'}
      </div>}

      <ScenarioReplay source={laptop1} busy={sourceBusy} error={sourceError} onCommand={sourceCommand} />

      <div className="lm-main-grid">
        <SimulatorViewport status={laptop1.status} frame={frame} offline={offline} replayState={laptop1.replay?.state} />
        <MissionStatus
          frame={frame}
          status={laptop1.status}
          lastReceivedAt={laptop1.last_received_at}
          twinScenario={offline ? undefined : twinScenario}
          offline={offline}
        />
      </div>

      <LiveEngineHealth frame={frame} offline={offline} />
      <FlightTelemetry frame={frame} />
      <EnvironmentMonitoring frame={frame} />
      <FaultCentre frame={frame} status={laptop1.last_error || laptop1.status} offline={offline} />

      {sourceBusy || !laptop1.mode ? <p className="lm-muted">Waiting for the selected telemetry source…</p> : (
        <RecommendationReviewCentre
          key={`${laptop1.mode}:${laptop1.replay?.session_id || ''}:${laptop1.replay?.state || ''}`}
          sourceMode={laptop1.mode} replaySessionId={laptop1.replay?.session_id}
          sourceUnavailable={laptop1.status === 'unavailable'} />
      )}

      {!offline && <>
        <TwinEngineTelemetry data={snapshot} connection={connection} />
        <TwinIntelligence data={snapshot} />
      </>}
      <DisabledControls />
    </div>
  )
}
