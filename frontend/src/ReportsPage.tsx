import { useState } from 'react'
import { Download, FileText, ShieldCheck } from 'lucide-react'
import { downloadDatasetReport } from './datasetApi'
import { useDatasets } from './useDatasets'

export default function ReportsPage() {
  const { selectedDatasetId, datasets, selectedSummary, isLoadingSummary } = useDatasets()
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function downloadReport() {
    if (selectedDatasetId === null) return
    setDownloading(true)
    setError(null)
    try {
      const report = await downloadDatasetReport(selectedDatasetId)
      const url = URL.createObjectURL(report)
      const link = document.createElement('a')
      link.href = url
      link.download = `tn-smart-energy-dataset-${selectedDatasetId}-report.pdf`
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not generate the PDF report.')
    } finally {
      setDownloading(false)
    }
  }

  const selectedFilename =
    datasets.find((dataset) => dataset.id === selectedDatasetId)?.filename ?? 'Selected dataset'

  return (
    <div className="page">
      <div className="page-heading"><div><p className="eyebrow">DATA EXPORTS</p><h1>Reports</h1></div></div>
      <div className="notice"><ShieldCheck size={17} /><span>Reports contain uploaded measurements, configured screening values and manually recorded events; they are not official utility records or diagnoses.</span></div>
      {selectedDatasetId === null ? (
        <div className="empty-feature panel"><div className="empty-icon"><FileText size={28} /></div><h2>Select an uploaded dataset</h2><p>Choose an uploaded dataset from the top bar to generate a report.</p></div>
      ) : (
        <section className="panel report-card">
          <div className="report-icon"><FileText size={25} /></div>
          <div className="report-copy">
            <h2>Dataset summary report</h2>
            <p>{selectedFilename}</p>
            {isLoadingSummary ? <small>Loading uploaded dataset summary…</small> : selectedSummary && (
              <small>{selectedSummary.record_count.toLocaleString()} readings · {selectedSummary.meter_count} meters · {selectedSummary.total_energy_kwh.toLocaleString()} kWh</small>
            )}
          </div>
          <button className="primary-button" type="button" onClick={downloadReport} disabled={downloading || isLoadingSummary}>
            <Download size={15} /> {downloading ? 'Generating PDF…' : 'Download PDF'}
          </button>
          {error && <p className="inline-error" role="alert">{error}</p>}
        </section>
      )}
    </div>
  )
}
