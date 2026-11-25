import { useEffect, useState } from 'react'
import { Activity, Building2, Save, ShieldCheck } from 'lucide-react'
import { useDatasets } from './useDatasets'
import {
  listDatasetTransformers,
  PUBLIC_DEMO_MODE,
  saveTransformerProfile,
  type TransformerSummary,
} from './datasetApi'

export default function TransformerMonitoringPage() {
  const { selectedDatasetId } = useDatasets()
  const [transformerResult, setTransformerResult] = useState<{
    datasetId: number
    transformers: TransformerSummary[]
  } | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [error, setError] = useState<{
    datasetId: number
    transformerId: string | null
    message: string
  } | null>(null)
  const [saving, setSaving] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const [profileDraft, setProfileDraft] = useState<{
    datasetId: number
    transformerId: string
    ratedCapacity: string
    feederId: string
    location: string
    highThreshold: string
    exceedanceThreshold: string
  } | null>(null)
  const [saveMessage, setSaveMessage] = useState<{ transformerId: string; message: string } | null>(null)

  useEffect(() => {
    if (selectedDatasetId === null) return
    let active = true
    listDatasetTransformers(selectedDatasetId)
      .then((items) => {
        if (!active) return
        setTransformerResult({ datasetId: selectedDatasetId, transformers: items })
        setError(null)
        setSelectedId((current) =>
          current && items.some((item) => item.transformer_id === current)
            ? current
            : items[0]?.transformer_id ?? null,
        )
      })
      .catch((cause: unknown) => {
        if (active) {
          setError({
            datasetId: selectedDatasetId,
            transformerId: null,
            message: cause instanceof Error ? cause.message : 'Could not load transformer readings.',
          })
        }
      })
    return () => {
      active = false
    }
  }, [selectedDatasetId, refreshKey])

  const transformers =
    transformerResult?.datasetId === selectedDatasetId ? transformerResult.transformers : []
  const listError =
    error?.datasetId === selectedDatasetId && error.transformerId === null ? error.message : null
  const selected = transformers.find((item) => item.transformer_id === selectedId) ?? null
  const draft =
    selected && profileDraft?.datasetId === selectedDatasetId &&
    profileDraft.transformerId === selected.transformer_id
      ? profileDraft
      : selected && selectedDatasetId !== null
        ? {
            datasetId: selectedDatasetId,
            transformerId: selected.transformer_id,
            ratedCapacity: selected.rated_capacity_kva?.toString() ?? '',
            feederId: selected.feeder_id ?? '',
            location: selected.location ?? '',
            highThreshold: selected.high_loading_threshold_percent.toString(),
            exceedanceThreshold: selected.exceedance_threshold_percent.toString(),
          }
        : null
  const formError =
    error?.datasetId === selectedDatasetId &&
    error.transformerId === selected?.transformer_id
      ? error.message
      : null
  const saveMessageText =
    saveMessage && saveMessage.transformerId === selected?.transformer_id
      ? saveMessage.message
      : null

  async function saveProfile(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selected || !draft || selectedDatasetId === null || !draft.ratedCapacity) return
    setSaving(true)
    setError(null)
    try {
      await saveTransformerProfile(selected.transformer_id, {
        rated_capacity_kva: Number(draft.ratedCapacity),
        feeder_id: draft.feederId.trim() || null,
        location: draft.location.trim() || null,
        high_loading_threshold_percent: Number(draft.highThreshold),
        exceedance_threshold_percent: Number(draft.exceedanceThreshold),
      })
      setSaveMessage({ transformerId: selected.transformer_id, message: 'Transformer ratings saved.' })
      setRefreshKey((current) => current + 1)
    } catch (cause) {
      setError({
        datasetId: selectedDatasetId,
        transformerId: selected.transformer_id,
        message: cause instanceof Error ? cause.message : 'Could not save transformer settings.',
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="page">
      <div className="page-heading">
        <div><p className="eyebrow">ASSET MONITORING</p><h1>Transformer loading</h1></div>
      </div>
      <div className="notice">
        <ShieldCheck size={17} />
        <span>Apparent power is estimated as active power ÷ power factor for the latest readings. Loading levels are configurable screening indicators, not universal safety limits.</span>
      </div>
      {selectedDatasetId === null ? (
        <div className="empty-feature panel">
          <div className="empty-icon"><Building2 size={28} /></div>
          <h2>Select an uploaded dataset</h2>
          <p>Upload or select readings with transformer IDs and active power to monitor configured assets.</p>
        </div>
      ) : (
        <div className="transformer-layout">
          <section className="panel transformer-list-panel">
            <div className="panel-header">
              <div><h2>Transformers</h2><p>{transformers.length} asset(s) in selected dataset</p></div>
            </div>
            {listError && <p className="inline-error" role="alert">{listError}</p>}
            {!listError && transformerResult?.datasetId === selectedDatasetId && transformers.length === 0 && <p className="inline-empty">No transformer IDs found in this dataset.</p>}
            <div className="meter-list">
              {transformers.map((item) => (
                <button
                  type="button"
                  key={item.transformer_id}
                  className={`meter-list-item ${item.transformer_id === selectedId ? 'selected' : ''}`}
                  onClick={() => {
                    setSelectedId(item.transformer_id)
                  }}
                >
                  <span className="meter-symbol"><Building2 size={16} /></span>
                  <span className="meter-list-copy">
                    <strong>{item.transformer_id}</strong>
                    <small>{item.location || item.feeder_id || 'Location not set'}</small>
                  </span>
                  <span className={`meter-status ${item.status === 'normal' ? '' : 'alert'}`}>
                    {item.status === 'normal' ? 'Normal' : item.status === 'high_loading' ? 'High load' : item.status === 'potential_capacity_exceedance' ? 'Review' : 'Set data'}
                  </span>
                </button>
              ))}
            </div>
          </section>

          {selected && (
            <div className="transformer-detail-column">
              <section className="panel transformer-overview">
                <div className="panel-header">
                  <div><h2>{selected.transformer_id}</h2><p>{PUBLIC_DEMO_MODE ? 'Latest simulated readings' : 'Latest readings'} across {selected.meter_count} meter(s)</p></div>
                  <Activity size={18} />
                </div>
                <div className="meter-stats transformer-stats">
                  <MeterStat label="Apparent power" value={selected.measured_apparent_power_kva == null ? 'Unavailable' : `${selected.measured_apparent_power_kva} kVA`} />
                  <MeterStat label="Active power" value={selected.measured_active_power_kw == null ? 'Unavailable' : `${selected.measured_active_power_kw} kW`} />
                  <MeterStat label="Rated capacity" value={selected.rated_capacity_kva == null ? 'Not configured' : `${selected.rated_capacity_kva} kVA`} />
                  <MeterStat label="Estimated loading" value={selected.loading_percent == null ? 'Unavailable' : `${selected.loading_percent}%`} />
                </div>
                <div className={`sanction-banner ${selected.status === 'normal' || selected.status === 'capacity_or_power_factor_not_available' ? '' : 'alert'}`}>
                  {selected.recommendation}
                  {selected.loading_percent != null && <> Current loading: {selected.loading_percent}%.</>}
                </div>
              </section>

              {PUBLIC_DEMO_MODE ? (
                <div className="notice">This public demo is read-only. Transformer ratings and screening thresholds cannot be changed.</div>
              ) : (
              <form className="panel meter-profile-form" onSubmit={saveProfile}>
                <div className="panel-header"><div><h2>Asset settings</h2><p>Configure transformer rating and screening thresholds</p></div></div>
                <div className="profile-fields transformer-profile-fields">
                  <label>Rated capacity (kVA)<input type="number" min="0.01" step="0.01" required value={draft?.ratedCapacity ?? ''} onChange={(event) => draft && setProfileDraft({ ...draft, ratedCapacity: event.target.value })} /></label>
                  <label>High-loading threshold (%)<input type="number" min="0" max="100" step="1" required value={draft?.highThreshold ?? '70'} onChange={(event) => draft && setProfileDraft({ ...draft, highThreshold: event.target.value })} /></label>
                  <label>Exceedance threshold (%)<input type="number" min={draft?.highThreshold ?? '70'} max="200" step="1" required value={draft?.exceedanceThreshold ?? '90'} onChange={(event) => draft && setProfileDraft({ ...draft, exceedanceThreshold: event.target.value })} /></label>
                  <label>Feeder ID<input value={draft?.feederId ?? ''} onChange={(event) => draft && setProfileDraft({ ...draft, feederId: event.target.value })} /></label>
                  <label>Location<input value={draft?.location ?? ''} onChange={(event) => draft && setProfileDraft({ ...draft, location: event.target.value })} /></label>
                </div>
                <div className="profile-actions">
                  {saveMessageText && <span className="save-message" role="status">{saveMessageText}</span>}
                  {formError && <span className="inline-error" role="alert">{formError}</span>}
                  <button className="primary-button" type="submit" disabled={saving}>
                    <Save size={15} /> {saving ? 'Saving…' : 'Save asset settings'}
                  </button>
                </div>
              </form>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function MeterStat({ label, value }: { label: string; value: string }) {
  return <div className="meter-stat"><span>{label}</span><strong>{value}</strong></div>
}
