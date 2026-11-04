import { defineConfig } from '@playwright/test'

// Isolated API/database: never use the developer's running server or twin.sqlite3.
export default defineConfig({
  testDir: './tests/browser',
  testMatch: ['mission-control.spec.js', 'decision-support.spec.js'],
  timeout: 45000,
  expect: { timeout: 10000 },
  workers: 1,
  reporter: [['list'], ['json', { outputFile: 'test-results/phase3-results.json' }]],
  use: { baseURL: 'http://localhost:4175', channel: 'msedge', headless: true,
    screenshot: 'only-on-failure', trace: 'retain-on-failure' },
  webServer: [
    {
      command: '"../.venv/Scripts/python.exe" -m uvicorn backend.api.main:app --app-dir .. --host 127.0.0.1 --port 8002',
      url: 'http://127.0.0.1:8002/api/v2/health',
      reuseExistingServer: false,
      env: { TWIN_DATABASE: ':memory:', LAPTOP1_TELEMETRY_WS_URL: '', TWIN_ALLOWED_ORIGINS: 'http://localhost:4175' },
    },
    {
      command: 'npm run preview -- --host localhost --port 4175 --strictPort --outDir dist-phase3',
      url: 'http://localhost:4175',
      reuseExistingServer: false,
    },
  ],
})
