// Do not render an evaluation from a different source/session after a switch.
export function evaluationMatchesSource(evaluation, mode, sessionId) {
  if (evaluation?.source_mode !== mode || !Array.isArray(evaluation.recommendations)) return false
  if (mode === 'OFFLINE_REPLAY') {
    return Boolean(sessionId) && evaluation.replay_session_id === sessionId
      && evaluation.recommendations.every(record => record.source === 'OFFLINE_REPLAY'
        && record.recommendation_details?.replay_session_id === sessionId)
  }
  return mode === 'LIVE_LAPTOP1' && evaluation.recommendations.every(record => record.source !== 'OFFLINE_REPLAY')
}
