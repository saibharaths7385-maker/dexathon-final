import { useMemo, useState } from 'react'
import { Activity, Crosshair, Plane, ShieldAlert, ShieldCheck, Users } from 'lucide-react'

const tone = readiness => {
  const status = String(readiness || '').toUpperCase()
  if (['ACTIVE', 'READY', 'NOMINAL'].includes(status)) return 'nominal'
  if (['WARNING', 'MONITOR', 'STANDBY'].includes(status)) return 'monitor'
  if (['CRITICAL', 'MAINTENANCE', 'MAINTENANCE REQUIRED'].includes(status)) return 'critical'
  return 'unknown'
}
const n = value => Number.isFinite(value) ? value.toFixed(0) : 'N/A'

export default function FleetCommandCenter({ fleet, lastUpdated }) {
  const [selected, setSelected] = useState('')
  const assets = useMemo(() => Array.isArray(fleet?.assets) ? fleet.assets : [], [fleet?.assets])
  if (!fleet) return <section className="v-panel fleet-loading"><Activity size={18}/><span>Synchronising fleet operational picture…</span></section>
  if (assets.length === 0) return <section className="v-panel fleet-loading"><Activity size={18}/><span>No fleet assets are available in the current API response.</span></section>
  const activeId = assets.some(item => item.engine_id === selected) ? selected : assets[0].engine_id
  const asset = assets.find(item => item.engine_id === activeId)
  const summary = fleet.summary || {}
  return <section className="fleet-command" id="fleet">
    <div className="v-section-heading"><div><span className="v-eyebrow">FLEET SNAPSHOT · SOURCE API</span><h2><Users size={20}/> Fleet command center</h2></div><span><Activity size={14}/> {assets.length} returned assets · last update {lastUpdated ? new Date(lastUpdated).toLocaleString() : 'awaiting first refresh'}</span></div>
    <div className="fleet-kpis">
      <article><span>FLEET READINESS</span><b>{n(summary.fleet_readiness_score)}{Number.isFinite(summary.fleet_readiness_score) && <small>%</small>}</b><i className="nominal"/></article>
      <article><span>MISSION AVAILABLE</span><b>{n(summary.mission_available)}{Number.isFinite(summary.asset_count) && <small> / {summary.asset_count}</small>}</b><i className="blue"/></article>
      <article><span>FLEET HEALTH</span><b>{n(summary.fleet_health)}{Number.isFinite(summary.fleet_health) && <small> / 100</small>}</b><i className="purple"/></article>
      <article><span>HIGH-RISK ASSETS</span><b>{n(summary.high_risk_assets)}<small> API reported</small></b><i className={summary.high_risk_assets > 0 ? 'amber' : 'nominal'}/></article>
    </div>
    <div className="fleet-grid">
      <article className="v-panel fleet-map"><div className="v-panel-head"><div><span className="v-eyebrow">RISK MAP / ASSET POSITIONING</span><h3><Crosshair size={16}/> Operational sectors</h3></div><span className="v-muted">SELECT AN AIRCRAFT</span></div>
        <div className="fleet-radar"><span className="radar-ring one"/><span className="radar-ring two"/><span className="radar-axis vertical"/><span className="radar-axis horizontal"/>{assets.filter(item => Number.isFinite(item.coordinates?.x) && Number.isFinite(item.coordinates?.y)).map(item => <button key={item.engine_id} onClick={() => setSelected(item.engine_id)} className={`fleet-blip ${tone(item.readiness)} ${activeId === item.engine_id ? 'selected' : ''}`} style={{ left: `${item.coordinates.x}%`, top: `${item.coordinates.y}%` }} aria-label={`Select ${item.engine_id}, status ${item.readiness || 'not provided'}`}><Plane size={13}/><b>{item.engine_id.slice(-2)}</b></button>)}</div>
        <div className="fleet-map-key"><span><i className="nominal"/> ACTIVE / READY</span><span><i className="monitor"/> WARNING / MONITOR</span><span><i className="critical"/> CRITICAL / MAINTENANCE</span><span><i className="unknown"/> STATUS UNAVAILABLE</span></div>
      </article>
      <article className="v-panel fleet-asset"><div className="v-panel-head"><div><span className="v-eyebrow">SELECTED ASSET / CONDITION SUMMARY</span><h3><ShieldCheck size={16}/> {asset?.engine_id || 'Asset unavailable'} · {asset?.sector || 'Sector not provided'}</h3></div><span className={`v-badge ${tone(asset?.readiness)}`}>{asset?.readiness || 'STATUS NOT PROVIDED'}</span></div>
        <div className="fleet-selected-score"><strong>{n(asset?.health_index)}</strong><span>health index</span><div><b>{n(asset?.reliability_percent)}{Number.isFinite(asset?.reliability_percent) && '%'}</b><small>reported reliability</small></div></div>
        <dl><div><dt>Reported remaining life</dt><dd>{n(asset?.rul_hours)}{Number.isFinite(asset?.rul_hours) && ' h'}</dd></div><div><dt>Reported risk</dt><dd>{n(asset?.risk_percent)}{Number.isFinite(asset?.risk_percent) && '%'}</dd></div><div><dt>Callsign</dt><dd>{asset?.callsign || 'Not provided'}</dd></div></dl>
        <p><ShieldAlert size={14}/> Fleet metrics and asset positions are displayed only when returned by the existing fleet API. Missing fields are not estimated.</p>
      </article>
    </div>
    <div className="fleet-asset-table">{assets.map(item => <button key={item.engine_id} onClick={() => setSelected(item.engine_id)} className={`${activeId === item.engine_id ? 'selected' : ''} ${tone(item.readiness)}`}><span className={`fleet-state ${tone(item.readiness)}`}/><b>{item.engine_id}</b><small>{item.sector || 'Sector not provided'}</small><div className="fleet-card-visual"><Plane size={20}/><strong style={Number.isFinite(item.health_index) ? { '--health': `${item.health_index}%` } : undefined}>{n(item.health_index)}</strong></div><em>{n(item.rul_hours)}{Number.isFinite(item.rul_hours) && ' h'} RUL</em><i>{item.readiness || 'STATUS NOT PROVIDED'}</i></button>)}</div>
  </section>
}
