import { ShieldAlert, Wrench } from 'lucide-react'
import { Card, SectionHeading, StatusBadge } from '../components'
import { useMission } from '../hooks/useMission'
import { faultTone } from '../lib/status'

const diagnoses = {
  HEALTHY: {
    label: 'NO ACTIVE FAULT',
    action: 'Continue mission and maintain routine telemetry monitoring.',
  },
  COOLING_ISSUE: {
    label: 'COOLING ISSUE',
    action: 'Reduce power and inspect cooling airflow and cylinder head temperatures.',
  },
  ENGINE_DEGRADATION: {
    label: 'ENGINE DEGRADATION',
    action: 'Return to base and inspect engine performance and fuel consumption.',
  },
  BEARING_WEAR: {
    label: 'BEARING WEAR',
    action: 'Reduce power and arrange an inspection of bearings and rotating assemblies.',
  },
  SENSOR_FAULT: {
    label: 'SENSOR FAULT',
    action: 'Cross-check the affected sensor with an independent measurement before action.',
  },
}

export default function Diagnosis() {
  const mission = useMission()
  const diagnosis = diagnoses[mission.faultClassification]
  const classification = diagnosis ? mission.faultClassification : 'NOT_ASSESSED'
  const label = diagnosis?.label || 'NOT ASSESSED'
  const unavailable = (value) => Number.isFinite(value) ? value : 'Unavailable'

  return (
    <>
      <SectionHeading
        eyebrow="LOCAL SYNTHETIC RULE-BASED CLASSIFIER"
        title="Engineering assessment"
        action={<StatusBadge tone={faultTone(classification)}>{classification.replaceAll('_', ' ')}</StatusBadge>}
      />
      <div className="diagnosis-grid">
        <Card className="fault-hero">
          <ShieldAlert size={34} aria-hidden="true" />
          <span className="eyebrow">CURRENT LOCAL CLASSIFICATION</span>
          <h3>{label}</h3>
          <StatusBadge tone={faultTone(classification)}>
            {classification.replaceAll('_', ' ')}
          </StatusBadge>
          <p>
            Synthetic sample: {unavailable(mission.latest?.rpm)} RPM · EGT {unavailable(mission.latest?.egt)}°C ·
            CHT {unavailable(mission.latest?.cht)}°C · Fuel {unavailable(mission.latest?.fuel_flow)} L/h ·
            Vibration {unavailable(mission.latest?.vibration)} g.
          </p>
        </Card>
        <Card className="diagnosis-detail">
          <SectionHeading eyebrow="ASSESSMENT EVIDENCE" title="Rule classification and response" />
          <div className="diagnosis-evidence">
            <span>CLASSIFIER SOURCE</span><strong>LOCAL SYNTHETIC RULES</strong>
            <span>ASSESSMENT STATE</span><strong>{diagnosis ? 'CLASSIFIED' : 'NOT ASSESSED'}</strong>
            <span>CONFIDENCE</span><strong>NOT PROVIDED</strong>
          </div>
          <div className="diagnosis-action">
            <Wrench size={18} aria-hidden="true" />
            <div>
              <span>{diagnosis ? `LOCAL DEMONSTRATOR OUTPUT · ${mission.recommendedAction}` : 'NO ASSESSMENT AVAILABLE'}</span>
              <p>{diagnosis?.action || 'A local classification is not available for the current state.'}</p>
            </div>
          </div>
          <p className="analytics-footnote">
            Synthetic browser-session data and rule labels are not calibrated engineering findings, probability estimates, or flight-clearance decisions.
          </p>
        </Card>
      </div>
    </>
  )
}
