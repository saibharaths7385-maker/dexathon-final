import test from 'node:test'
import assert from 'node:assert/strict'
import { CHART_HISTORY_LIMIT, chartRows, measurementState, orderTelemetryHistory, streamFreshness } from '../src/v2/liveMonitoringModel.js'

const frame = (sequence, timestamp, sensors = {}) => ({ sequence, timestamp, sensors })

test('valid, missing, invalid and zero measurements remain distinct', () => {
  assert.deepEqual(measurementState(0), { state: 'VALID', value: 0 })
  assert.equal(measurementState(undefined).state, 'UNAVAILABLE')
  assert.equal(measurementState(Number.NaN).state, 'INVALID')
  assert.equal(chartRows([frame(1, '2026-01-01T00:00:00Z', { rpm: 0 })], 'rpm')[0].value, 0)
})

test('history is deduplicated, chronologically ordered and bounded', () => {
  const rows = [
    frame(2, '2026-01-01T00:00:02Z', { rpm: 2 }),
    frame(1, '2026-01-01T00:00:03Z', { rpm: 1 }),
    frame(2, '2026-01-01T00:00:02Z', { rpm: 99 }),
  ]
  const ordered = orderTelemetryHistory(rows, 2)
  assert.deepEqual(ordered.map(row => row.sequence), [2, 1])
  assert.equal(ordered[0].sensors.rpm, 2)
  assert.equal(orderTelemetryHistory(Array.from({ length: 200 }, (_, index) => frame(index, `2026-01-01T00:00:${String(index % 60).padStart(2, '0')}Z`))).length, CHART_HISTORY_LIMIT)
})

test('stream freshness distinguishes stale and disconnected states', () => {
  assert.equal(streamFreshness('streaming', { age_seconds: 1 }), 'FRESH')
  assert.equal(streamFreshness('streaming', { age_seconds: 8 }), 'STALE')
  assert.equal(streamFreshness('offline', {}), 'DISCONNECTED')
})
