import { useEffect, useState } from 'react'
import { request } from '../v2/api'

export default function ScenarioReplay({ source, busy, error, onCommand }) {
  const [scenarios, setScenarios] = useState([])
  const [catalogueError, setCatalogueError] = useState('')
  const offline = source.mode === 'OFFLINE_REPLAY'
  const replay = source.replay
  useEffect(() => {
    const abort = new AbortController()
    request('/replay', undefined, AbortSignal.any([abort.signal, AbortSignal.timeout(12000)]))
      .then(data => setScenarios(data.scenarios))
      .catch(error => { if (error.name !== 'AbortError') setCatalogueError('Replay catalogue unavailable. Check the local backend.') })
    return () => abort.abort()
  }, [])

  const control = (action, args = {}) => onCommand('/replay/control', { action, ...args })
  return <section className="lm-panel lm-replay-panel" aria-label="Telemetry source">
    <div className="lm-section-header"><div>
      <span className="lm-eyebrow">ACTIVE TELEMETRY SOURCE</span>
      <h3>{offline ? 'Scenario Replay' : 'Live Laptop 1'}</h3>
    </div><span className="lm-section-detail">{offline ? 'Replay controls affect local fixture playback only.' : 'Read-only Protocol 1 telemetry; aircraft controls remain disabled.'}</span></div>
    <div className="lm-replay-controls">
      <label className="lm-control-field">Telemetry source
        <select value={source.mode || ''} disabled={busy} onChange={event => onCommand('/telemetry/source', { mode: event.target.value })}>
          <option value="" disabled>Waiting for backend</option>
          <option value="LIVE_LAPTOP1">LIVE_LAPTOP1 · read-only feed</option>
          <option value="OFFLINE_REPLAY">OFFLINE_REPLAY · synthetic fixtures</option>
        </select>
      </label>
      {offline && <label className="lm-control-field">Replay scenario
        <select value={replay?.scenario || 'normal'} disabled={busy || !offline || !scenarios.length}
          onChange={event => control('select', { scenario: event.target.value })}>
          {scenarios.map(scenario => <option key={scenario.id} value={scenario.id}>{scenario.label}</option>)}
        </select>
      </label>}
      {offline && <label className="lm-control-field">Replay speed
        <select value={replay?.speed || 1} disabled={busy || !offline}
          onChange={event => control('speed', { speed: Number(event.target.value) })}>
          {[0.25, 0.5, 1, 2, 4].map(speed => <option key={speed} value={speed}>{speed}×</option>)}
        </select>
      </label>}
      {offline && <div className="lm-replay-buttons">
        <button type="button" disabled={busy || !offline || replay?.state !== 'idle'} onClick={() => control('start')}>Start replay</button>
        <button type="button" disabled={busy || !offline || !['running', 'paused'].includes(replay?.state)}
          onClick={() => control(replay?.state === 'paused' ? 'resume' : 'pause')}>
          {replay?.state === 'paused' ? 'Resume replay' : 'Pause replay'}
        </button>
        <button type="button" disabled={busy || !offline} onClick={() => control('reset')}>Reset replay</button>
      </div>}
    </div>
    {(error || catalogueError) && <p className="lm-review-error" role="alert">{error || catalogueError}</p>}
    {offline ? <>
      <p className="lm-replay-banner">OFFLINE REPLAY / SYNTHETIC DATA — no live aircraft telemetry</p>
      <dl className="lm-review-meta">
        <div><dt>Replay status</dt><dd data-testid="replay-status">{replay?.state || 'unavailable'}</dd></div>
        <div><dt>Current scenario</dt><dd>{replay?.scenario || 'unavailable'}</dd></div>
        <div><dt>Replay time</dt><dd>{replay?.elapsed_seconds?.toFixed(1) ?? '—'} / {replay?.duration_seconds ?? '—'} s</dd></div>
        <div><dt>Telemetry freshness</dt><dd>{source.last_error || (source.status === 'connected' ? 'fresh on replay clock' : source.status)}</dd></div>
        <div><dt>Sample age</dt><dd>{replay?.sample_age_seconds == null ? 'unavailable' : `${replay.sample_age_seconds.toFixed(2)} replay s`}</dd></div>
        <div><dt>Frames accepted / rejected</dt><dd>{replay?.accepted_frames ?? 0} / {replay?.rejected_frames ?? 0}</dd></div>
      </dl>
      <p className="lm-muted">Session <span data-testid="replay-session">{replay?.session_id}</span><br />{replay?.provenance}</p>
      <p className="lm-muted">Fault-code semantics are unverified for Laptop 1. The V2 engine model is not fed by these Protocol 1 fixtures.</p>
    </> : <p className="lm-replay-banner">LIVE LAPTOP 1 / SIMULATED DEMO TELEMETRY — {source.status?.toUpperCase() || 'UNKNOWN'}{source.target ? ` · ${source.target}` : ''}</p>}
  </section>
}
