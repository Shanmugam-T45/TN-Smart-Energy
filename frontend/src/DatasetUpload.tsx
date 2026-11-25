import { useRef, useState, type ChangeEvent } from 'react'
import { Download, UploadCloud } from 'lucide-react'
import { useDatasets } from './useDatasets'
import { uploadDataset } from './datasetApi'

const sampleCsv = [
  'meter_id,timestamp,energy_kwh,voltage,current_a,active_power_kw,power_factor,feeder_id,transformer_id,consumer_category,sanctioned_load_kw,transformer_rated_kva',
  'METER-SIM-001,2026-11-22T00:00:00Z,12.4,229,18.2,4.2,0.91,F-SIM-01,T-SIM-201,household,5,250',
  'METER-SIM-001,2026-11-22T01:00:00Z,11.8,231,17.6,4.1,0.92,F-SIM-01,T-SIM-201,household,5,250',
  'METER-SIM-002,2026-11-22T00:00:00Z,28.2,228,42.1,9.6,0.88,F-SIM-02,T-SIM-204,commercial,12,315',
].join('\n')

export default function DatasetUpload() {
  const inputRef = useRef<HTMLInputElement>(null)
  const { registerDataset } = useDatasets()
  const [isUploading, setIsUploading] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return

    setMessage(null)
    setError(null)
    setIsUploading(true)
    try {
      const result = await uploadDataset(file)
      registerDataset(result)
      const rejected = result.rejected_rows
      const errors = result.errors.slice(0, 3).map((item) => `Row ${item.row}: ${item.reason}`).join(' ')
      setMessage(
        `Saved ${result.accepted_rows} readings from ${result.filename}.` +
          (rejected ? ` Rejected ${rejected} rows. ${errors}` : ''),
      )
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : 'Upload failed. Please try again.')
    } finally {
      setIsUploading(false)
    }
  }

  function downloadTemplate() {
    const blob = new Blob([sampleCsv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'tn-smart-energy-sample.csv'
    link.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  return (
    <div className="dataset-upload">
      <input
        ref={inputRef}
        className="visually-hidden"
        type="file"
        accept=".csv,text/csv"
        aria-label="Choose a CSV meter dataset"
        onChange={handleFileChange}
      />
      <button
        className="upload-button"
        type="button"
        disabled={isUploading}
        onClick={() => inputRef.current?.click()}
      >
        <UploadCloud size={17} /> {isUploading ? 'Uploading…' : 'Upload data'}
      </button>
      <button className="template-button" type="button" onClick={downloadTemplate} title="Download simulated CSV sample">
        <Download size={15} /> <span>CSV template</span>
      </button>
      {(message || error) && (
        <div className={`upload-feedback ${error ? 'error' : 'success'}`} role={error ? 'alert' : 'status'}>
          {error || message}
        </div>
      )}
    </div>
  )
}
