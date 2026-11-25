import { useEffect, useState } from 'react'
import { Activity, Home, MapPin, Save, Zap } from 'lucide-react'
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
import {
  getDatasetMeter,
  listDatasetMeters,
  PUBLIC_DEMO_MODE,
  saveMeterProfile,
  type MeterDetail,
  type MeterSummary,
} from './datasetApi'

export default function HouseholdMonitoringPage() {
  const { selectedDatasetId } = useDatasets()
  const [meterResult, setMeterResult] = useState<{ datasetId: number; meters: MeterSummary[] } | null>(null)
  const [selectedMeterId, setSelectedMeterId] = useState<string | null>(null)
  const [detail, setDetail] = useState<MeterDetail | null>(null)
  const [metersError, setMetersError] = useState<{ datasetId: number; message: string } | null>(null)
  const [detailError, setDetailError] = useState<{ datasetId: number; meterId: string; message: string } | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [sanctionedLoad, setSanctionedLoad] = useState('')
  const [category, setCategory] = useState('')
  const [locality, setLocality] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveMessage, setSaveMessage] = useState<{ meterId: string; message: string } | null>(null)

  useEffect(() => {
    if (selectedDatasetId === null) return
    let active = true
    listDatasetMeters(selectedDatasetId)
      .then((items) => {
        if (!active) return
        setMeterResult({ datasetId: selectedDatasetId, meters: items })
        setSelectedMeterId((current) =>
          current && items.some((meter) => meter.meter_id === current)
            ? current
            : items[0]?.meter_id ?? null,
        )
      })
      .catch((error: unknown) => {
        if (active) {
          setMetersError({
            datasetId: selectedDatasetId,
            message: error instanceof Error ? error.message : 'Could not load meters.',
          })
        }
      })
    return () => {
      active = false
    }
  }, [selectedDatasetId, refreshKey])

  useEffect(() => {
    if (selectedDatasetId === null || selectedMeterId === null) return
    let active = true
    getDatasetMeter(selectedDatasetId, selectedMeterId)
      .then((result) => {
        if (!active) return
        setDetail(result)
        setSanctionedLoad(result.profile?.sanctioned_load_kw?.toString() ?? '')
        setCategory(result.profile?.consumer_category ?? '')
        setLocality(result.profile?.locality ?? '')
        setDetailError(null)
      })
      .catch((error: unknown) => {
        if (active) {
          setDetailError({
            datasetId: selectedDatasetId,
            meterId: selectedMeterId,
            message: error instanceof Error ? error.message : 'Could not load meter readings.',
          })
        }
      })
    return () => {
      active = false
    }
  }, [selectedDatasetId, selectedMeterId, refreshKey])

  const meters = meterResult?.datasetId === selectedDatasetId ? meterResult.meters : []
  const hasLoadedMeters = meterResult?.datasetId === selectedDatasetId
  const metersErrorMessage =
    metersError?.datasetId === selectedDatasetId ? metersError.message : null
  const selectedMeter = meters.find((meter) => meter.meter_id === selectedMeterId) ?? null
  const detailErrorMessage =
    detailError?.datasetId === selectedDatasetId && detailError.meterId === selectedMeterId
      ? detailError.message
      : null
  const saveMessageText =
    saveMessage?.meterId === selectedMeterId ? saveMessage.message : null
  const detailIsCurrent =
    detail?.dataset_id === selectedDatasetId && detail.meter_id === selectedMeterId
  const chartData = detailIsCurrent
    ? detail.readings.map((reading) => ({
        time: reading.timestamp.slice(5, 16).replace('T', ' '),
        power: reading.active_power_kw,
      }))
    : []

  async function saveProfile(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selectedMeterId || !sanctionedLoad || selectedDatasetId === null) return
    setSaving(true)
    setSaveMessage(null)
    setDetailError(null)
    try {
      await saveMeterProfile(selectedMeterId, {
        sanctioned_load_kw: Number(sanctionedLoad),
        consumer_category: category.trim() || null,
        locality: locality.trim() || null,
      })
      setSaveMessage({ meterId: selectedMeterId, message: 'Meter profile and sanctioned load saved.' })
      setRefreshKey((current) => current + 1)
    } catch (error) {
      setDetailError({
        datasetId: selectedDatasetId,
        meterId: selectedMeterId,
        message: error instanceof Error ? error.message : 'Could not save the meter profile.',
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="page">
      <div className="page-heading">
        <div><p className="eyebrow">CUSTOMER METER MONITORING</p><h1>Household smart meters</h1></div>
      </div>
      <div className="notice">
        <Activity size={17} />
        <span>Meter alerts compare the latest uploaded active power with the configured sanctioned load. Alerts are advisory screening only.</span>
      </div>

      {selectedDatasetId === null ? (
        <div className="empty-feature panel">
          <div className="empty-icon"><Home size={28} /></div>
          <h2>Select an uploaded dataset</h2>
          <p>Upload or select meter readings from the top bar to inspect household meters.</p>
        </div>
      ) : (
        <div className="meter-layout">
          <section className="panel meter-list-panel">
            <div className="panel-header">
              <div><h2>Meter list</h2><p>{meters.length} meter(s) in selected dataset</p></div>
            </div>
            {metersErrorMessage && <p className="inline-error">{metersErrorMessage}</p>}
            {!metersErrorMessage && hasLoadedMeters && meters.length === 0 && <p className="inline-empty">No meter readings found in this dataset.</p>}
            <div className="meter-list">
              {meters.map((meter) => (
                <button
                  type="button"
                  key={meter.meter_id}
                  className={`meter-list-item ${meter.meter_id === selectedMeterId ? 'selected' : ''}`}
                  onClick={() => {
                    setSelectedMeterId(meter.meter_id)
                    setSaveMessage(null)
                  }}
                >
                  <span className="meter-symbol"><Zap size={16} /></span>
                  <span className="meter-list-copy">
                    <strong>{meter.meter_id}</strong>
                    <small>{meter.locality || meter.consumer_category || 'Household meter'}</small>
                  </span>
                  <span className={`meter-status ${meter.alert_status === 'at_or_above_sanctioned_load' ? 'alert' : ''}`}>
                    {meter.alert_status === 'at_or_above_sanctioned_load' ? 'Alert' : meter.alert_status === 'sanctioned_load_not_configured' ? 'Set limit' : meter.alert_status === 'active_power_not_available' ? 'No power' : 'Normal'}
                  </span>
                </button>
              ))}
            </div>
          </section>

          <section className="meter-detail-column">
            {selectedMeter && (
              <>
                <div className="panel meter-overview">
                  <div className="panel-header">
                    <div><h2>{selectedMeter.meter_id}</h2><p>{PUBLIC_DEMO_MODE ? 'Latest simulated demo meter values' : 'Latest uploaded meter values'}</p></div>
                    <span className={`status-tag ${selectedMeter.alert_status === 'at_or_above_sanctioned_load' ? 'warning' : ''}`}>
                      {selectedMeter.alert_status === 'at_or_above_sanctioned_load' ? 'Sanctioned load alert' : 'Advisory monitoring'}
                    </span>
                  </div>
                  <div className="meter-stats">
                    <MeterStat label="Recorded energy" value={`${selectedMeter.total_energy_kwh.toLocaleString()} kWh`} />
                    <MeterStat label="Latest active power" value={selectedMeter.latest_active_power_kw == null ? 'Not provided' : `${selectedMeter.latest_active_power_kw} kW`} />
                    <MeterStat label="Latest voltage" value={selectedMeter.latest_voltage == null ? 'Not provided' : `${selectedMeter.latest_voltage} V`} />
                    <MeterStat label="Sanctioned load" value={selectedMeter.sanctioned_load_kw == null ? 'Not configured' : `${selectedMeter.sanctioned_load_kw} kW`} />
                  </div>
                  <div className={`sanction-banner ${selectedMeter.alert_status === 'at_or_above_sanctioned_load' ? 'alert' : ''}`}>
                    {selectedMeter.alert_status === 'at_or_above_sanctioned_load'
                      ? `${PUBLIC_DEMO_MODE ? 'Latest simulated demo power' : 'Latest uploaded power'} (${selectedMeter.latest_active_power_kw} kW) is at or above the configured sanctioned load (${selectedMeter.sanctioned_load_kw} kW).`
                      : selectedMeter.alert_status === 'sanctioned_load_not_configured'
                        ? 'Configure this meter’s sanctioned load to enable threshold screening.'
                        : selectedMeter.alert_status === 'active_power_not_available'
                          ? 'This meter has no active_power_kw reading, so sanctioned-load screening cannot run.'
                          : `${PUBLIC_DEMO_MODE ? 'Latest simulated demo active power' : 'Latest uploaded active power'} is below the configured sanctioned-load value.`}
                  </div>
                </div>

                <div className="panel">
                  <div className="panel-header"><div><h2>Meter demand history</h2><p>{PUBLIC_DEMO_MODE ? 'Simulated active power • no forecast is applied here' : 'Uploaded active power • no forecast is applied here'}</p></div></div>
                  <div className="chart-area small">
                    {detailErrorMessage ? <div className="chart-empty">{detailErrorMessage}</div> : !detailIsCurrent ? <div className="chart-empty">Loading meter history…</div> : chartData.some((point) => point.power !== null) ? (
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={chartData} margin={{ left: -20, right: 8 }}>
                          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#edf1ef" />
                          <XAxis dataKey="time" tick={{ fill: '#81908a', fontSize: 10 }} axisLine={false} tickLine={false} />
                          <YAxis tick={{ fill: '#81908a', fontSize: 10 }} axisLine={false} tickLine={false} />
                          <Tooltip contentStyle={{ borderRadius: 10, border: '1px solid #e5ebe8', fontSize: 11 }} />
                          <Line type="monotone" dataKey="power" name="Active power (kW)" stroke="#1f8a70" strokeWidth={2} dot={false} connectNulls={false} />
                        </LineChart>
                      </ResponsiveContainer>
                    ) : <div className="chart-empty">No active-power readings are available for this meter.</div>}
                  </div>
                </div>

                {PUBLIC_DEMO_MODE ? (
                  <div className="notice">This public demo is read-only. Meter profiles and sanctioned-load settings cannot be changed.</div>
                ) : (
                <form className="panel meter-profile-form" onSubmit={saveProfile}>
                  <div className="panel-header"><div><h2>Meter profile and sanctioned load</h2><p>Values can also be imported using optional CSV columns.</p></div></div>
                  <div className="profile-fields">
                    <label>Sanctioned load (kW)<input type="number" min="0.01" step="0.01" required value={sanctionedLoad} onChange={(event) => setSanctionedLoad(event.target.value)} /></label>
                    <label>Consumer category<input value={category} onChange={(event) => setCategory(event.target.value)} placeholder="Household" /></label>
                    <label><span><MapPin size={13} /> Locality</span><input value={locality} onChange={(event) => setLocality(event.target.value)} placeholder="Optional" /></label>
                  </div>
                  <div className="profile-actions">
                    {saveMessageText && <span className="save-message" role="status">{saveMessageText}</span>}
                    {detailErrorMessage && <span className="inline-error" role="alert">{detailErrorMessage}</span>}
                    <button className="primary-button" type="submit" disabled={saving || !detailIsCurrent}>
                      <Save size={15} /> {saving ? 'Saving…' : 'Save meter settings'}
                    </button>
                  </div>
                </form>
                )}
              </>
            )}
          </section>
        </div>
      )}
    </div>
  )
}

function MeterStat({ label, value }: { label: string; value: string }) {
  return <div className="meter-stat"><span>{label}</span><strong>{value}</strong></div>
}
