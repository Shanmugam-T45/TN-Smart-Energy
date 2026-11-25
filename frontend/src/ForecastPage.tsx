import { useEffect, useMemo, useState } from 'react'
import { Activity, RefreshCw, ShieldCheck } from 'lucide-react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useDatasets } from './useDatasets'
import { getDemandForecast, type DemandForecast } from './datasetApi'

export default function ForecastPage() {
  const { selectedDatasetId, selectedSummary } = useDatasets()
  const [horizon, setHorizon] = useState(24)
  const [refreshKey, setRefreshKey] = useState(0)
  const [forecastResult, setForecastResult] = useState<DemandForecast | null>(null)
  const [error, setError] = useState<{ datasetId: number; message: string } | null>(null)

  useEffect(() => {
    if (selectedDatasetId === null) return
    let active = true
    getDemandForecast(selectedDatasetId, horizon)
      .then((result) => {
        if (active) {
          setForecastResult(result)
          setError(null)
        }
      })
      .catch((cause: unknown) => {
        if (active) {
          setError({
            datasetId: selectedDatasetId,
            message: cause instanceof Error ? cause.message : 'Could not generate the demand forecast.',
          })
        }
      })
    return () => {
      active = false
    }
  }, [selectedDatasetId, horizon, refreshKey])

  const resultIsCurrent =
    forecastResult?.dataset_id === selectedDatasetId &&
    forecastResult.horizon_hours === horizon
  const errorMessage = error?.datasetId === selectedDatasetId ? error.message : null
  const chartData = useMemo(() => {
    if (!resultIsCurrent || forecastResult?.status !== 'forecast_available') return []
    const historical = (selectedSummary?.demand_series ?? []).map((point) => ({
      timestamp: point.timestamp,
      label: new Date(point.timestamp).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit' }),
      measured: point.demand_kw as number | null,
      forecast: null as number | null,
    }))
    const future = forecastResult.forecast.map((point) => ({
      timestamp: point.timestamp,
      label: new Date(point.timestamp).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit' }),
      measured: null as number | null,
      forecast: point.demand_kw,
      lower: point.lower_bound_kw,
      upper: point.upper_bound_kw,
    }))
    return [...historical, ...future].slice(-Math.max(72, horizon + 24))
  }, [forecastResult, horizon, resultIsCurrent, selectedSummary])

  return (
    <div className="page">
      <div className="page-heading">
        <div><p className="eyebrow">DEMAND ANALYTICS</p><h1>Demand forecasting</h1></div>
        <form className="forecast-controls" onSubmit={(event) => {
          event.preventDefault()
          setRefreshKey((current) => current + 1)
        }}>
          <label>Horizon (hours)<input type="number" min="1" max="168" value={horizon} onChange={(event) => setHorizon(Number(event.target.value))} /></label>
          <button className="primary-button" type="submit"><RefreshCw size={14} /> Refresh forecast</button>
        </form>
      </div>
      <div className="notice">
        <ShieldCheck size={17} />
        <span>Model-based estimates use uploaded demand history only. Forecasts are not live-grid predictions or dispatch instructions.</span>
      </div>

      {selectedDatasetId === null ? (
        <div className="empty-feature panel">
          <div className="empty-icon"><Activity size={28} /></div>
          <h2>Select an uploaded dataset</h2>
          <p>Upload time-stamped active_power_kw readings to train a demand forecast.</p>
        </div>
      ) : (
        <>
          {errorMessage && <div className="panel inline-error" role="alert">{errorMessage}</div>}
          {resultIsCurrent && forecastResult?.status === 'insufficient_history' && (
            <div className="panel forecast-empty">
              <h2>More history is needed</h2>
              <p>{forecastResult.training_observations} distinct demand timestamps found; at least {forecastResult.minimum_observations} are required.</p>
            </div>
          )}
          {resultIsCurrent && forecastResult?.status === 'forecast_available' && (
            <>
              <section className="metric-grid">
                <ForecastMetric label="Model" value="Random forest" detail={forecastResult.training_observations.toLocaleString() + ' observations'} />
                <ForecastMetric label="Forecast horizon" value={`${forecastResult.horizon_hours} h`} detail="Hourly estimates" />
                <ForecastMetric label="Validation MAE" value={forecastResult.validation_mae_kw == null ? 'Not calculated' : `${forecastResult.validation_mae_kw} kW`} detail={forecastResult.validation_method ?? 'Requires 40+ observations'} />
                <ForecastMetric label="Last observed" value={forecastResult.last_observed_timestamp ? new Date(forecastResult.last_observed_timestamp).toLocaleString() : '—'} detail="Based on uploaded readings" />
              </section>
              <section className="panel forecast-chart-panel">
                <div className="panel-header"><div><h2>Measured history and forecast</h2><p>{forecastResult.model}</p></div><span className="panel-badge">Uploaded data</span></div>
                <div className="chart-legend"><span><i className="actual" /> Measured</span><span><i className="predicted" /> Forecast</span></div>
                <div className="chart-area">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartData} margin={{ left: -20, right: 12, top: 8 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#edf1ef" />
                      <XAxis dataKey="label" tick={{ fill: '#81908a', fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={30} />
                      <YAxis tick={{ fill: '#81908a', fontSize: 10 }} axisLine={false} tickLine={false} />
                      <Tooltip contentStyle={{ borderRadius: 10, border: '1px solid #e5ebe8', fontSize: 11 }} />
                      <Line type="monotone" dataKey="measured" name="Measured demand (kW)" stroke="#1f8a70" strokeWidth={2} dot={false} connectNulls={false} />
                      <Line type="monotone" dataKey="forecast" name="Forecast demand (kW)" stroke="#d49635" strokeWidth={2} strokeDasharray="5 4" dot={false} connectNulls={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                <div className="forecast-limitation">{forecastResult.limitation}</div>
              </section>
            </>
          )}
          {!errorMessage && !resultIsCurrent && <div className="panel forecast-empty">Loading forecast…</div>}
        </>
      )}
    </div>
  )
}

function ForecastMetric({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <div className="metric-card forecast-metric"><div className="metric-content"><span>{label}</span><strong>{value}</strong><small>{detail}</small></div></div>
}
