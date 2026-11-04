import { Link } from 'react-router-dom'
import { Award, Layers, ArrowRight, Battery, Fuel, Gauge, Radio, Sparkles, Thermometer, Zap } from 'lucide-react'
import { useMission } from '../hooks/useMission'
import { HealthScore, MissionRecommendation, RemainingLife } from '../components/MissionMetrics'
import { TelemetryChart } from '../components/Charts'
import MissionEnvironment from '../components/MissionEnvironment'
import { useTwin } from '../v2/useTwin'

const telemetryReadings = [
  { label: 'ENGINE SPEED', field: 'rpm', unit: 'rpm', digits: 0, Icon: Gauge },
  { label: 'EXHAUST GAS TEMP', field: 'egt', unit: '°C', digits: 1, Icon: Thermometer },
  { label: 'CYLINDER HEAD TEMP', field: 'cht', unit: '°C', digits: 1, Icon: Thermometer },
  { label: 'FUEL FLOW', field: 'fuel_flow', unit: 'L/h', digits: 2, Icon: Fuel },
  { label: 'BATTERY VOLTAGE', field: 'battery_voltage', unit: 'V', digits: 2, Icon: Battery },
  { label: 'CURRENT', field: 'current_a', unit: 'A', digits: 2, Icon: Zap },
]

const connectionLabels = {
  connecting: 'CONNECTING',
  streaming: 'LIVE STREAM',
  polling: 'API POLLING',
  reconnecting: 'RECONNECTING',
  offline: 'OFFLINE',
}

function formatSampleTime(timestamp) {
  if (typeof timestamp !== 'string' || !timestamp) return 'Unavailable'
  const parsed = new Date(timestamp)
  return Number.isNaN(parsed.getTime()) ? timestamp : parsed.toLocaleString()
}

export function Inject() {
  const { scenario, setScenario } = useMission()
  const scenarios = [
    ['cooling', 'Inject cooling fault'],
    ['sensor', 'Inject sensor fault'],
    ['bearing', 'Inject bearing wear'],
    ['degradation', 'Inject engine degradation'],
  ]

  return (
    <section className="fault-injector" aria-labelledby="fault-injector-title">
      <div>
        <span className="eyebrow">SIMULATION CONTROLS</span>
        <h3 id="fault-injector-title">Fault injection demo</h3>
        <p>Change the local mock telemetry scenario. No aircraft or backend is controlled.</p>
      </div>
      <div className="fault-actions">
        {scenarios.map(([value, label]) => (
          <button
            className={scenario === value ? 'selected' : ''}
            aria-pressed={scenario === value}
            onClick={() => setScenario(value)}
            key={value}
          >
            {label}
          </button>
        ))}
        <button className="reset" onClick={() => setScenario('normal')}>Reset nominal</button>
      </div>
    </section>
  )
}

export function Recommendation() {
  const { recommendation, risk, fault } = useMission()
  return <MissionRecommendation recommendation={recommendation} risk={risk} fault={fault} />
}

