import { useState } from 'react'
import { Activity, Clock3, Radio, RefreshCw, Zap } from 'lucide-react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { CHART_HISTORY_LIMIT, SENSOR_DEFINITIONS, chartRows, measurementState, sensorKeys, streamFreshness } from './liveMonitoringModel'

const colors = { rpm: '#68e7d0', egt: '#efc36e', cht: '#f29a70', oil_temperature: '#aa9ae4', oil_pressure: '#79b9e8', fuel_flow: '#7fd39b', vibration: '#e58db6' }
const scenarioLabels = { urban: 'Urban', volcanic: 'Volcanic', desert: 'Desert', forest: 'Forest', snow_mountain: 'Snow Mountain' }
const formatValue = (value, digits = 1) => typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString('en-US', { maximumFractionDigits: digits }) : 'UNAVAILABLE'
const timeLabel = value => value ? new Date(value).toLocaleTimeString('en-GB', { hour12: false, timeZone: 'UTC' }) : 'UNAVAILABLE'

function SensorCard({ snapshot, keyName, connection }) {
  const definition = SENSOR_DEFINITIONS[keyName]
  const reading = measurementState(snapshot?.sensors?.[keyName])
  const freshness = streamFreshness(connection, snapshot?.quality)
  return <article className={`live-sensor-card ${reading.state.toLowerCase()}`}>
    <div className="live-sensor-head"><span>{definition.label}</span><span>{reading.state}</span></div>
    <strong>{reading.state === 'VALID' ? formatValue(reading.value, keyName === 'rpm' ? 0 : 2) : reading.state}</strong>
    {reading.state === 'VALID' && <small>{definition.unit}</small>}
    <p>{definition.name}</p>
    <footer><span>LAST {timeLabel(snapshot?.timestamp)}</span><b>{freshness}</b></footer>
  </article>
}

function TrendChart({ history, keyName, title, prominent = false, windowSize }) {
  const definition = SENSOR_DEFINITIONS[keyName]
  const rows = chartRows(history, keyName, windowSize)
  return <section className={`live-chart ${prominent ? 'prominent' : ''}`}>
    <header><div><span className="v-eyebrow">HISTORICAL WINDOW · {rows.length}/{CHART_HISTORY_LIMIT}</span><h4>{title}</h4></div><b>{definition.unit}</b></header>
    {rows.length ? <ResponsiveContainer width="100%" height={prominent ? 220 : 170}>
      <LineChart data={rows} margin={{ top: 10, right: 12, left: -18, bottom: 0 }}>
        <CartesianGrid stroke="#ffffff0b" vertical={false}/>
        <XAxis dataKey="timestamp" tickFormatter={timeLabel} minTickGap={45} stroke="#607985" tick={{ fontSize: 9 }}/>
        <YAxis stroke="#607985" tick={{ fontSize: 9 }} width={45} domain={['auto', 'auto']}/>
        <Tooltip labelFormatter={value => new Date(value).toISOString()} formatter={value => [value == null ? 'UNAVAILABLE' : `${formatValue(value, 2)} ${definition.unit}`, definition.label]} contentStyle={{ background: '#14232d', border: '1px solid #354a55', borderRadius: 8, fontSize: 11 }}/>
        <Line type="monotone" dataKey="value" stroke={colors[keyName]} strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false}/>
      </LineChart>
    </ResponsiveContainer> : <div className="live-chart-empty">HISTORICAL DATA UNAVAILABLE</div>}
  </section>
}

export default function LiveEngineMonitoring({ data, history = [], connection }) {
  const [windowSize, setWindowSize] = useState(CHART_HISTORY_LIMIT)
  const freshness = streamFreshness(connection, data?.quality)
  const replay = data?.source === 'replay' || data?.source === 'OFFLINE_REPLAY'
  const availableKeys = sensorKeys.filter(key => data?.sensors?.[key] !== undefined || history.some(row => row.sensors?.[key] !== undefined))
  const chartKeys = availableKeys.length ? availableKeys : sensorKeys
  const scenario = scenarioLabels[data?.controls?.scenario] || data?.controls?.scenario || 'UNAVAILABLE'
  const mission = data?.controls?.mission || {}
  return <section className="live-monitoring" id="live-monitoring" aria-label="Live engine monitoring">
    <div className="live-monitoring-heading">
      <div><span className="v-eyebrow"><Radio size={11}/> PHASE 7.3 · ENGINE TELEMETRY</span><h2>Live engine monitoring</h2><p>Schema-backed measurements only. Missing fields remain unavailable and are never replaced with zero.</p></div>
      <div className={`live-mode ${replay ? 'replay' : 'live'}`}><i/>{replay ? 'REPLAY' : 'LIVE'} MODE</div>
    </div>
    <div className="live-context">
      <span>AIRCRAFT <b>{data?.engine_id || 'UNAVAILABLE'}</b></span><span>MISSION <b>{mission.mission_id || 'UNAVAILABLE'}</b></span><span>SCENARIO <b>{scenario}</b></span><span>SOURCE <b>{data?.source || 'UNAVAILABLE'}</b></span><span>TIMESTAMP <b>{timeLabel(data?.timestamp)}</b></span>
    </div>
    <div className="live-stream-strip"><span><Radio size={14}/> STREAM <b>{connection?.toUpperCase() || 'UNAVAILABLE'}</b></span><span><Clock3 size={14}/> LAST RECEIVED <b>{timeLabel(data?.timestamp)}</b></span><span><Activity size={14}/> FRESHNESS <b>{freshness}</b></span><span><RefreshCw size={14}/> POLLING FALLBACK <b>{connection === 'polling' ? 'ACTIVE' : 'STANDBY'}</b></span></div>
    <div className="live-sensor-grid">{sensorKeys.map(key => <SensorCard key={key} snapshot={data} keyName={key} connection={connection}/>)}</div>
    <div className="live-chart-controls"><span>HISTORICAL TIME WINDOW</span><select aria-label="Historical time window" value={windowSize} onChange={event => setWindowSize(Number(event.target.value))}><option value={30}>Last 30 frames</option><option value={90}>Last 90 frames</option><option value={CHART_HISTORY_LIMIT}>Last 180 frames</option></select></div>
    <div className="live-chart-grid">
      <TrendChart history={history} keyName="rpm" title="RPM trend" prominent windowSize={windowSize}/>
      {chartKeys.filter(key => key !== 'rpm').map(key => <TrendChart key={key} history={history} keyName={key} title={`${SENSOR_DEFINITIONS[key].label} trend`} windowSize={windowSize}/>)}
    </div>
    <div className="live-replay-note"><Zap size={15}/><span><b>{replay ? 'REPLAY DATA' : 'LIVE DATA'}</b> Historical charts use received V2 timestamps and sequence identifiers. Protocol 1 offline replay frames are not merged into this chart history; use the existing replay surface for replay control.</span></div>
  </section>
}
