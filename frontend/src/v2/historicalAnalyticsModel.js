export const HISTORICAL_LIMIT = 3600
export const HISTORICAL_SENSORS = {
  rpm: { label: 'RPM', unit: 'rpm' },
  egt: { label: 'EGT', unit: '°C' },
  cht: { label: 'CHT', unit: '°C' },
  oil_temperature: { label: 'Oil temperature', unit: '°C' },
  oil_pressure: { label: 'Oil pressure', unit: 'bar' },
  fuel_flow: { label: 'Fuel flow', unit: 'L/h' },
  vibration: { label: 'Vibration', unit: 'mm/s RMS' },
}

const finite = value => typeof value === 'number' && Number.isFinite(value)

export function validTimestamp(value) {
  return typeof value === 'string' && Number.isFinite(Date.parse(value))
}

export function normalizeHistoricalResponse(response) {
  if (!response || typeof response !== 'object' || !Array.isArray(response.history)) return { valid: false, records: [], duplicatesExcluded: 0 }
  const seen = new Set()
  let duplicatesExcluded = 0
  const records = response.history.filter(row => {
    if (!row || row.sequence == null || !validTimestamp(row.timestamp) || typeof row.sensors !== 'object' || !row.sensors) return false
    if (seen.has(row.sequence)) { duplicatesExcluded += 1; return false }
    seen.add(row.sequence)
    return true
  }).map(row => ({
    sequence: row.sequence,
    timestamp: row.timestamp,
    sensors: { ...row.sensors },
    source: row.source ?? null,
    expected: row.expected ? { ...row.expected } : null,
  })).sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp) || Number(a.sequence) - Number(b.sequence))
  return { valid: true, records, duplicatesExcluded }
}

export function chartData(records, sensor) {
  return records.map(row => ({ timestamp: row.timestamp, sequence: row.sequence, value: finite(row.sensors[sensor]) ? row.sensors[sensor] : null }))
}

export function dataQuality(records, sensorKeys = Object.keys(HISTORICAL_SENSORS)) {
  let valid = 0; let missing = 0; let invalid = 0
  for (const row of records) for (const key of sensorKeys) {
    const value = row.sensors[key]
    if (value == null) missing += 1
    else if (finite(value)) { valid += 1 }
    else invalid += 1
  }
  return { totalRecords: records.length, valid, missing, invalid }
}

export function timeCoverage(records) {
  if (!records.length) return { start: null, end: null, durationSeconds: null }
  const start = records[0].timestamp
  const end = records[records.length - 1].timestamp
  return { start, end, durationSeconds: Math.max(0, (Date.parse(end) - Date.parse(start)) / 1000) }
}

export function normalizeFaultResponse(response) {
  if (!response || typeof response !== 'object' || !Array.isArray(response.fault_history)) return { valid: false, records: [] }
  return { valid: true, records: response.fault_history.filter(item => item && validTimestamp(item.timestamp)).map(item => ({ ...item, fault: item.fault && typeof item.fault === 'object' ? { ...item.fault } : null })) }
}

export function provenanceLabel(records) {
  const sources = [...new Set(records.map(row => row.source).filter(Boolean))]
  if (!sources.length) return 'PROVENANCE UNKNOWN'
  if (sources.every(source => source === 'simulation')) return 'SYNTHETIC / DEMONSTRATION DATA'
  return sources.join(', ')
}

export function trendUnavailable() {
  return { status: 'NOT AVAILABLE', reason: 'No read-only historical trend-analysis endpoint is exposed by the backend.' }
}
