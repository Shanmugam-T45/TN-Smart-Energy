export const PUBLIC_DEMO_MODE = import.meta.env.VITE_PUBLIC_DEMO_MODE === 'true'
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? (
  import.meta.env.PROD ? '' : 'http://127.0.0.1:8000'
)

export interface DatasetMetadata {
  id: number
  filename: string
  uploaded_at: string
  accepted_rows: number
  rejected_rows: number
}

export interface DatasetSummary extends DatasetMetadata {
  record_count: number
  meter_count: number
  feeder_count: number
  transformer_count: number
  total_energy_kwh: number
  current_demand_kw: number | null
  maximum_demand_kw: number | null
  maximum_transformer_loading_percent: number | null
  average_demand_kw: number | null
  low_voltage_reading_count: number
  low_voltage_threshold_v: number
  demand_series: Array<{ timestamp: string; demand_kw: number }>
  consumption_series: Array<{ date: string; energy_kwh: number }>
}

export interface DatasetUploadResult extends DatasetMetadata {
  errors: Array<{ row: number; reason: string }>
}

export interface MeterSummary {
  meter_id: string
  record_count: number
  total_energy_kwh: number
  latest_timestamp: string
  latest_active_power_kw: number | null
  latest_voltage: number | null
  sanctioned_load_kw: number | null
  consumer_category: string | null
  locality: string | null
  alert_status: string
}

export interface MeterReading {
  timestamp: string
  energy_kwh: number
  voltage: number | null
  current_a: number | null
  active_power_kw: number | null
  power_factor: number | null
}

export interface MeterDetail {
  dataset_id: number
  meter_id: string
  profile: {
    meter_id: string
    sanctioned_load_kw: number | null
    consumer_category: string | null
    locality: string | null
    updated_at: string
  } | null
  readings: MeterReading[]
}

export interface TransformerSummary {
  transformer_id: string
  feeder_id: string | null
  location: string | null
  rated_capacity_kva: number | null
  high_loading_threshold_percent: number
  exceedance_threshold_percent: number
  latest_timestamp: string
  meter_count: number
  measured_active_power_kw: number | null
  measured_apparent_power_kva: number | null
  loading_percent: number | null
  status: string
  recommendation: string
}

export interface DemandForecast {
  dataset_id: number
  status: 'forecast_available' | 'insufficient_history'
  minimum_observations?: number
  training_observations: number
  horizon_hours?: number
  model?: string
  last_observed_timestamp?: string
  validation_mae_kw?: number | null
  validation_method?: string | null
  forecast: Array<{
    timestamp: string
    demand_kw: number
    lower_bound_kw: number
    upper_bound_kw: number
  }>
  limitation: string
}

export interface ConservationResult {
  original_peak_kw: number
  shiftable_load_kw: number
  new_estimated_peak_kw: number
  peak_reduction_percent: number
  kwh_energy_savings: number | null
  interpretation: string
  data_source: string
}

export interface VoltageAnalysis {
  dataset_id: number
  voltage_reading_count: number
  average_voltage: number | null
  minimum_voltage: number | null
  maximum_voltage: number | null
  low_voltage_count: number
  high_voltage_count: number
  within_screen_count: number
  low_threshold_v: number
  high_threshold_v: number
  feeders: Array<{
    feeder_id: string
    reading_count: number
    average_voltage: number
    minimum_voltage: number
    maximum_voltage: number
    low_voltage_count: number
    high_voltage_count: number
  }>
  limitation: string
}

export interface OutageEvent {
  id: number
  dataset_id: number
  feeder_id: string
  started_at: string
  ended_at: string | null
  cause: string
  notes: string | null
  created_at: string
  duration_minutes: number
  is_ongoing: boolean
}

export interface OutageAnalysis {
  dataset_id: number
  event_count: number
  ongoing_count: number
  total_duration_minutes: number
  source: 'manually_logged'
  events: OutageEvent[]
  limitation: string
}

export interface FeederLossSummary {
  feeder_id: string
  meter_ids: string[]
  input_meter_id: string | null
  output_meter_ids: string[]
  analysis_ready: boolean
  input_energy_kwh: number | null
  output_energy_kwh: number | null
  energy_discrepancy_kwh: number | null
  discrepancy_percent: number | null
}

export interface LossAnalysis {
  dataset_id: number
  feeders: FeederLossSummary[]
  source: string
  limitation: string
}

async function readResponse<T>(response: Response): Promise<T> {
  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const detail =
      typeof body === 'object' && body !== null && 'detail' in body
        ? (body as { detail: unknown }).detail
        : null
    throw new Error(describeError(detail) || `Request failed (${response.status})`)
  }
  return body as T
}

