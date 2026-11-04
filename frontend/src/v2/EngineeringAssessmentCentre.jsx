import { AlertTriangle, ChevronDown, ClipboardCheck, Database, Radio } from 'lucide-react'
import { assessmentState, normalizeAssessmentResponse, provenanceLabel } from './engineeringAssessmentModel'

const formatValue = (reading, unit) => reading?.state === 'VALID'
  ? `${reading.value}${unit ? ` ${unit}` : ''}`
  : reading?.state === 'INVALID' ? 'INVALID' : 'Not provided'

function SummaryCard({ label, value }) {
  return <article className="assessment-summary-card"><span>{label}</span><strong>{value}</strong></article>
}

function Finding({ finding, index }) {
  return <details className={`assessment-finding ${finding.statusKey?.toLowerCase() || 'unknown'}`}>
    <summary><span className="assessment-finding-status">{finding.statusKey || finding.status || 'STATUS NOT PROVIDED'}</span><b>{finding.parameter || 'Parameter not provided'}</b><ChevronDown size={15}/></summary>
    <div className="assessment-finding-body">
      <div className="assessment-finding-grid">
        <span>OBSERVED <b>{formatValue(finding.observed, finding.unit)}</b></span>
        <span>LIMIT / RANGE <b>{finding.limit ?? finding.referenceRange ?? 'Not provided'}</b></span>
        <span>RULE ID <b>{finding.ruleId ?? 'Not provided'}</b></span>
        <span>TIMESTAMP <b>{finding.timestamp.value && finding.timestamp.valid ? new Date(finding.timestamp.value).toISOString() : 'Not provided'}</b></span>
      </div>
      <div className="assessment-evidence"><span>EXPLANATION</span><p>{finding.explanation || 'Not provided'}</p><span>EVIDENCE</span><pre>{finding.evidence == null ? 'Not provided' : JSON.stringify(finding.evidence, null, 2)}</pre></div>
      {!finding.statusKey && <p className="assessment-unknown">Finding {index + 1} has an unrecognized backend status; it is not classified as normal.</p>}
    </div>
  </details>
}

export default function EngineeringAssessmentCentre({ data, connection, assessment: rawAssessment }) {
  const assessment = normalizeAssessmentResponse(rawAssessment ?? data?.engineering_assessment)
  const state = assessmentState({ assessment, connection })
  const summary = assessment.summary
  const quality = assessment.quality
  const provenance = provenanceLabel(assessment.provenance)
  const unavailable = state === 'ASSESSMENT NOT AVAILABLE'
  return <section className="engineering-assessment-centre" id="engineering-assessment" aria-label="Engineering assessment centre">
    <header className="assessment-heading"><div><span className="v-eyebrow"><ClipboardCheck size={12}/> ENGINEERING ASSESSMENT</span><h2>ENGINEERING ASSESSMENT CENTRE</h2><p>Explainable engineering-rule assessment of available engine telemetry.</p></div><div className={`assessment-state ${state.toLowerCase().replaceAll(' ', '-')}`}><i/>{state}</div></header>
    {unavailable ? <div className="assessment-unavailable"><AlertTriangle size={20}/><strong>ASSESSMENT NOT AVAILABLE</strong><p>Engineering assessment results are not currently exposed through the available API.</p></div> : <>
      <div className="assessment-summary-grid">
        <SummaryCard label="TOTAL ASSESSED" value={summary.totalAssessed}/><SummaryCard label="NORMAL" value={summary.normal}/><SummaryCard label="WARNING" value={summary.warning}/><SummaryCard label="CRITICAL" value={summary.critical}/><SummaryCard label="NOT ASSESSED" value={summary.notAssessed}/>
      </div>
      <div className="assessment-quality"><span><Database size={14}/> VALID READINGS <b>{quality?.valid ?? 'Not provided'}</b></span><span>MISSING <b>{quality?.missing ?? 'Not provided'}</b></span><span>INVALID <b>{quality?.invalid ?? 'Not provided'}</b></span><span>UNAVAILABLE FIELDS <b>{quality?.unavailable ?? 'Not provided'}</b></span></div>
      <div className="assessment-provenance"><span>SOURCE <b>{assessment.source || 'Not provided'}</b></span><span>AIRCRAFT <b>{assessment.aircraftId || 'Not provided'}</b></span><span>MISSION <b>{assessment.missionId || 'Not provided'}</b></span><span>SCENARIO <b>{assessment.scenario || 'Not provided'}</b></span><span>PROVENANCE <b>{provenance}</b></span><span>TIMESTAMP <b>{assessment.timestamp.valid ? new Date(assessment.timestamp.value).toISOString() : 'Not provided'}</b></span></div>
      <div className="assessment-findings"><div className="assessment-section-title"><span className="v-eyebrow">BACKEND FINDINGS</span><b>{assessment.findings.length} supplied</b></div>{assessment.findings.length ? assessment.findings.map((finding, index) => <Finding key={index} finding={finding} index={index}/>) : <div className="assessment-empty"><Radio size={17}/> NO FINDINGS SUPPLIED</div>}</div>
    </>}
  </section>
}
