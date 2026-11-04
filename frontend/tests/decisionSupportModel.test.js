import test from 'node:test'
import assert from 'node:assert/strict'
import { hasRecommendationId, normalizeDecisionHistory, normalizeRecommendationList, normalizeRecommendation, recommendationState } from '../src/v2/decisionSupportModel.js'

const record = (overrides = {}) => ({ recommendation_id: 'rec-1', source: 'test', aircraft_id: 'A1', mission_id: 'M1', scenario: 'urban', status: 'pending', created_at: '2026-01-01T00:00:00Z', recommendation_details: { title: 'Review', recommended_action: 'Inspect', severity: 'warning', reason: 'Evidence', evidence: { value: 0 }, provenance: { synthetic: true } }, ...overrides })

test('normalizes valid, empty and malformed recommendation responses', () => {
  assert.equal(normalizeRecommendationList({ recommendations: [record()] }).items[0].id, 'rec-1')
  assert.deepEqual(normalizeRecommendationList({ recommendations: [] }).items, [])
  assert.equal(normalizeRecommendationList({ recommendations: {} }).valid, false)
  assert.equal(normalizeRecommendation(null), null)
})

test('preserves missing fields, evidence, provenance and timestamps', () => {
  const item = normalizeRecommendation(record({ recommendation_id: undefined, created_at: 'bad', recommendation_details: { evidence: null } }))
  assert.equal(item.id, null); assert.equal(item.title, null); assert.equal(item.reason, null)
  assert.equal(item.createdAt.valid, false); assert.deepEqual(item.provenance, null); assert.equal(item.evidence, null)
})

test('known and unknown statuses and priorities remain distinct', () => {
  assert.equal(normalizeRecommendation(record()).statusKnown, true)
  assert.equal(normalizeRecommendation(record({ status: 'approved' })).statusKnown, true)
  assert.equal(normalizeRecommendation(record({ status: 'rejected' })).statusKnown, true)
  assert.equal(normalizeRecommendation(record({ status: 'unknown', recommendation_details: { severity: 'unknown' } })).statusKnown, false)
  assert.equal(normalizeRecommendation(record({ recommendation_details: { severity: 'unknown' } })).severityKnown, false)
})

test('history and state helpers preserve empty and unavailable states', () => {
  assert.deepEqual(normalizeDecisionHistory({ history: [] }).items, [])
  assert.equal(normalizeDecisionHistory({ history: null }).valid, false)
  assert.equal(recommendationState({ status: 'loading', hasData: false, error: '' }), 'LOADING')
  assert.equal(recommendationState({ status: 'ready', hasData: false, error: '' }), 'NO PENDING RECOMMENDATIONS')
  assert.equal(recommendationState({ status: 'offline', hasData: false, error: 'down' }), 'DECISION SUPPORT UNAVAILABLE')
  assert.equal(hasRecommendationId(normalizeRecommendation(record())), true)
  assert.equal(hasRecommendationId(normalizeRecommendation(record({ recommendation_id: null }))), false)
})

test('normalization does not create records or mutate input', () => {
  const source = record(); const copy = JSON.parse(JSON.stringify(source))
  normalizeRecommendationList({ recommendations: [source] })
  assert.deepEqual(source, copy)
})
