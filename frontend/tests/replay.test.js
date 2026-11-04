import test from 'node:test'
import assert from 'node:assert/strict'
import { evaluationMatchesSource } from '../src/lib/replay.js'

test('offline evaluation requires matching source and session on every record', () => {
  const evaluation = { source_mode: 'OFFLINE_REPLAY', replay_session_id: 'one',
    recommendations: [{ source: 'OFFLINE_REPLAY', recommendation_details: { replay_session_id: 'one' } }] }
  assert.equal(evaluationMatchesSource(evaluation, 'OFFLINE_REPLAY', 'one'), true)
  assert.equal(evaluationMatchesSource(evaluation, 'OFFLINE_REPLAY', 'two'), false)
  assert.equal(evaluationMatchesSource(evaluation, 'LIVE_LAPTOP1'), false)
  evaluation.recommendations.push({ source: 'LAPTOP1_PROTOCOL1' })
  assert.equal(evaluationMatchesSource(evaluation, 'OFFLINE_REPLAY', 'one'), false)
})

test('live evaluation rejects replay contamination and incomplete responses', () => {
  const evaluation = { source_mode: 'LIVE_LAPTOP1', recommendations: [{ source: 'LAPTOP1_PROTOCOL1' }] }
  assert.equal(evaluationMatchesSource(evaluation, 'LIVE_LAPTOP1'), true)
  evaluation.recommendations.push({ source: 'OFFLINE_REPLAY' })
  assert.equal(evaluationMatchesSource(evaluation, 'LIVE_LAPTOP1'), false)
  for (const value of [null, {}, { recommendations: [] }, { source_mode: 'OFFLINE_REPLAY' }]) {
    assert.equal(evaluationMatchesSource(value, 'OFFLINE_REPLAY', 'one'), false)
  }
})
