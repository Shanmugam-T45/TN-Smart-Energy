import { useEffect, useState } from 'react'
import { BarChart3, ShieldCheck } from 'lucide-react'
import { getLossAnalysis, PUBLIC_DEMO_MODE, saveFeederMeterRoles, type LossAnalysis } from './datasetApi'
import { useDatasets } from './useDatasets'

type LossDraft = {
  datasetId: number
  feederId: string
  inputMeterId: string
  outputMeterIds: string[]
}

export default function LossAnalysisPage() {
  const { selectedDatasetId } = useDatasets()
  const [analysis, setAnalysis] = useState<LossAnalysis | null>(null)
  const [selectedFeederId, setSelectedFeederId] = useState<string | null>(null)
  const [draft, setDraft] = useState<LossDraft | null>(null)
  const [error, setError] = useState<{ datasetId: number; message: string } | null>(null)
  const [saving, setSaving] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const [savedMessage, setSavedMessage] = useState<{ feederId: string; message: string } | null>(null)

  useEffect(() => {
    if (selectedDatasetId === null) return
    let active = true
    getLossAnalysis(selectedDatasetId)
      .then((result) => {
        if (!active) return
        setAnalysis(result)
        setError(null)
        setSelectedFeederId((current) =>
          current && result.feeders.some((feeder) => feeder.feeder_id === current)
            ? current
            : result.feeders[0]?.feeder_id ?? null,
        )
      })
      .catch((cause: unknown) => {
        if (active) {
          setError({
            datasetId: selectedDatasetId,
            message: cause instanceof Error ? cause.message : 'Could not load feeder energy data.',
          })
        }
      })
    return () => {
      active = false
    }
  }, [selectedDatasetId, refreshKey])

  const current = analysis?.dataset_id === selectedDatasetId ? analysis : null
  const feeder = current?.feeders.find((item) => item.feeder_id === selectedFeederId) ?? null
  const formValues =
    feeder && draft?.datasetId === selectedDatasetId && draft.feederId === feeder.feeder_id
      ? draft
      : feeder && selectedDatasetId !== null
        ? {
            datasetId: selectedDatasetId,
            feederId: feeder.feeder_id,
            inputMeterId: feeder.input_meter_id ?? feeder.meter_ids[0] ?? '',
            outputMeterIds: feeder.output_meter_ids,
          }
        : null
  const errorMessage = error?.datasetId === selectedDatasetId ? error.message : null
  const savedMessageText =
    savedMessage && savedMessage.feederId === feeder?.feeder_id ? savedMessage.message : null

  function updateDraft(update: Partial<Pick<LossDraft, 'inputMeterId' | 'outputMeterIds'>>) {
    if (!formValues) return
    setDraft({ ...formValues, ...update })
  }

  async function saveRoles(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!formValues || selectedDatasetId === null) return
    setSaving(true)
    setError(null)
    try {
      await saveFeederMeterRoles(selectedDatasetId, formValues.feederId, {
        input_meter_id: formValues.inputMeterId,
        output_meter_ids: formValues.outputMeterIds,
      })
      setSavedMessage({ feederId: formValues.feederId, message: 'Meter roles saved and energy balance recalculated.' })
      setRefreshKey((value) => value + 1)
    } catch (cause) {
      setError({
        datasetId: selectedDatasetId,
        message: cause instanceof Error ? cause.message : 'Could not save feeder meter roles.',
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="page">
      <div className="page-heading"><div><p className="eyebrow">NETWORK EFFICIENCY</p><h1>Distribution loss analysis</h1></div></div>
      <div className="notice"><ShieldCheck size={17} /><span>Choose an upstream input meter and downstream output meters for a feeder. A difference is an energy-balance discrepancy, not proof of technical loss or theft.</span></div>
      {selectedDatasetId === null ? (
        <div className="empty-feature panel"><div className="empty-icon"><BarChart3 size={28} /></div><h2>Select an uploaded dataset</h2><p>Upload readings with feeder_id values to configure input and output meter boundaries.</p></div>
      ) : errorMessage && !current ? (
        <div className="panel forecast-empty" role="alert">{errorMessage}</div>
      ) : !current ? (
        <div className="panel forecast-empty">Loading feeder energy data…</div>
      ) : current.feeders.length === 0 ? (
        <div className="panel forecast-empty"><h2>No feeder IDs found</h2><p>Assign feeder_id values in the uploaded dataset before configuring a boundary.</p></div>
      ) : (
        <div className="loss-layout">
          <section className="panel">
            <div className="panel-header"><div><h2>Feeder comparison</h2><p>Summed energy by uploaded meter</p></div></div>
            <div className="table-wrap">
              <table>
                <thead><tr><th>Feeder</th><th>Input (kWh)</th><th>Output (kWh)</th><th>Difference (kWh)</th><th>Difference (%)</th></tr></thead>
                <tbody>
                  {current.feeders.map((item) => (
                    <tr key={item.feeder_id} className={item.feeder_id === selectedFeederId ? 'selected-row' : ''}>
                      <td><button className="table-link" type="button" onClick={() => setSelectedFeederId(item.feeder_id)}>{item.feeder_id}</button></td>
                      <td>{item.input_energy_kwh ?? 'Not configured'}</td>
                      <td>{item.output_energy_kwh ?? 'Not configured'}</td>
                      <td>{item.energy_discrepancy_kwh ?? '—'}</td>
                      <td>{item.discrepancy_percent == null ? '—' : `${item.discrepancy_percent}%`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="forecast-limitation">{current.limitation}</div>
          </section>

          {PUBLIC_DEMO_MODE ? (
            <div className="notice">This public demo is read-only. The sample feeder boundaries are preconfigured and cannot be changed.</div>
          ) : feeder && formValues && (
            <form className="panel loss-config" onSubmit={saveRoles}>
              <div className="panel-header"><div><h2>Configure {feeder.feeder_id}</h2><p>{feeder.meter_ids.length} meter(s) available</p></div></div>
              <label className="loss-input-select">Upstream input meter
                <select required value={formValues.inputMeterId} onChange={(event) => {
                  updateDraft({
                    inputMeterId: event.target.value,
                    outputMeterIds: formValues.outputMeterIds.filter((meterId) => meterId !== event.target.value),
                  })
                }}>
                  {feeder.meter_ids.map((meterId) => <option key={meterId} value={meterId}>{meterId}</option>)}
                </select>
              </label>
              <fieldset className="output-meter-list">
                <legend>Downstream output meters (choose at least one)</legend>
                {feeder.meter_ids.filter((meterId) => meterId !== formValues.inputMeterId).map((meterId) => (
                  <label key={meterId}>
                    <input
                      type="checkbox"
                      checked={formValues.outputMeterIds.includes(meterId)}
                      onChange={(event) => updateDraft({
                        outputMeterIds: event.target.checked
                          ? [...formValues.outputMeterIds, meterId]
                          : formValues.outputMeterIds.filter((item) => item !== meterId),
                      })}
                    />
                    {meterId}
                  </label>
                ))}
              </fieldset>
              {errorMessage && <p className="inline-error" role="alert">{errorMessage}</p>}
              {savedMessageText && <p className="save-message" role="status">{savedMessageText}</p>}
              <div className="profile-actions"><button className="primary-button" type="submit" disabled={saving || !formValues.outputMeterIds.length}>{saving ? 'Saving…' : 'Save feeder boundary'}</button></div>
            </form>
          )}
        </div>
      )}
    </div>
  )
}
