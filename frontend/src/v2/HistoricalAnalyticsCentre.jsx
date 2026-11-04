import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, BarChart3, Database, RefreshCw } from 'lucide-react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { getTwinFaultHistory, getTwinHistory, getTwinMissions } from './api'
import { HISTORICAL_LIMIT, HISTORICAL_SENSORS, chartData, dataQuality, normalizeFaultResponse, normalizeHistoricalResponse, provenanceLabel, timeCoverage, trendUnavailable } from './historicalAnalyticsModel'

const colors = { rpm: '#68e7d0', egt: '#efc36e', cht: '#f29a70', oil_temperature: '#aa9ae4', oil_pressure: '#79b9e8', fuel_flow: '#7fd39b', vibration: '#e58db6' }
const formatTime = value => value ? new Date(value).toISOString() : 'Not provided'

function Trend({ sensor, records }) {
  const definition = HISTORICAL_SENSORS[sensor]
  const data = chartData(records, sensor)
  const valid = data.filter(row => row.value !== null)
  return <article className="historical-trend"><header><div><span className="v-eyebrow">{definition.label}</span><h3>{definition.unit}</h3></div><b>{valid.length} valid</b></header>{valid.length >= 2 ? <ResponsiveContainer width="100%" height={170}><LineChart data={data} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}><CartesianGrid stroke="#ffffff0b" vertical={false}/><XAxis dataKey="timestamp" tickFormatter={formatTime} minTickGap={45} tick={{ fontSize: 8 }} stroke="#607985"/><YAxis domain={['auto', 'auto']} tick={{ fontSize: 8 }} stroke="#607985"/><Tooltip labelFormatter={formatTime} formatter={value => [value == null ? 'UNAVAILABLE' : `${value} ${definition.unit}`, definition.label]} contentStyle={{ background: '#14232d', border: '1px solid #354a55', fontSize: 10 }}/><Line dataKey="value" stroke={colors[sensor]} strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false}/></LineChart></ResponsiveContainer> : <div className="historical-empty">INSUFFICIENT VALID HISTORY</div>}</article>
}

export default function HistoricalAnalyticsCentre() {
  const [state, setState] = useState({ status: 'loading', records: [], faults: [], missions: [], error: '', duplicates: 0 })
  const [refresh, setRefresh] = useState(0)
  const [windowDays, setWindowDays] = useState('all')
  useEffect(() => {
    const controller = new AbortController()
    Promise.all([getTwinHistory(HISTORICAL_LIMIT, controller.signal), getTwinFaultHistory(HISTORICAL_LIMIT, controller.signal), getTwinMissions(200, controller.signal)])
      .then(([history, faults, missions]) => {
        const normalized = normalizeHistoricalResponse(history)
        const faultData = normalizeFaultResponse(faults)
        if (!normalized.valid || !faultData.valid || !Array.isArray(missions?.missions)) throw new Error('Historical response was malformed.')
        setState({ status: 'ready', records: normalized.records, faults: faultData.records, missions: missions.missions, error: '', duplicates: normalized.duplicatesExcluded })
      }).catch(error => { if (error.name !== 'AbortError') setState(current => ({ ...current, status: 'error', error: error.message || 'Historical analytics unavailable.' })) })
    return () => controller.abort()
  }, [refresh])
  const cutoff = windowDays === 'all' ? null : Date.now() - Number(windowDays) * 24 * 60 * 60 * 1000
  const records = useMemo(() => cutoff === null
    ? state.records
    : state.records.filter(record => Date.parse(record.timestamp) >= cutoff), [cutoff, state.records])
  const faults = useMemo(() => cutoff === null
    ? state.faults
    : state.faults.filter(record => Date.parse(record.timestamp) >= cutoff), [cutoff, state.faults])
  const coverage = useMemo(() => timeCoverage(records), [records])
  const quality = useMemo(() => dataQuality(records), [records])
  const trend = trendUnavailable()
  const provenance = provenanceLabel(records)
  return <section className="historical-analytics-centre" id="historical-analytics" aria-label="Historical analytics and predictive intelligence">
    <header className="historical-heading"><div><span className="v-eyebrow"><BarChart3 size={12}/> STORED TWIN HISTORY · API SOURCE</span><h2>Stored telemetry history</h2><p>Read-only sensor history and mission records returned by the existing twin service.</p></div><div className="historical-controls"><label>TIME RANGE<select aria-label="Historical time range" value={windowDays} onChange={event => setWindowDays(event.target.value)}><option value="all">All returned history</option><option value="1">Last 24 hours</option><option value="7">Last 7 days</option><option value="30">Last 30 days</option></select></label><button className="v-icon-button" aria-label="Refresh historical analytics" onClick={() => setRefresh(value => value + 1)}><RefreshCw size={15}/></button></div></header>
    {state.status === 'loading' && <div className="historical-state">LOADING HISTORICAL DATA</div>}
    {state.status === 'error' && <div className="historical-state error"><AlertTriangle size={16}/> HISTORICAL ANALYTICS UNAVAILABLE · {state.error}</div>}
    {state.status === 'ready' && <><div className="historical-scope"><span>RECORDS IN RANGE <b>{quality.totalRecords}</b></span><span>VALID READINGS <b>{quality.valid}</b></span><span>MISSING <b>{quality.missing}</b></span><span>INVALID <b>{quality.invalid}</b></span><span>DUPLICATES EXCLUDED <b>{state.duplicates}</b></span><span>PROVENANCE <b>{provenance}</b></span></div><div className="historical-coverage"><span><Database size={14}/> TIME COVERAGE <b>{formatTime(coverage.start)} → {formatTime(coverage.end)}</b></span><span>MISSION SCOPE <b>{state.missions.length ? `${state.missions.length} persisted missions` : 'Not available'}</b></span><span>SCENARIO <b>Not available in history records</b></span></div><div className="historical-chart-grid">{Object.keys(HISTORICAL_SENSORS).map(sensor => <Trend key={sensor} sensor={sensor} records={records}/>)}</div><div className="historical-lower-grid"><section className="historical-panel"><header><span className="v-eyebrow">WARNING HISTORY</span><b>{faults.length ? faults.length : 'NOT AVAILABLE'}</b></header>{faults.length ? <div className="historical-warning-list">{faults.slice(0, 20).map((item, index) => <div key={`${item.sequence}-${index}`}><b>{item.fault?.failure_mode || item.fault?.id || 'Finding not provided'}</b><span>{item.mission_id || 'Mission not provided'} · {formatTime(item.timestamp)}</span></div>)}</div> : <div className="historical-empty">WARNING HISTORY NOT AVAILABLE</div>}</section><section className="historical-panel"><header><span className="v-eyebrow">PREDICTIVE INTELLIGENCE</span><b>{trend.status}</b></header><div className="historical-empty">TREND ANALYSIS NOT AVAILABLE<div>{trend.reason}</div></div></section></div></>}
  </section>
}
