import { useState } from 'react'
import { Activity, ShieldCheck, SlidersHorizontal } from 'lucide-react'
import { useDatasets } from './useDatasets'
import { runConservationScenario, type ConservationResult } from './datasetApi'

export default function ConservationPage() {
  const { selectedDatasetId, selectedSummary, isLoadingSummary } = useDatasets()
  const [shiftPercent, setShiftPercent] = useState(18)
  const [actualReduction, setActualReduction] = useState('')
  const [result, setResult] = useState<{
    datasetId: number
    result: ConservationResult
  } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)

  const baseline = selectedDatasetId === null ? null : selectedSummary?.maximum_demand_kw ?? null
  const scenario = result?.datasetId === selectedDatasetId ? result.result : null

  async function runScenario(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (selectedDatasetId === null || baseline === null) return
    setRunning(true)
    setError(null)
    try {
      const calculation = await runConservationScenario({
        original_peak_kw: baseline,
        shiftable_load_kw: baseline * shiftPercent / 100,
        actual_reduction_kwh: actualReduction === '' ? null : Number(actualReduction),
      })
      setResult({ datasetId: selectedDatasetId, result: calculation })
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not run the conservation scenario.')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="page">
      <div className="page-heading">
        <div><p className="eyebrow">ENERGY CONSERVATION</p><h1>Load-shifting simulator</h1></div>
      </div>
      <div className="notice">
        <ShieldCheck size={17} />
        <span>Scenario only: shifting load can reduce peak demand, but this estimate does not control appliances or establish energy savings unless measured kWh savings are supplied.</span>
      </div>

      {selectedDatasetId === null ? (
        <div className="empty-feature panel">
          <div className="empty-icon"><SlidersHorizontal size={28} /></div>
          <h2>Select an uploaded dataset</h2>
          <p>Upload meter readings with active_power_kw to use a measured peak as the scenario baseline.</p>
        </div>
      ) : isLoadingSummary ? (
        <div className="panel forecast-empty">Loading dataset demand…</div>
      ) : baseline === null ? (
        <div className="panel forecast-empty">
          <h2>Demand readings are required</h2>
          <p>The selected dataset has no active_power_kw values, so the app cannot calculate a measured peak baseline.</p>
        </div>
      ) : (
        <div className="simulator-grid">
          <form className="panel controls-panel" onSubmit={runScenario}>
            <div className="panel-header"><div><h2>Scenario controls</h2><p>Calculated from selected uploaded dataset</p></div></div>
            <div className="scenario-baseline">
              <span>Measured peak baseline</span>
              <strong>{baseline.toLocaleString(undefined, { maximumFractionDigits: 2 })} kW</strong>
            </div>
            <label>Shiftable share <strong>{shiftPercent}%</strong><input type="range" min="0" max="40" step="1" value={shiftPercent} onChange={(event) => setShiftPercent(Number(event.target.value))} /></label>
            <div className="scenario-baseline compact">
              <span>Shiftable demand</span>
              <strong>{(baseline * shiftPercent / 100).toLocaleString(undefined, { maximumFractionDigits: 2 })} kW</strong>
            </div>
            <label className="energy-savings-input">Measured energy reduction (optional, kWh)<input type="number" min="0" step="0.01" value={actualReduction} onChange={(event) => setActualReduction(event.target.value)} placeholder="Leave blank if unknown" /></label>
            {error && <p className="inline-error" role="alert">{error}</p>}
            <button className="primary-button" type="submit" disabled={running || baseline <= 0}>
              <Activity size={15} /> {running ? 'Calculating…' : 'Run scenario'}
            </button>
          </form>

          <section className="panel conservation-result">
            <div className="panel-header"><div><h2>Scenario result</h2><p>Advisory comparison • not a measured outcome</p></div></div>
            {scenario ? (
              <>
                <div className="conservation-values">
                  <div><span>Original peak</span><strong>{scenario.original_peak_kw.toFixed(2)} kW</strong></div>
                  <div><span>Estimated peak after shifting</span><strong>{scenario.new_estimated_peak_kw.toFixed(2)} kW</strong></div>
                  <div><span>Estimated peak reduction</span><strong>{scenario.peak_reduction_percent.toFixed(2)}%</strong></div>
                  <div><span>Measured energy savings supplied</span><strong>{scenario.kwh_energy_savings == null ? 'Not provided' : `${scenario.kwh_energy_savings} kWh`}</strong></div>
                </div>
                <div className="saving">{scenario.interpretation}</div>
              </>
            ) : (
              <div className="forecast-empty">Set the shiftable share and run a scenario to see the estimate.</div>
            )}
          </section>
        </div>
      )}
    </div>
  )
}