function describeError(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (typeof detail === 'object' && detail !== null) {
    const item = detail as { message?: unknown; errors?: unknown }
    const message = typeof item.message === 'string' ? item.message : ''
    const errors = Array.isArray(item.errors)
      ? item.errors
          .slice(0, 5)
          .map((error) => {
            if (typeof error !== 'object' || error === null) return String(error)
            const row = error as { row?: unknown; reason?: unknown }
            return `Row ${String(row.row)}: ${String(row.reason)}`
          })
          .join('; ')
      : ''
    return [message, errors].filter(Boolean).join(' ')
  }
  return ''
}

export async function listDatasets(): Promise<DatasetMetadata[]> {
  const response = await fetch(`${API_BASE_URL}/api/datasets`)
  return readResponse<DatasetMetadata[]>(response)
}

export async function uploadDataset(file: File): Promise<DatasetUploadResult> {
  const form = new FormData()
  form.append('file', file)
  const response = await fetch(`${API_BASE_URL}/api/datasets/upload`, {
    method: 'POST',
    body: form,
  })
  return readResponse<DatasetUploadResult>(response)
}

export async function getDatasetSummary(id: number): Promise<DatasetSummary> {
  const response = await fetch(`${API_BASE_URL}/api/datasets/${id}/summary`)
  return readResponse<DatasetSummary>(response)
}

export async function listDatasetMeters(id: number): Promise<MeterSummary[]> {
  const response = await fetch(`${API_BASE_URL}/api/datasets/${id}/meters`)
  const result = await readResponse<{ meters: MeterSummary[] }>(response)
  return result.meters
}

export async function getDatasetMeter(id: number, meterId: string): Promise<MeterDetail> {
  const response = await fetch(
    `${API_BASE_URL}/api/datasets/${id}/meters/${encodeURIComponent(meterId)}`,
  )
  return readResponse<MeterDetail>(response)
}

export async function saveMeterProfile(
  meterId: string,
  profile: { sanctioned_load_kw: number; consumer_category: string | null; locality: string | null },
): Promise<MeterDetail['profile']> {
  const response = await fetch(
    `${API_BASE_URL}/api/meters/${encodeURIComponent(meterId)}/profile`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(profile),
    },
  )
  return readResponse<MeterDetail['profile']>(response)
}

export async function listDatasetTransformers(id: number): Promise<TransformerSummary[]> {
  const response = await fetch(`${API_BASE_URL}/api/datasets/${id}/transformers`)
  const result = await readResponse<{ transformers: TransformerSummary[] }>(response)
  return result.transformers
}

export async function saveTransformerProfile(
  transformerId: string,
  profile: {
    rated_capacity_kva: number
    feeder_id: string | null
    location: string | null
    high_loading_threshold_percent: number
    exceedance_threshold_percent: number
  },
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/api/transformers/${encodeURIComponent(transformerId)}/profile`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(profile),
    },
  )
  await readResponse<unknown>(response)
}

export async function getDemandForecast(id: number, horizon: number): Promise<DemandForecast> {
  const response = await fetch(`${API_BASE_URL}/api/datasets/${id}/forecast?horizon=${horizon}`)
  return readResponse<DemandForecast>(response)
}

export async function runConservationScenario(input: {
  original_peak_kw: number
  shiftable_load_kw: number
  actual_reduction_kwh: number | null
}): Promise<ConservationResult> {
  const response = await fetch(`${API_BASE_URL}/api/analysis/conservation`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  return readResponse<ConservationResult>(response)
}

export async function getVoltageAnalysis(id: number): Promise<VoltageAnalysis> {
  const response = await fetch(`${API_BASE_URL}/api/datasets/${id}/voltage-analysis`)
  return readResponse<VoltageAnalysis>(response)
}

export async function getOutageAnalysis(id: number): Promise<OutageAnalysis> {
  const response = await fetch(`${API_BASE_URL}/api/datasets/${id}/outages`)
  return readResponse<OutageAnalysis>(response)
}

export async function createOutageEvent(
  datasetId: number,
  input: {
    feeder_id: string
    started_at: string
    ended_at: string | null
    cause: string
    notes: string | null
  },
): Promise<OutageEvent> {
  const response = await fetch(`${API_BASE_URL}/api/datasets/${datasetId}/outages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  return readResponse<OutageEvent>(response)
}

export async function getLossAnalysis(id: number): Promise<LossAnalysis> {
  const response = await fetch(`${API_BASE_URL}/api/datasets/${id}/loss-analysis`)
  return readResponse<LossAnalysis>(response)
}

export async function saveFeederMeterRoles(
  datasetId: number,
  feederId: string,
  input: { input_meter_id: string; output_meter_ids: string[] },
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/api/datasets/${datasetId}/feeders/${encodeURIComponent(feederId)}/meter-roles`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    },
  )
  await readResponse<unknown>(response)
}

export async function downloadDatasetReport(id: number): Promise<Blob> {
  const response = await fetch(`${API_BASE_URL}/api/datasets/${id}/reports/summary.pdf`)
  if (!response.ok) {
    await readResponse<unknown>(response)
    throw new Error(`Report request failed (${response.status})`)
  }
  return response.blob()
}
