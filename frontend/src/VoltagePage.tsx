import { useEffect, useState } from 'react'
import { Gauge, ShieldCheck } from 'lucide-react'
import { useDatasets } from './useDatasets'
import { getVoltageAnalysis, type VoltageAnalysis } from './datasetApi'

export default function VoltagePage() {
  const { selectedDatasetId } = useDatasets()
  const [analysis, setAnalysis] = useState<VoltageAnalysis | null>(null)
  const [error, setError] = useState<{ datasetId: number; message: string } | null>(null)

  useEffect(() => {
    if (selectedDatasetId === null) return
    let active = true
    getVoltageAnalysis(selectedDatasetId)
      .then((result) => {
        if (active) {
          setAnalysis(result)
          setError(null)
        }
      })
      .catch((cause: unknown) => {
        if (active) {
          setError({
            datasetId: selectedDatasetId,
            message: cause instanceof Error ? cause.message : 'Could not load voltage readings.',
          })
        }
      })
    return () => {
      active = false
    }
  }, [selectedDatasetId])

  const current = analysis?.dataset_id === selectedDatasetId ? analysis : null
  const errorMessage = error?.datasetId === selectedDatasetId ? error.message : null

  return (
    <div className="page">
      <div className="page-heading"><div><p className="eyebrow">POWER QUALITY</p><h1>Voltage analysis</h1></div></div>
      <div className="notice"><ShieldCheck size={17} /><span>Readings below 207 V or above 253 V are flagged for screening only; these levels do not establish a fault or regulatory violation.</span></div>
      {selectedDatasetId === null ? (
        <div className="empty-feature panel"><div className="empty-icon"><Gauge size={28} /></div><h2>Select an uploaded dataset</h2><p>Upload voltage measurements to inspect screening results by feeder.</p></div>
      ) : errorMessage ? (
        <div className="panel forecast-empty" role="alert">{errorMessage}</div>
      ) : !current ? (
        <div className="panel forecast-empty">Loading voltage analysis…</div>
      ) : current.voltage_reading_count === 0 ? (
        <div className="panel forecast-empty"><h2>No voltage readings found</h2><p>The selected dataset does not contain voltage values.</p></div>
      ) : (
        <>
          <section className="metric-grid">
            <VoltageMetric label="Readings analyzed" value={current.voltage_reading_count.toLocaleString()} />
            <VoltageMetric label="Average voltage" value={`${current.average_voltage ?? '—'} V`} />
            <VoltageMetric label="Low screens" value={current.low_voltage_count.toLocaleString()} detail={`Below ${current.low_threshold_v} V`} />
            <VoltageMetric label="High screens" value={current.high_voltage_count.toLocaleString()} detail={`Above ${current.high_threshold_v} V`} />
          </section>
          <section className="panel table-panel">
            <div className="panel-header"><div><h2>Voltage by feeder</h2><p>Aggregated uploaded readings • not fault diagnosis</p></div></div>
            <div className="table-wrap">
              <table>
                <thead><tr><th>Feeder</th><th>Readings</th><th>Average (V)</th><th>Range (V)</th><th>Low screens</th><th>High screens</th></tr></thead>
                <tbody>
                  {current.feeders.map((feeder) => (
                    <tr key={feeder.feeder_id}>
                      <td>{feeder.feeder_id}</td>
                      <td>{feeder.reading_count}</td>
                      <td>{feeder.average_voltage}</td>
                      <td>{feeder.minimum_voltage}–{feeder.maximum_voltage}</td>
                      <td><span className={`status-tag ${feeder.low_voltage_count ? 'warning' : ''}`}>{feeder.low_voltage_count}</span></td>
                      <td><span className={`status-tag ${feeder.high_voltage_count ? 'warning' : ''}`}>{feeder.high_voltage_count}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="forecast-limitation">{current.limitation}</div>
          </section>
        </>
      )}
    </div>
  )
}

function VoltageMetric({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return <div className="metric-card forecast-metric"><div className="metric-content"><span>{label}</span><strong>{value}</strong>{detail && <small>{detail}</small>}</div></div>
}