export default function Dashboard() {
  const mission = useMission()
  const twin = useTwin()
  const latest = twin.snapshot || twin.history.at(-1)
  const sensors = latest?.sensors
  const apiSource = typeof twin.snapshot?.source === 'string' && twin.snapshot.source
    ? twin.snapshot.source.toUpperCase().replaceAll('_', ' ')
    : 'TWIN API'
  const hasTwinData = Boolean(latest)
  const isConnected = twin.connection === 'streaming' || twin.connection === 'polling'
  const chartData = twin.history.slice(-60).map((sample) => ({
    ...sample.sensors,
    time: formatSampleTime(sample.timestamp),
  }))
  const telemetryCharts = [
    ['rpm', 'ENGINE SPEED', '#53c7ed', 'rpm'],
    ['egt', 'EXHAUST GAS TEMPERATURE', '#8da9f4', '°C'],
    ['cht', 'CYLINDER HEAD TEMPERATURE', '#69b7db', '°C'],
    ['fuel_flow', 'FUEL FLOW', '#a7b8e8', 'L/h'],
  ]

  return (
    <div className="dashboard-wrapper">
      <div className="dashboard-content">
        <section className="dashboard-hero" aria-labelledby="mission-overview-title">
          <div className="dashboard-identity">
            <span className="eyebrow">SKYNEX 3.0 / UAV ENGINE DIGITAL TWIN</span>
            <span className="simulation-badge">LOCAL FAULT INJECTION · SYNTHETIC</span>
          </div>
          <div className="page-title">
            <div>
              <span className="eyebrow">MISSION CONTROL / PROPULSION SYSTEM</span>
              <h2 id="mission-overview-title">Mission overview</h2>
              <p>Aircraft status, source-reported telemetry and simulated mission assessment.</p>
            </div>
            <div className={`mission-state dashboard-api-status ${twin.connection}`} role="status">
              <i /> TWIN API · {connectionLabels[twin.connection] || 'STATUS UNKNOWN'}
            </div>
          </div>
          <div className="dashboard-operations-strip" aria-label="Aircraft and mission overview">
            <div>
              <span>AIRCRAFT</span>
              <strong>{twin.snapshot?.engine_id || 'UAV-01'}</strong>
              <small>{twin.snapshot?.engine_id ? 'TWIN API' : 'DEMO AIRCRAFT'}</small>
            </div>
            <div>
              <span>MISSION</span>
              <strong>{twin.snapshot?.mission?.mission_id || mission.mission}</strong>
              <small>{twin.snapshot?.mission?.decision || `LOCAL SIMULATION · ${mission.mission}`}</small>
            </div>
            <div>
              <span>TELEMETRY SAMPLE</span>
              <strong>{formatSampleTime(latest?.timestamp)}</strong>
              <small>{hasTwinData ? apiSource : 'WAITING FOR API DATA'}</small>
            </div>
          </div>
          <p className="dashboard-source-note">Twin telemetry is shown only when supplied by the API. Health, remaining life and mission recommendations below are local synthetic estimates, not aircraft operating limits or flight clearance.</p>
        </section>
        <section className="dashboard-quick-access" aria-label="Judge evaluation quick access">
          <Award size={22} aria-hidden="true" />
          <div>
            <h3>Explore the demonstrator</h3>
            <p>Run deterministic fault scenarios or inspect the digital twin architecture.</p>
          </div>
          <div className="dashboard-quick-actions">
            <Link to="/judge-demo" className="dashboard-action primary">
              <Sparkles size={15} aria-hidden="true" /> Launch Judge Demo <ArrowRight size={15} aria-hidden="true" />
            </Link>
            <Link to="/architecture" className="dashboard-action">
              <Layers size={15} aria-hidden="true" /> View Architecture
            </Link>
          </div>
        </section>

      <div className="overview-grid">
          <section className="dashboard-assessment-panel" aria-label="Mission assessment summary">
            <div className="dashboard-assessment-heading">
              <span className="eyebrow">LOCAL RULE-BASED ASSESSMENT · SYNTHETIC TELEMETRY</span>
              <h2>Mission assessment summary</h2>
              <p>This demonstrator recommendation is not an AI service response or flight authorization.</p>
            </div>
            <Recommendation />
          </section>
          <section className="panel health-panel" aria-label="Engine health and remaining life">
            <div className="dashboard-health">
            <div>
              <span className="eyebrow">SYNTHETIC ENGINE HEALTH</span>
              <HealthScore value={mission.health} />
            </div>
            <RemainingLife
              hours={mission.rul}
              lower={mission.rulRange.lower}
              upper={mission.rulRange.upper}
            />
          </div>
          <div className="readiness">
            <span>Data source <b>Local simulation</b></span>
            <span>Data integrity <b>Synthetic stream</b></span>
          </div>
        </section>
      </div>
      <section className="live-readouts" aria-labelledby="live-readouts-title">
        <div className="section-heading">
          <div>
            <span className="eyebrow">SOURCE-REPORTED · TWIN API</span>
            <h2 id="live-readouts-title">Engine telemetry</h2>
            <p className="dashboard-section-note">Values are displayed only when present in the latest received API snapshot.</p>
          </div>
          <span className="dashboard-sample-time">Connection <b>{connectionLabels[twin.connection] || 'STATUS UNKNOWN'}</b></span>
        </div>
        {twin.error && (
          <div className="dashboard-data-alert" role="status">
            <Radio size={16} aria-hidden="true" />
            <span>{twin.error}</span>
          </div>
        )}
        {!hasTwinData && !twin.error && (
          <div className="dashboard-data-alert" role="status">
            <Radio size={16} aria-hidden="true" />
            <span>Telemetry is not available yet. No sensor values are being inferred or substituted.</span>
          </div>
        )}
        {hasTwinData && !isConnected && (
          <div className="dashboard-data-alert warning" role="status">
            <Radio size={16} aria-hidden="true" />
            <span>Telemetry link is {connectionLabels[twin.connection]?.toLowerCase() || 'unavailable'}; showing the last received snapshot.</span>
          </div>
        )}
        <div className="live-readout-grid">
          {telemetryReadings.map(({ label, field, unit, digits, Icon }) => {
            const value = sensors?.[field]
            const available = typeof value === 'number' && Number.isFinite(value)
            return (
              <article className={`live-readout ${available ? '' : 'unavailable'}`} key={field}>
                <div className="live-readout-heading">
                  <span>{label}</span>
                  <Icon size={16} aria-hidden="true" />
                </div>
                <strong>{available ? value.toFixed(digits) : '—'}<small>{unit}</small></strong>
                <small className="readout-status">{available ? `${apiSource} SAMPLE` : 'NOT PROVIDED'}</small>
              </article>
            )
          })}
        </div>
        <p className="dashboard-sample-time">Sample time <b>{formatSampleTime(latest?.timestamp)}</b></p>
      </section>
      <section className="dashboard-live-charts" aria-label="Live engine telemetry charts">
        <div className="section-heading">
          <div>
            <span className="eyebrow">API HISTORY · SOURCE-REPORTED</span>
            <h2>Engine trends</h2>
            <p className="dashboard-section-note">{chartData.length ? `${chartData.length} received samples` : 'No API history samples available.'}</p>
          </div>
        </div>
        <div className="dashboard-chart-grid">
          {telemetryCharts.map(([field, title, color, unit]) => (
            <TelemetryChart
              key={field}
              data={chartData}
              field={field}
              title={title}
              color={color}
              unit={unit}
            />
          ))}
        </div>
      </section>
      <MissionEnvironment />
      <Inject />
      </div>
      <svg
        className="uav-watermark"
        viewBox="0 0 200 200"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        <path
          d="M100 20L120 60H160L130 85L145 130L100 105L55 130L70 85L40 60H80L100 20Z"
          fill="currentColor"
          opacity="0.12"
        />
        <circle cx="100" cy="100" r="80" stroke="currentColor" strokeWidth="2" opacity="0.08" />
        <path
          d="M100 40L115 70H145L125 90L135 120L100 100L65 120L75 90L55 70H85L100 40Z"
          fill="currentColor"
          opacity="0.10"
        />
      </svg>
    </div>
  )
}
