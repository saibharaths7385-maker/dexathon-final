import test from 'node:test'
import assert from 'node:assert/strict'
import { assessmentSummary, connectionLabel, measurementState, provenanceLabel, SCENARIO_LABELS } from '../src/components/ai/healthOverviewModel.js'

test('maps live, stale, disconnected and connecting states', () => {
  assert.equal(connectionLabel('streaming', 'live'), 'LIVE')
  assert.equal(connectionLabel('polling', 'live'), 'LIVE')
  assert.equal(connectionLabel('streaming', 'stale'), 'STALE')
  assert.equal(connectionLabel('offline', 'waiting'), 'DISCONNECTED')
  assert.equal(connectionLabel('reconnecting', 'waiting'), 'CONNECTING')
})

test('keeps missing and invalid telemetry distinct', () => {
  assert.deepEqual(measurementState(undefined), { value: 'UNAVAILABLE', state: 'MISSING' })
  assert.deepEqual(measurementState(null), { value: 'UNAVAILABLE', state: 'MISSING' })
  assert.deepEqual(measurementState(Number.NaN), { value: 'INVALID', state: 'INVALID' })
  assert.deepEqual(measurementState(4800), { value: 4800, state: 'VALID' })
})

test('assessment remains explicitly unavailable and uncalibrated', () => {
  const summary = assessmentSummary()
  assert.equal(summary.status, 'ASSESSMENT NOT AVAILABLE')
  assert.equal(summary.score, null)
  assert.equal(summary.calibration, 'NOT_CALIBRATED')
  assert.equal(summary.warningCount, null)
})

test('unknown provenance is not presented as real telemetry', () => {
  assert.equal(provenanceLabel({}), 'UNCONFIRMED')
  assert.equal(provenanceLabel({ synthetic: true }), 'SYNTHETIC DEMONSTRATION')
})

test('scenario labels only use the approved environmental identifiers', () => {
  assert.deepEqual(Object.keys(SCENARIO_LABELS), ['urban', 'volcanic', 'desert', 'forest', 'snow_mountain'])
})
