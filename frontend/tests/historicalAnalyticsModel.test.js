import test from 'node:test'
import assert from 'node:assert/strict'
import { chartData, dataQuality, normalizeFaultResponse, normalizeHistoricalResponse, provenanceLabel, timeCoverage, trendUnavailable } from '../src/v2/historicalAnalyticsModel.js'

const row = (sequence, timestamp, sensors = { rpm: 0, egt: 1, cht: 2, oil_temperature: 3, oil_pressure: 4, fuel_flow: 5, vibration: 6 }) => ({ sequence, timestamp, sensors, source: 'simulation' })

test('normalizes valid history, preserves zero and sorts chronologically', () => {
  const result = normalizeHistoricalResponse({ history: [row(2, '2026-01-01T00:00:02Z'), row(1, '2026-01-01T00:00:01Z')] })
  assert.deepEqual(result.records.map(item => item.sequence), [1, 2])
  assert.equal(chartData(result.records, 'rpm')[0].value, 0)
})

test('handles empty, malformed and invalid timestamps', () => {
  assert.deepEqual(normalizeHistoricalResponse({ history: [] }).records, [])
  assert.equal(normalizeHistoricalResponse(null).valid, false)
  assert.equal(normalizeHistoricalResponse({ history: [{ sequence: 1, timestamp: 'bad', sensors: {} }] }).records.length, 0)
})

test('deduplicates sequence identifiers and isolates malformed records', () => {
  const result = normalizeHistoricalResponse({ history: [row(1, '2026-01-01T00:00:01Z'), row(1, '2026-01-01T00:00:02Z'), null] })
  assert.equal(result.records.length, 1)
  assert.equal(result.duplicatesExcluded, 1)
})

test('quality counts missing, invalid and valid values without replacing them', () => {
  const result = normalizeHistoricalResponse({ history: [row(1, '2026-01-01T00:00:01Z', { rpm: 0, egt: null, cht: 'bad' })] })
  assert.deepEqual(dataQuality(result.records, ['rpm', 'egt', 'cht']), { totalRecords: 1, valid: 1, missing: 1, invalid: 1 })
  assert.equal(chartData(result.records, 'egt')[0].value, null)
})

test('coverage and provenance are explicit', () => {
  const result = normalizeHistoricalResponse({ history: [row(1, '2026-01-01T00:00:01Z'), row(2, '2026-01-01T00:01:01Z')] })
  assert.equal(timeCoverage(result.records).durationSeconds, 60)
  assert.equal(provenanceLabel(result.records), 'SYNTHETIC / DEMONSTRATION DATA')
  assert.equal(provenanceLabel([]), 'PROVENANCE UNKNOWN')
})

test('fault history and unsupported predictive analysis remain truthful', () => {
  assert.equal(normalizeFaultResponse({ fault_history: [] }).valid, true)
  assert.equal(normalizeFaultResponse({}).valid, false)
  assert.equal(trendUnavailable().status, 'NOT AVAILABLE')
  assert.match(trendUnavailable().reason, /endpoint/)
})

test('normalization does not mutate source records', () => {
  const source = { history: [row(1, '2026-01-01T00:00:01Z')] }
  const copy = JSON.parse(JSON.stringify(source))
  normalizeHistoricalResponse(source)
  assert.deepEqual(source, copy)
})
