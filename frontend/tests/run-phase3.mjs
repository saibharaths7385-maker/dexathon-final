import { spawnSync } from 'node:child_process'

const env = { ...process.env, VITE_API_BASE_URL: 'http://127.0.0.1:8002', PHM_PHASE3: '1' }
for (const args of [
  ['node_modules/vite/bin/vite.js', 'build', '--outDir', 'dist-phase3'],
  ['node_modules/@playwright/test/cli.js', 'test', '--config', 'playwright.phase3.config.js'],
]) {
  const result = spawnSync(process.execPath, args, { env, stdio: 'inherit' })
  if (result.error) throw result.error
  if (result.status !== 0) process.exit(result.status ?? 1)
}
