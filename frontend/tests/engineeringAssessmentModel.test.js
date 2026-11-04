import test from 'node:test'
import assert from 'node:assert/strict'
import { assessmentState, normalizeAssessmentResponse, provenanceLabel, readingState } from '../src/v2/engineeringAssessmentModel.js'

const finding = (status, extra = {}) => ({ parameter: 'EGT', status, observed_value: 0, unit: '°C', ...extra })

test('normalizes a valid assessment and preserves evidence and provenance', () => {
  const result = normalizeAssessmentResponse({
    findings: [finding('WARNING', { evidence: { observed: 0 }, explanation: 'Rule evidence', rule_id: 'egt.rule' })],
    data_quality: { valid: 1, missing: 0, invalid: 0 }, provenance: { synthetic: true }, timestamp: '2026-01-01T00:00:00Z',
  })

  test('accepts the existing Phase 2 field names without inventing limits', () => {
    const result = normalizeAssessmentResponse({
      findings: [{ parameter: 'EGT', status: 'NORMAL', measurement: 12, threshold: 20 }],
      scenario_id: 'urban',
    })
    assert.equal(result.findings[0].observed.value, 12)
    assert.equal(result.findings[0].limit, 20)
    assert.equal(result.scenario, 'urban')
  })
  assert.equal(result.available, true)
  assert.equal(result.findings[0].statusKey, 'WARNING')
  assert.deepEqual(result.findings[0].evidence, { observed: 0 })
  assert.equal(provenanceLabel(result.provenance), 'SYNTHETIC / DEMO DATA')
})

test('missing, empty and malformed responses remain unavailable', () => {
  assert.equal(normalizeAssessmentResponse(null).state, 'MISSING')
  assert.equal(normalizeAssessmentResponse({}).state, 'EMPTY')
  assert.equal(normalizeAssessmentResponse({ findings: {} }).state, 'MALFORMED')
  assert.equal(assessmentState({ assessment: normalizeAssessmentResponse(null), connection: 'streaming' }), 'ASSESSMENT NOT AVAILABLE')
})

test('known statuses are counted without classifying unknown statuses as normal', () => {
  const result = normalizeAssessmentResponse({ findings: [finding('NORMAL'), finding('WARNING'), finding('CRITICAL'), finding('NOT_ASSESSED'), finding('vendor_status')] })
  assert.deepEqual(result.summary, { totalAssessed: 3, normal: 1, warning: 1, critical: 1, notAssessed: 1 })
  assert.equal(result.findings[4].status, 'vendor_status')
  assert.equal(result.findings[4].statusKey, null)
})

test('missing, invalid and zero measurements are distinct', () => {
  assert.deepEqual(readingState(undefined), { state: 'MISSING', value: null })
  assert.deepEqual(readingState(null), { state: 'MISSING', value: null })
  assert.deepEqual(readingState('bad'), { state: 'INVALID', value: null })
  assert.deepEqual(readingState(0), { state: 'VALID', value: 0 })
})

test('missing thresholds and fields are not fabricated', () => {
  const result = normalizeAssessmentResponse({ findings: [finding('NORMAL')] })
  assert.equal(result.findings[0].limit, null)
  assert.equal(result.findings[0].referenceRange, null)
  assert.equal(result.findings[0].ruleId, null)
  assert.equal(result.findings[0].explanation, null)
})

test('timestamp validation preserves original values', () => {
  const result = normalizeAssessmentResponse({ timestamp: 'not-a-date', findings: [finding('NORMAL', { timestamp: '2026-01-01T00:00:00Z' })] })
  assert.equal(result.timestamp.value, 'not-a-date')
  assert.equal(result.timestamp.valid, false)
  assert.equal(result.findings[0].timestamp.valid, true)
})

test('unknown provenance is explicit and stream states remain truthful', () => {
  const assessment = normalizeAssessmentResponse({ findings: [] })
  assert.equal(provenanceLabel(assessment.provenance), 'PROVENANCE UNKNOWN')
  assert.equal(assessmentState({ assessment, connection: 'offline' }), 'DISCONNECTED')
  assert.equal(assessmentState({ assessment, connection: 'reconnecting' }), 'CONNECTING')
  assert.equal(assessmentState({ assessment: normalizeAssessmentResponse({}), connection: 'streaming' }), 'INSUFFICIENT DATA')
})

test('normalization does not mutate the response', () => {
  const source = { findings: [finding('NORMAL', { evidence: { value: 0 } })] }
  const copy = JSON.parse(JSON.stringify(source))
  normalizeAssessmentResponse(source)
  assert.deepEqual(source, copy)
})
