export const CHART_HISTORY_LIMIT = 180

export const SENSOR_DEFINITIONS = {
  rpm: { label: 'RPM', name: 'Engine speed', unit: 'rpm', group: 'speed' },
  egt: { label: 'EGT', name: 'Exhaust gas temperature', unit: '°C', group: 'temperature' },
  cht: { label: 'CHT', name: 'Cylinder head temperature', unit: '°C', group: 'temperature' },
  oil_temperature: { label: 'Oil temperature', name: 'Oil temperature', unit: '°C', group: 'temperature' },
  oil_pressure: { label: 'Oil pressure', name: 'Oil pressure', unit: 'bar', group: 'lubrication' },
  fuel_flow: { label: 'Fuel flow', name: 'Fuel flow', unit: 'L/h', group: 'fuel' },
  vibration: { label: 'Vibration', name: 'Vibration', unit: 'mm/s RMS', group: 'mechanical' },
}

export const sensorKeys = Object.keys(SENSOR_DEFINITIONS)

export function measurementState(value) {
  if (value == null) return { state: 'UNAVAILABLE', value: null }
  if (typeof value !== 'number' || !Number.isFinite(value)) return { state: 'INVALID', value: null }
  return { state: 'VALID', value }
}

export function orderTelemetryHistory(rows, limit = CHART_HISTORY_LIMIT) {
  const unique = new Map()
  for (const row of Array.isArray(rows) ? rows : []) {
    if (!row || row.sequence == null || !row.timestamp) continue
    if (!unique.has(row.sequence)) unique.set(row.sequence, row)
  }
  return [...unique.values()]
    .sort((a, b) => {
      const time = Date.parse(a.timestamp) - Date.parse(b.timestamp)
      return Number.isNaN(time) ? Number(a.sequence) - Number(b.sequence) : time || Number(a.sequence) - Number(b.sequence)
    })
    .slice(-limit)
}

export function chartRows(rows, key, limit = CHART_HISTORY_LIMIT) {
  return orderTelemetryHistory(rows, limit).map(row => ({
    timestamp: row.timestamp,
    sequence: row.sequence,
    value: measurementState(row.sensors?.[key]).value,
  }))
}

export function streamFreshness(connection, quality, now = Date.now()) {
  const age = quality?.age_seconds
  if (quality?.status === 'stale' || (typeof age === 'number' && age > 5)) return 'STALE'
  if (connection === 'offline') return 'DISCONNECTED'
  if (connection === 'reconnecting' || connection === 'connecting') return 'CONNECTING'
  if (typeof age === 'number') return 'FRESH'
  return 'UNKNOWN'
}
