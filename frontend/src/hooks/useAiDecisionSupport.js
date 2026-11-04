import { useCallback, useEffect, useRef, useState } from 'react'
import {
  getDecisionHistory,
  getPendingRecommendations,
  submitRecommendationDecision,
} from '../v2/api'

export function useAiDecisionSupport({ refreshMs = 10000 } = {}) {
  const [pending, setPending] = useState([])
  const [history, setHistory] = useState([])
  const [status, setStatus] = useState('loading')
  const [error, setError] = useState('')
  const [lastUpdated, setLastUpdated] = useState(null)
  const lastUpdatedRef = useRef(null)
  const [refreshVersion, setRefreshVersion] = useState(0)
  const retry = useCallback(() => setRefreshVersion(value => value + 1), [])

  useEffect(() => {
    let active = true
    const controller = new AbortController()
    async function refresh() {
      try {
        const [pendingResult, historyResult] = await Promise.all([
          getPendingRecommendations(controller.signal),
          getDecisionHistory(controller.signal),
        ])
        if (!active) return
        setPending(Array.isArray(pendingResult.recommendations) ? pendingResult.recommendations : [])
        setHistory(Array.isArray(historyResult.history) ? historyResult.history : [])
        const updatedAt = new Date().toISOString()
        lastUpdatedRef.current = updatedAt
        setLastUpdated(updatedAt)
        setStatus('ready')
        setError('')
      } catch (failure) {
        if (!active || failure.name === 'AbortError') return
        setStatus(lastUpdatedRef.current ? 'stale' : 'offline')
        setError(failure instanceof Error ? failure.message : 'Decision-support data unavailable.')
      }
    }
    refresh()
    const interval = refreshMs > 0 ? setInterval(refresh, refreshMs) : undefined
    return () => {
      active = false
      controller.abort()
      if (interval) clearInterval(interval)
    }
  }, [refreshMs, refreshVersion])

  const decide = useCallback(async (recommendationId, decision, operatorComment) => {
    const result = await submitRecommendationDecision(recommendationId, decision, operatorComment)
    setPending(current => current.filter(item => item.recommendation_id !== recommendationId))
    setHistory(current => [result, ...current.filter(item => item.recommendation_id !== recommendationId)])
    setRefreshVersion(value => value + 1)
    return result
  }, [])

  return { pending, history, status, error, lastUpdated, retry, decide }
}
