import { useState } from 'react'
import { AlertTriangle, Check, ChevronDown, Clock3, History, ShieldCheck, X } from 'lucide-react'
import { useAiDecisionSupport } from '../hooks/useAiDecisionSupport'
import { hasRecommendationId, normalizeDecisionHistory, normalizeRecommendationList, recommendationState } from './decisionSupportModel'

const display = value => value == null || value === '' ? 'Not provided' : String(value)
const formatTime = item => item?.valid ? new Date(item.value).toISOString() : 'Not provided'

function Evidence({ details }) {
  return <div className="decision-evidence">
    <span>EXPLANATION</span><p>{display(details.reason)}</p>
    <span>SUPPORTING EVIDENCE</span><pre>{details.evidence == null ? 'Not provided' : JSON.stringify(details.evidence, null, 2)}</pre>
    <span>PROVENANCE / LIMITATIONS</span><pre>{details.provenance == null && details.limitation == null ? 'Not provided' : JSON.stringify({ provenance: details.provenance, limitation: details.limitation }, null, 2)}</pre>
  </div>
}

function RecommendationCard({ item, busyId, onDecide }) {
  const [comment, setComment] = useState('')
  const [expanded, setExpanded] = useState(false)
  const disabled = busyId === item.id || !hasRecommendationId(item)
  return <article className={`decision-card ${item.severityKnown ? item.severity : 'unknown'}`}>
    <div className="decision-card-head"><span className="decision-severity">{display(item.severity).toUpperCase()}</span><span className="decision-status">{display(item.status).toUpperCase()}</span></div>
    <h3>{display(item.title)}</h3>
    <div className="decision-identity"><span>RECOMMENDATION <b>{display(item.id)}</b></span><span>AIRCRAFT <b>{display(item.aircraftId)}</b></span><span>MISSION <b>{display(item.missionId)}</b></span><span>SCENARIO <b>{display(item.scenario)}</b></span></div>
    <p className="decision-action"><strong>RECOMMENDED ACTION</strong>{display(item.action)}</p>
    <details open={expanded} onToggle={event => setExpanded(event.currentTarget.open)}><summary><span>DETAILS & EVIDENCE</span><ChevronDown size={15}/></summary><Evidence details={item.details}/></details>
    {item.status === 'pending' && <div className="decision-actions"><input value={comment} onChange={event => setComment(event.target.value)} placeholder="Operator comment (required)" aria-label="Operator comment"/><button disabled={disabled || !comment.trim()} onClick={() => onDecide(item, 'approved', comment)}> <Check size={14}/> APPROVE</button><button disabled={disabled || !comment.trim()} onClick={() => onDecide(item, 'rejected', comment)}><X size={14}/> REJECT</button></div>}
    <footer><span>CREATED {formatTime(item.createdAt)}</span><span>DECIDED {formatTime(item.decisionAt)}</span></footer>
  </article>
}

function HistoryItem({ item }) {
  return <article className="decision-history-item"><span className={`decision-history-status ${item.status || 'unknown'}`}>{display(item.status).toUpperCase()}</span><div><b>{display(item.title)}</b><small>{display(item.id)} · {formatTime(item.decisionAt)}</small></div><p>{display(item.operatorComment)}</p></article>
}

export default function AiDecisionSupportCentre() {
  const { pending, history, status, error, retry, decide } = useAiDecisionSupport()
  const pendingResult = normalizeRecommendationList({ recommendations: pending })
  const historyResult = normalizeDecisionHistory({ history })
  const state = recommendationState({ status, hasData: pendingResult.items.length > 0, error })
  const [busyId, setBusyId] = useState(null)
  const [actionMessage, setActionMessage] = useState('')
  async function handleDecision(item, decision, comment) {
    if (!window.confirm(`Confirm ${decision.toUpperCase()} for recommendation ${item.id}?`)) return
    setBusyId(item.id); setActionMessage('')
    try { await decide(item.id, decision, comment); setActionMessage(`Backend confirmed ${decision} decision for ${item.id}.`) }
    catch (failure) { setActionMessage(failure instanceof Error ? failure.message : 'Decision request failed.') }
    finally { setBusyId(null) }
  }
  return <section className="ai-decision-centre" id="decision-support" aria-label="AI decision support centre">
    <header className="decision-heading"><div><span className="v-eyebrow"><ShieldCheck size={12}/> PHASE 7.5 · OPERATOR DECISION SUPPORT</span><h2>AI DECISION SUPPORT CENTRE</h2><p>Evidence-based maintenance recommendations and operator decision management.</p></div><div className={`decision-state ${state.toLowerCase().replaceAll(' ', '-')}`}><i/>{state}</div></header>
    {(error || actionMessage) && <div className={`decision-message ${error ? 'error' : 'success'}`} role={error ? 'alert' : 'status'}><AlertTriangle size={14}/>{actionMessage || error}{error && <button onClick={retry}>RETRY</button>}</div>}
    <div className="decision-layout"><div><div className="decision-section-title"><span className="v-eyebrow">PENDING RECOMMENDATIONS</span><b>{pendingResult.items.length}</b></div>{status === 'loading' ? <div className="decision-empty">LOADING</div> : pendingResult.items.length ? pendingResult.items.map(item => <RecommendationCard key={item.id || item.details.title} item={item} busyId={busyId} onDecide={handleDecision}/>) : <div className="decision-empty">{error ? 'DECISION SUPPORT UNAVAILABLE' : 'NO PENDING RECOMMENDATIONS'}</div>}</div>
      <aside className="decision-history"><div className="decision-section-title"><span className="v-eyebrow"><History size={12}/> DECISION HISTORY</span><b>{historyResult.items.length}</b></div>{historyResult.items.length ? historyResult.items.map((item, index) => <HistoryItem key={`${item.id || 'record'}-${index}`} item={item}/>) : <div className="decision-empty"><Clock3 size={15}/> NO DECISION HISTORY</div>}</aside></div>
  </section>
}
