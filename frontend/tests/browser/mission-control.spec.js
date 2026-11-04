import { expect, test } from '@playwright/test'
import { analysis, history, makeReplay, samples } from '../fixtures/contracts.js'

async function mockMissionApi(page) {
  await page.route('**/api/v2/fleet', (route) => route.fulfill({
    json: {
      summary: {
        asset_count: 2,
        fleet_health: 86,
        fleet_readiness_score: 91,
        mission_available: 2,
        high_risk_assets: 0,
      },
      assets: [
        {
          engine_id: 'VAYU-01',
          sector: 'LEAD',
          callsign: 'MALE-01',
          coordinates: { x: 50, y: 50 },
          health_index: 94,
          reliability_percent: 98,
          rul_hours: 286,
          risk_percent: 2,
          readiness: 'ACTIVE',
        },
        {
          engine_id: 'VAYU-02',
          sector: 'NORTH',
          callsign: 'MALE-02',
          coordinates: { x: 50, y: 22 },
          health_index: 82,
          reliability_percent: 84,
          rul_hours: 174,
          risk_percent: 16,
          readiness: 'READY',
        },
      ],
    },
  }))
  await page.route('**/api/demo-flight', (route) => route.fulfill({ json: { telemetry: samples } }))
  await page.route('**/api/analyze', (route) => route.fulfill({ json: analysis }))
  await page.route('**/api/replay', (route) => route.fulfill({ json: makeReplay() }))
  await page.route('**/api/health-history', (route) => route.fulfill({ json: history }))
}

function mockTwinStream(page) {
  const snapshot = {
    engine_id: 'VAYU-01',
    sequence: 12,
    timestamp: new Date().toISOString(),
    source: 'simulation',
    sensors: {
      rpm: 4800,
      egt: 650,
      cht: 180,
      oil_temperature: 95,
      oil_pressure: 4.5,
      fuel_flow: 22,
      vibration: 1.8,
    },
    expected: { rpm: 4800, egt: 650, cht: 180, oil_temperature: 95, oil_pressure: 4.5, fuel_flow: 22, vibration: 1.8 },
    health_index: 94,
    hybrid: { fused_health: 93.5, method: 'Reduced-order digital twin + residual condition surrogate' },
    rul: { hours: 420, interval_kind: 'Sensitivity range; not a calibrated confidence interval.' },
    mission: { mission_id: 'MISSION-ALPHA', reliability_percent: 98, decision: 'WITHIN DEMO ENVELOPE' },
    controls: { scenario: 'nominal', mission: { mission_id: 'MISSION-ALPHA' } },
    quality: { status: 'live', age_seconds: 0 },
    maintenance: [{ priority: 'routine', failure_mode: 'Routine condition inspection' }],
    disclaimer: 'Synthetic research demonstrator. Not flight clearance.',
  }
  let reviewRecord = {
    recommendation_id: 'review-rec-1',
    source: 'SKYNEX_V2_BUILT_IN_SIMULATION',
    aircraft_id: 'VAYU-01',
    mission_id: 'MISSION-ALPHA',
    scenario: 'nominal',
    recommendation_details: {
      decision: 'WITHIN DEMO ENVELOPE',
      failure_mode: 'Routine condition inspection',
      severity: 'routine',
      reason: 'No monitored fault rule is currently active.',
      recommended_action: 'Continue scheduled inspection.',
      evidence: [],
    },
    status: 'pending',
    operator_comment: null,
    created_at: new Date().toISOString(),
    decision_at: null,
  }
  page.route('**/api/v2/twin', (route) => route.fulfill({ json: snapshot }))
  page.route('**/api/v2/history*', (route) => route.fulfill({ json: { history: [] } }))
  page.route('**/api/v2/telemetry/source', (route) => route.fulfill({
    json: { mode: 'LIVE_LAPTOP1', status: 'disconnected', latest_frame: null, last_received_at: null, last_error: null },
  }))
  page.route('**/api/v2/recommendations/evaluate', (route) => route.fulfill({
    json: { source_mode: 'LIVE_LAPTOP1', recommendations: [reviewRecord], advisory_only: true },
  }))
  page.route('**/api/v2/recommendations/pending*', (route) => route.fulfill({
    json: { recommendations: reviewRecord.status === 'pending' ? [reviewRecord] : [] },
  }))
  page.route('**/api/v2/decisions/history*', (route) => route.fulfill({
    json: { history: [reviewRecord] },
  }))
  page.route('**/api/v2/recommendations/*/decision', async (route) => {
    const submission = route.request().postDataJSON()
    reviewRecord = {
      ...reviewRecord,
      status: submission.status,
      operator_comment: submission.operator_comment,
      decision_at: new Date().toISOString(),
    }
    await route.fulfill({ json: reviewRecord })
  })
  page.routeWebSocket('**/api/v2/stream', (socket) => {
    socket.send(JSON.stringify(snapshot))
  })
  return {
    getReviewRecord: () => reviewRecord,
    setReviewRecord: (record) => { reviewRecord = record },
  }
}

