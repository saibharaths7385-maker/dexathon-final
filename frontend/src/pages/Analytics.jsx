import { useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Card, SectionHeading, TelemetryChart } from '../components'
import { useMission } from '../hooks/useMission'
import { telemetryHealth } from '../data/mockData'
import HistoricalAnalyticsCentre from '../v2/HistoricalAnalyticsCentre'
import '../v2/v2.css'

export default function Analytics() {
  const { history } = useMission()
  const [windowMinutes, setWindowMinutes] = useState('15')
  const samples = useMemo(() => {
    const cutoff = windowMinutes === 'all' ? null : Date.now() - Number(windowMinutes) * 60_000
    return history
      .filter((sample) => {
        if (cutoff === null) return true
        const timestamp = Date.parse(sample.timestamp)
        return Number.isFinite(timestamp) && timestamp >= cutoff
      })
      .map((sample) => ({ ...sample, health_score: telemetryHealth(sample) }))
  }, [history, windowMinutes])
  const faultFrequency = useMemo(() => {
    const counts = new Map([
      ['HEALTHY', 0],
      ['COOLING_ISSUE', 0],
      ['ENGINE_DEGRADATION', 0],
      ['BEARING_WEAR', 0],
      ['SENSOR_FAULT', 0],
    ])
    samples.forEach(({ fault_classification }) => {
      if (counts.has(fault_classification)) {
        counts.set(fault_classification, counts.get(fault_classification) + 1)
      }
    })
    return [...counts].map(([fault, count]) => ({ fault: fault.replaceAll('_', ' '), count }))
  }, [samples])

  return (
    <div className="analytics-page">
      <SectionHeading
        eyebrow="STORED TWIN HISTORY · LOCAL DEMONSTRATOR"
        title="Historical analytics"
      />
      <HistoricalAnalyticsCentre />
      <section className="analytics-local-session">
        <SectionHeading
          eyebrow="LOCAL SYNTHETIC SESSION HISTORY"
          title="Browser-session trends"
          action={
            <label className="analytics-range">
              <span>TIME WINDOW</span>
              <select aria-label="History window" value={windowMinutes} onChange={(event) => setWindowMinutes(event.target.value)}>
                <option value="5">Last 5 minutes</option>
                <option value="15">Last 15 minutes</option>
                <option value="all">All available samples</option>
              </select>
            </label>
          }
        />
      <div className="analytics-provenance">
        <span>GENERATED IN THIS BROWSER SESSION</span>
        <span>{samples.length} / {history.length} samples in range</span>
        <span>2-second sample interval · no persisted/backend history</span>
      </div>
      <div className="analytics-grid">
        <Card>{samples.length ? <TelemetryChart data={samples} metric="health_score" title="RULE-BASED HEALTH ESTIMATE · 0–100" color="#4ade80" height={300} status="SYNTHETIC" /> : <p className="analytics-empty">No samples are available in this time window.</p>}</Card>
        <Card>{samples.length ? <TelemetryChart data={samples} metric="rpm" title="ENGINE SPEED · RPM" color="#00e5ff" height={300} status="SYNTHETIC" /> : <p className="analytics-empty">No samples are available in this time window.</p>}</Card>
        <Card>{samples.length ? <TelemetryChart data={samples} metric="egt" title="EXHAUST GAS TEMPERATURE · °C" color="#ff9f43" height={300} status="SYNTHETIC" /> : <p className="analytics-empty">No samples are available in this time window.</p>}</Card>
        <Card className="fault-frequency-card">
          <div className="chart-wrap">
            <div className="chart-title">LOCAL RULE CLASSIFICATIONS <span>SYNTHETIC SAMPLE COUNT</span></div>
            {samples.length ? <ResponsiveContainer width="100%" height={300}>
              <BarChart data={faultFrequency} margin={{ top: 12, right: 12, bottom: 18, left: -12 }}>
                <CartesianGrid stroke="#ffffff0c" vertical={false} />
                <XAxis dataKey="fault" tick={{ fill: '#8998b2', fontSize: 9 }} angle={-12} textAnchor="end" axisLine={false} tickLine={false} />
                <YAxis allowDecimals={false} tick={{ fill: '#65718d', fontSize: 10 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ background: '#0d1428', border: '1px solid #ffffff1a', borderRadius: 10, color: '#fff' }} />
                <Bar dataKey="count" name="Samples" fill="#45d7aa" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer> : <p className="analytics-empty">No classification samples are available in this time window.</p>}
          </div>
          <p className="analytics-footnote">Health estimates and classifications are calculated from local synthetic samples. They are not backend analysis, stored flight records, or calibrated predictions.</p>
        </Card>
      </div>
      </section>
    </div>
  )
}
