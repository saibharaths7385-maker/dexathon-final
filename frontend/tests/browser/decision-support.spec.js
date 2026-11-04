import { expect, test } from '@playwright/test'

const api = 'http://127.0.0.1:8002/api/v2'
test.skip(process.env.PHM_PHASE3 !== '1', 'Run npm run test:phase3 with its isolated API and database.')

test('real local API: evaluate, approve, reject and reload history without aircraft commands', async ({ page, request }, testInfo) => {
  const writes = []
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('request', req => { if (req.method() === 'POST') writes.push(new URL(req.url()).pathname) })
  await page.goto('/live-mission')
  const review = page.getByRole('region', { name: 'Recommendation Review Centre' })
  const laptop = review.locator('.lm-review-card').filter({ hasText: 'LAPTOP1 PROTOCOL1' })
  await expect(laptop).toContainText('Telemetry quality')
  await expect(laptop).toContainText('missing')
  await expect(laptop).toContainText('protocol1.data_quality')
  await laptop.getByLabel(/Operator comment/).fill('No live source; restore the verified feed.')
  await laptop.getByRole('button', { name: 'Reject recommendation' }).click()
  await expect(laptop.locator('.lm-decision-status')).toHaveText('rejected')

  const twin = review.locator('.lm-review-card').filter({ hasText: 'SKYNEX V2 BUILT IN SIMULATION' })
  await expect(twin).toContainText('Routine condition inspection')
  await expect(twin).toContainText('rpm')
  await expect(twin).toContainText('demo envelope')
  await expect(twin).not.toContainText('Â°C')
  await twin.getByLabel(/Operator comment/).fill('Reviewed synthetic nominal evidence only.')
  await twin.getByRole('button', { name: 'Approve recommendation' }).click()
  await expect(twin.locator('.lm-decision-status')).toHaveText('approved')
  await page.reload()
  await expect(review.locator('.lm-history-row').filter({ hasText: 'Reviewed synthetic nominal evidence only.' })).toContainText('approved')
  await expect(review.locator('.lm-history-row').filter({ hasText: 'No live source; restore the verified feed.' })).toContainText('rejected')
  await twin.getByText(/Original recorded evidence/).click()
  await expect(twin).toContainText('Current evidence above does not amend a prior decision.')
  const history = await (await request.get(`${api}/decisions/history`)).json()
  const approved = history.history.find(record => record.status === 'approved')
  expect((await request.post(`${api}/recommendations/${approved.recommendation_id}/decision`, {
    data: { status: 'rejected', operator_comment: 'Duplicate attempt' },
  })).status()).toBe(409)
  expect(writes.every(path => path === '/api/v2/recommendations/evaluate' || /^\/api\/v2\/recommendations\/[^/]+\/decision$/.test(path))).toBe(true)
  expect(errors).toEqual([])
  await page.screenshot({ path: testInfo.outputPath('phase3-real-api.png'), fullPage: true })
})

test('source fault evidence, stale replacement, unavailable evaluation and recovery', async ({ page }) => {
  let mode = 'fault'
  const stamp = new Date().toISOString()
  const faultDetails = {
    category: 'Source-reported fault review', failure_mode: 'Source-reported fault review',
    severity: 'warning', recommended_action: 'Review the source fault against verified procedures.',
    reason: 'Source fault semantics remain unverified.', decision: 'OPERATOR REVIEW',
    rule_id: 'protocol1.source_faults', ruleset_version: 'scenario-advisory-3.0.0',
    sample_timestamp: stamp, phase: 'cruise',
    evidence: [{ key: 'faults', value: [{ code: 'TEST-FAULT', severity: 'critical' }] }],
    limitation: 'Scenario engineering limits remain unverified.',
  }
  const record = {
    recommendation_id: 'fault-review', source: 'LAPTOP1_PROTOCOL1', aircraft_id: 'TEST-AIRCRAFT',
    mission_id: 'TEST-MISSION', scenario: 'unverified-scenario', status: 'pending',
    created_at: stamp, decision_at: null, operator_comment: null,
    recommendation_details: faultDetails, current_details: faultDetails,
  }
  await page.route('**/api/v2/recommendations/evaluate', route => {
    if (mode === 'offline') return route.fulfill({ status: 503, json: { detail: 'Evaluation unavailable' } })
    const stale = { ...faultDetails, failure_mode: 'Telemetry quality', rule_id: 'protocol1.data_quality',
      reason: 'Source sample is stale; condition advice withheld.', evidence: [{ key: 'sample_age', value: 10, unit: 's' }] }
    return route.fulfill({ json: { advisory_only: true, recommendations: mode === 'fault' ? [record] : [
      { ...record, recommendation_id: 'stale-review', recommendation_details: stale, current_details: stale },
    ] } })
  })
  await page.route('**/api/v2/recommendations/pending*', route => route.fulfill({ json: { recommendations: [record] } }))
  await page.route('**/api/v2/decisions/history*', route => route.fulfill({ json: { history: [record] } }))
  await page.goto('/live-mission')
  const review = page.getByRole('region', { name: 'Recommendation Review Centre' })
  const cards = review.locator('.lm-review-list > .lm-review-card')
  await expect(cards).toContainText('TEST-FAULT')
  await expect(cards).toContainText('unverified-scenario')
  await expect(cards.locator('.lm-severity')).toHaveText('warning')
  mode = 'stale'
  await expect(cards).toContainText('condition advice withheld')
  await expect(cards).not.toContainText('TEST-FAULT')
  await expect(review.locator('.lm-history-row')).toContainText('Source-reported fault review')
  await review.getByText('Review earlier pending recommendations', { exact: true }).click()
  await expect(review.getByText('These are historical records, not current condition advice.', { exact: false })).toBeVisible()
  const historical = review.locator('details').filter({ has: page.getByText('Review earlier pending recommendations', { exact: true }) })
  await expect(historical.getByRole('button', { name: 'Approve recommendation' })).toBeEnabled()
  await review.getByText('Review earlier pending recommendations', { exact: true }).click()
  mode = 'offline'
  await expect(review.getByRole('alert')).toContainText('Evaluation unavailable')
  await expect(cards.getByRole('button', { name: 'Approve recommendation' })).toBeDisabled()
  mode = 'fault'
  await expect(cards).toContainText('TEST-FAULT')
  await expect(cards.getByRole('button', { name: 'Approve recommendation' })).toBeEnabled()
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
})