test('mission operations pages render and link through the current command layout', async ({ page }) => {
  await mockMissionApi(page)
  await page.goto('/')

  await expect(page.getByRole('heading', { name: 'Mission overview' })).toBeVisible()
  await expect(page.getByRole('img', { name: /Health score \d+ out of 100/ })).toBeVisible()
  await expect(page.getByLabel(/Estimated remaining useful life: \d+(\.\d+)? hours/)).toBeVisible()
  await expect(page.getByRole('heading', { name: 'CONTINUE MISSION' })).toBeVisible()
  await expect(page.locator('.live-readout')).toHaveCount(6)

  await page.getByRole('link', { name: 'Telemetry', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Live Telemetry' })).toBeVisible()
  await expect(page.locator('.telemetry-grid .chart-card')).toHaveCount(6)
  const initialRpm = await page.locator('.telemetry-grid .chart-card header b').first().textContent()
  await expect.poll(
    () => page.locator('.telemetry-grid .chart-card header b').first().textContent(),
  ).not.toBe(initialRpm)

  await page.getByRole('link', { name: 'Fleet', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Fleet command center' })).toBeVisible()
  await expect(page.locator('.fleet-asset-table button')).toHaveCount(3)
  await expect(page.getByText(/last update/)).toBeVisible()
  const maintenanceAsset = page.locator('.fleet-asset-table button').filter({ hasText: 'VAYU-03' })
  await expect(maintenanceAsset).toContainText('67')
  await expect(maintenanceAsset).toContainText('MAINTENANCE REQUIRED')
  await page.getByRole('button', { name: /Select VAYU-02/ }).click()
  await expect(page.locator('.fleet-asset h3')).toContainText('VAYU-02')
  await expect(page.getByText('174 h RUL')).toBeVisible()

  await page.getByRole('link', { name: 'Digital Twin', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Digital twin', exact: true })).toBeVisible()
  await expect(page.locator('.twin-grid')).toBeVisible()
  await expect(page.locator('.twin-grid .twin-card')).toHaveCount(6)
  await expect(page.getByText('RESIDUAL ANALYSIS').first()).toBeVisible()

  await page.getByRole('link', { name: 'Replay', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Flight playback' })).toBeVisible()
  await expect(page.getByText(/FRAME 01 \/ \d+/)).toBeVisible()
  await expect(page.locator('.replay-chart-grid .chart-wrap')).toHaveCount(4)

  await page.getByRole('link', { name: 'Diagnosis', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Fault assessment' })).toBeVisible()
  await expect(page.getByText('RECOMMENDED ACTION')).toBeVisible()

  await page.getByRole('link', { name: 'Analytics', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Engine trends' })).toBeVisible()
  await expect(page.locator('.fault-frequency-card')).toBeVisible()
})

test('mission navigation and fleet panels remain usable on a narrow viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockMissionApi(page)
  await page.goto('/')
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.getByRole('button', { name: 'Open navigation' }).click()
  await page.getByRole('link', { name: 'Fleet', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Fleet command center' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)

  for (const [name, heading] of [
    ['Telemetry', 'Live Telemetry'],
    ['Digital Twin', 'Digital twin'],
    ['Replay', 'Flight playback'],
    ['Diagnosis', 'Fault assessment'],
    ['Analytics', 'Engine trends'],
  ]) {
    await page.getByRole('button', { name: 'Open navigation' }).click()
    await page.getByRole('link', { name, exact: true }).click()
    await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible()
    const documentWidth = await page.evaluate(() => document.documentElement.scrollWidth)
    expect(documentWidth, `${name} has horizontal overflow at mobile width`).toBeLessThanOrEqual(390)
  }
})

test('Live Mission is available from navigation and labels unintegrated simulator data honestly', async ({ page }, testInfo) => {
  await mockMissionApi(page)
  mockTwinStream(page)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await page.getByRole('button', { name: 'Open navigation' }).click()
  await page.getByRole('link', { name: 'Live Mission', exact: true }).click()

  await expect(page.getByRole('heading', { name: 'Live Mission', level: 2 })).toBeVisible()
  await expect(page.getByText('LIVE LAPTOP 1 · DISCONNECTED').first()).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Simulator view unavailable' })).toBeVisible()
  await expect(page.getByText('SKYNEX BUILT-IN SIMULATION')).toBeVisible()
  await expect(page.getByRole('region', { name: 'Laptop 1 propulsion telemetry' })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Flight telemetry' })).toContainText('Heading unavailable')
  await expect(page.getByRole('region', { name: 'Environment monitoring' })).toContainText('N/A')
  await expect(page.getByRole('region', { name: 'Environment monitoring' })).toContainText('FIELD · environment.temperature_c')
  await expect(page.getByRole('region', { name: 'Fault and alert centre' })).toContainText('Current fault status unavailable')
  await expect(page.locator('.lm-command-buttons button')).toHaveCount(5)
  for (const command of ['Start', 'Pause', 'Resume', 'Reset', 'Abort']) {
    await expect(page.getByRole('button', { name: command, exact: true })).toBeDisabled()
  }
  await expect(page.getByLabel('Throttle adjustment unavailable')).toBeDisabled()
  await expect(page.getByLabel('Scenario selection')).toBeDisabled()
  await expect(page.getByLabel('Simulated fault injection')).toBeDisabled()
  await expect(page.getByText('Validated AI prediction:')).toContainText('not available')
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)

  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.screenshot({ path: testInfo.outputPath('live-mission.png'), fullPage: true })
})

test('Live Mission displays normalized Laptop 1 telemetry with exact source labels', async ({ page }) => {
  await mockMissionApi(page)
  mockTwinStream(page)
  const frame = {
    protocol: 1,
    seq: 42,
    aircraft_id: 'EAGLE_EYE_MINI',
    mission_id: 'MISSION-DEMO',
    scenario: 'coastal',
    phase: 'cruise',
    timestamp: '2026-11-04T10:40:00Z',
    flight: {
      altitude_m: 1200,
      airspeed_ms: 42,
      airspeed_mps: 42,
      heading_deg: 85,
      pitch_deg: 3,
      roll_deg: -2,
      latitude: 12.9,
      longitude: 77.6,
    },
    propulsion: {
      engine_rpm: 4800,
      rpm: 4800,
      engine_temp_c: 190,
      temperature_c: 190,
      battery_voltage_v: 14.2,
      battery_voltage: 14.2,
      current_a: 12.3,
      fuel_pct: 74,
      fuel_percent: 74,
    },
    environment: {
      temperature_c: 28,
      humidity_pct: 55,
      humidity_percent: 55,
      wind_speed_ms: 5,
      wind_speed_mps: 5,
      wind_dir_deg: 220,
      wind_direction_deg: 220,
      turbulence: 0.2,
      visibility_m: 9000,
      dust: 0.1,
      dust_level: 0.1,
      ash: 0,
      ash_level: 0,
    },
    faults: [],
    mission: { progress: 0.6, wp_index: 3, current_waypoint: 3, waypoints: [{}, {}, {}, {}, {}, {}, {}, {}], total_waypoints: 8, time_s: 345, elapsed_seconds: 345, state: 'CRUISE' },
    normalization: {
      rpm_kind: 'engine',
      temperature_kind: 'engine',
      fields: {
        'flight.airspeed_mps': 'flight.airspeed_ms',
        'propulsion.rpm': 'propulsion.engine_rpm',
        'propulsion.temperature_c': 'propulsion.engine_temp_c',
        'propulsion.battery_voltage': 'propulsion.battery_voltage_v',
        'propulsion.current_a': 'propulsion.current_a',
        'propulsion.fuel_percent': 'propulsion.fuel_pct',
        'environment.humidity_percent': 'environment.humidity_pct',
        'environment.wind_speed_mps': 'environment.wind_speed_ms',
        'environment.wind_direction_deg': 'environment.wind_dir_deg',
        'environment.dust_level': 'environment.dust',
        'environment.ash_level': 'environment.ash',
        'mission.current_waypoint': 'mission.wp_index',
        'mission.total_waypoints': 'mission.waypoints.length',
        'mission.elapsed_seconds': 'mission.time_s',
      },
    },
  }
  await page.route('**/api/v2/telemetry/source', (route) => route.fulfill({
    json: { mode: 'LIVE_LAPTOP1', status: 'connected', latest_frame: frame, last_received_at: frame.timestamp, last_error: null },
  }))
  await page.goto('/live-mission')

  await expect(page.getByText('LIVE LAPTOP 1 · CONNECTED').first()).toBeVisible()
  await expect(page.getByText('EAGLE_EYE_MINI', { exact: true })).toBeVisible()
  await expect(page.getByText('MISSION-DEMO', { exact: true })).toBeVisible()
  await expect(page.getByText('cruise', { exact: true })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Laptop 1 propulsion telemetry' })).toContainText('4,800')
  await expect(page.getByRole('region', { name: 'Laptop 1 propulsion telemetry' })).toContainText('190.0')
  await expect(page.getByRole('region', { name: 'Laptop 1 propulsion telemetry' })).toContainText('Engine RPM')
  await expect(page.getByRole('region', { name: 'Laptop 1 propulsion telemetry' })).toContainText('Engine temperature')
  await expect(page.getByRole('region', { name: 'Laptop 1 propulsion telemetry' })).toContainText('engine_rpm')
  await expect(page.getByRole('region', { name: 'Laptop 1 propulsion telemetry' })).toContainText('engine_temp_c')
  await expect(page.getByRole('region', { name: 'Laptop 1 propulsion telemetry' })).toContainText('battery_voltage')
  await expect(page.getByRole('region', { name: 'Laptop 1 propulsion telemetry' })).toContainText('current_a')
  await expect(page.getByRole('region', { name: 'Laptop 1 propulsion telemetry' })).toContainText('fuel_pct')
  await expect(page.getByRole('region', { name: 'Laptop 1 propulsion telemetry' })).toContainText('14.20')
  await expect(page.getByRole('region', { name: 'Laptop 1 propulsion telemetry' })).toContainText('12.30')
  await expect(page.getByRole('region', { name: 'Laptop 1 propulsion telemetry' })).toContainText('74')
  await expect(page.getByRole('region', { name: 'Flight telemetry' })).toContainText('1,200.0')
  await expect(page.getByRole('region', { name: 'Flight telemetry' })).toContainText('42.0')
  await expect(page.getByRole('region', { name: 'Flight telemetry' })).toContainText('85.0')
  await expect(page.getByRole('region', { name: 'Environment monitoring' })).toContainText('220.0')
  await expect(page.getByRole('region', { name: 'Environment monitoring' })).toContainText('9,000.0 m')
  await expect(page.getByRole('region', { name: 'Fault and alert centre' })).toContainText('NO SOURCE-REPORTED FAULTS')
  await expect(page.getByRole('region', { name: 'Mission status' })).toContainText('60%')
  await expect(page.getByRole('region', { name: 'Mission status' })).toContainText('3 / 8')
  await expect(page.getByRole('region', { name: 'Mission status' })).toContainText('CRUISE')
  await expect(page.locator('.lm-protocol-card')).toHaveCount(0)
  const review = page.getByRole('region', { name: 'Recommendation Review Centre' })
  await expect(review).toContainText('SKYNEX V2 BUILT IN SIMULATION')
  await expect(review).toContainText('scenario engineering limits are unverified')
  await expect(review).toContainText('Routine condition inspection')
  await review.getByLabel(/Operator comment/).fill('Reviewed the available twin evidence.')
  const decisionRequest = page.waitForRequest((request) =>
    request.url().includes('/api/v2/recommendations/review-rec-1/decision')
  )
  await review.getByRole('button', { name: 'Approve recommendation' }).click()
  const request = await decisionRequest
  expect(request.method()).toBe('POST')
  expect(request.postDataJSON()).toEqual({
    status: 'approved',
    operator_comment: 'Reviewed the available twin evidence.',
  })
  await expect(review.getByRole('status')).toContainText('Recommendation approved')
  await expect(review.locator('.lm-history-row .lm-decision-status.approved')).toContainText('approved')
  await expect(review.locator('.lm-history-row')).toContainText('Reviewed the available twin evidence.')
  await expect(review.getByText('No pending recommendations for operator review.')).toBeVisible()
})

test('Live Mission updates the exact source fields and labels absent metrics N/A', async ({ page }) => {
  await mockMissionApi(page)
  mockTwinStream(page)
  let pollCount = 0
  await page.route('**/api/v2/telemetry/source', (route) => {
    pollCount += 1
    const frame = {
      protocol: 1,
      seq: pollCount,
      aircraft_id: 'EAGLE_EYE_MINI',
      mission_id: 'MISSION-DEMO',
      scenario: 'coastal',
      phase: 'cruise',
      timestamp: new Date().toISOString(),
      flight: {},
      propulsion: pollCount === 1 ? { rpm: 4800 } : { rpm: 4900 },
      environment: {},
      faults: null,
      mission: {},
    }
    return route.fulfill({
      json: {
        mode: 'LIVE_LAPTOP1',
        status: 'connected',
        latest_frame: frame,
        last_received_at: frame.timestamp,
        last_error: null,
      },
    })
  })
  await page.goto('/live-mission')

  const engine = page.getByRole('region', { name: 'Laptop 1 propulsion telemetry' })
  await expect(engine).toContainText('4,800')
  await expect(engine).toContainText('N/A')
  await expect(page.getByRole('region', { name: 'Flight telemetry' })).toContainText('N/A')
  await expect(page.getByRole('region', { name: 'Environment monitoring' })).toContainText('N/A')
  await expect(page.getByRole('region', { name: 'Mission status' })).toContainText('Last received')
  await expect(engine).toContainText('4,900')
  expect(pollCount).toBeGreaterThan(1)
})

test('Live Mission keeps RQ11B motor channels motor-specific', async ({ page }) => {
  await mockMissionApi(page)
  mockTwinStream(page)
  const frame = {
    protocol: 1,
    seq: 9,
    aircraft_id: 'RQ11B',
    mission_id: 'RQ11B-DEMO',
    scenario: 'patrol',
    phase: 'cruise',
    timestamp: new Date().toISOString(),
    flight: {},
    propulsion: { motor_rpm: 5100, rpm: 5100, motor_temp_c: 61, temperature_c: 61 },
    environment: {},
    faults: [],
    mission: {},
    normalization: {
      rpm_kind: 'motor',
      temperature_kind: 'motor',
      fields: {
        'propulsion.rpm': 'propulsion.motor_rpm',
        'propulsion.temperature_c': 'propulsion.motor_temp_c',
      },
    },
  }
  await page.route('**/api/v2/telemetry/source', (route) => route.fulfill({
    json: { mode: 'LIVE_LAPTOP1', status: 'connected', latest_frame: frame, last_received_at: frame.timestamp, last_error: null },
  }))
  await page.goto('/live-mission')

  const propulsion = page.getByRole('region', { name: 'Laptop 1 propulsion telemetry' })
  await expect(propulsion).toContainText('Motor RPM')
  await expect(propulsion).toContainText('Motor temperature')
  await expect(propulsion).toContainText('propulsion.motor_rpm')
  await expect(propulsion).toContainText('propulsion.motor_temp_c')
  await expect(propulsion).not.toContainText('Engine RPM')
})

test('Live Mission requires a comment and reports duplicate decisions clearly', async ({ page }) => {
  await mockMissionApi(page)
  mockTwinStream(page)
  await page.route('**/api/v2/recommendations/review-rec-1/decision', (route) =>
    route.fulfill({
      status: 409,
      json: { detail: 'Recommendation has already been decided.' },
    })
  )
  await page.goto('/live-mission')

  const review = page.getByRole('region', { name: 'Recommendation Review Centre' })
  await review.getByRole('button', { name: 'Approve recommendation' }).click()
  await expect(review.getByRole('alert')).toContainText(
    'Enter an operator comment before approving or rejecting.'
  )
  await expect(review.getByRole('button', { name: 'Approve recommendation' })).toBeEnabled()

  await review.getByLabel(/Operator comment/).fill('Already reviewed.')
  await review.getByRole('button', { name: 'Approve recommendation' }).click()
  await expect(review.getByRole('alert')).toContainText(
    'Recommendation has already been decided.'
  )
})

test('Live Mission records rejection and disables repeat submissions while saving', async ({ page }) => {
  await mockMissionApi(page)
  const mock = mockTwinStream(page)
  let submissionCount = 0
  await page.route('**/api/v2/recommendations/review-rec-1/decision', async (route) => {
    submissionCount += 1
    const submission = route.request().postDataJSON()
    await page.waitForTimeout(250)
    const record = {
      ...mock.getReviewRecord(),
      status: submission.status,
      operator_comment: submission.operator_comment,
      decision_at: new Date().toISOString(),
    }
    mock.setReviewRecord(record)
    await route.fulfill({ json: record })
  })
  await page.goto('/live-mission')

  const review = page.getByRole('region', { name: 'Recommendation Review Centre' })
  await review.getByLabel(/Operator comment/).fill('Reject pending maintenance evidence.')
  const reject = review.locator('.lm-reject')
  await reject.click()
  await expect(reject).toBeDisabled()
  await expect(review.getByRole('button', { name: 'Submitting rejection…' })).toBeVisible()
  await expect(review.locator('.lm-history-row .lm-decision-status.rejected')).toContainText('rejected')
  await expect(review.locator('.lm-history-row')).toContainText(
    'Reject pending maintenance evidence.'
  )
  expect(submissionCount).toBe(1)
  await expect(review.getByText('No pending recommendations for operator review.')).toBeVisible()
})

test('Live Mission reports source fault fields without fabricating severity', async ({ page }) => {
  await mockMissionApi(page)
  mockTwinStream(page)
  await page.route('**/api/v2/telemetry/source', (route) => route.fulfill({
    json: {
      mode: 'LIVE_LAPTOP1',
      status: 'connected',
      latest_frame: {
        protocol: 1,
        seq: 43,
        aircraft_id: 'EAGLE_EYE_MINI',
        mission_id: 'MISSION-DEMO',
        scenario: 'coastal',
        phase: 'cruise',
        timestamp: '2026-11-04T10:40:01Z',
        flight: {},
        propulsion: {},
        environment: {},
        faults: [{ code: 'GNSS DEGRADED', description: 'GNSS accuracy degraded.' }],
        mission: {},
      },
      last_received_at: '2026-11-04T10:40:01Z',
      last_error: null,
    },
  }))
  await page.goto('/live-mission')

  const alerts = page.getByRole('region', { name: 'Fault and alert centre' })
  await expect(alerts).toContainText('GNSS DEGRADED')
  await expect(alerts).toContainText('GNSS accuracy degraded.')
  await expect(alerts).toContainText('Severity unavailable')
  await expect(alerts).toContainText('Laptop 1 · Protocol 1')
  await expect(alerts).toContainText('2026')
})

test('live fault injection updates health, mission decision, and diagnosis', async ({ page }) => {
  await mockMissionApi(page)
  await page.goto('/')
  const healthValue = page.locator('.metric-card').filter({ hasText: 'HEALTH SCORE' }).locator('strong')
  const nominalHealth = await healthValue.textContent()

  await page.getByRole('button', { name: 'Inject engine degradation' }).click()
  await expect.poll(() => healthValue.textContent()).not.toBe(nominalHealth)
  await expect(page.getByRole('heading', { name: 'RETURN TO BASE' })).toBeVisible()

  await page.getByRole('link', { name: 'Diagnosis', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'ENGINE DEGRADATION' })).toBeVisible()
  await expect(page.getByText(/RECOMMENDED ACTION · RETURN TO BASE/)).toBeVisible()
})
