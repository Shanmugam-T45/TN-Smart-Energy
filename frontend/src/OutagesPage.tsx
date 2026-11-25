import { useEffect, useState } from 'react'
import { AlertTriangle, ShieldCheck } from 'lucide-react'
import { createOutageEvent, getOutageAnalysis, PUBLIC_DEMO_MODE, type OutageAnalysis } from './datasetApi'
import { useDatasets } from './useDatasets'

function toLocalDateTimeValue(date: Date) {
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}

function toIsoTimestamp(value: string) {
  return new Date(value).toISOString()
}

export default function OutagesPage() {
  const { selectedDatasetId } = useDatasets()
  const [analysis, setAnalysis] = useState<OutageAnalysis | null>(null)
  const [error, setError] = useState<{ datasetId: number; message: string } | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [feederId, setFeederId] = useState('')
  const [startedAt, setStartedAt] = useState(() => toLocalDateTimeValue(new Date()))
  const [endedAt, setEndedAt] = useState('')
  const [cause, setCause] = useState('')
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (selectedDatasetId === null) return
    let active = true
    getOutageAnalysis(selectedDatasetId)
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
            message: cause instanceof Error ? cause.message : 'Could not load outage events.',
          })
        }
      })
    return () => {
      active = false
    }
  }, [selectedDatasetId, refreshKey])

  const current = analysis?.dataset_id === selectedDatasetId ? analysis : null
  const errorMessage = error?.datasetId === selectedDatasetId ? error.message : null

  async function submitOutage(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (selectedDatasetId === null) return
    setSaving(true)
    setError(null)
    try {
      await createOutageEvent(selectedDatasetId, {
        feeder_id: feederId.trim(),
        started_at: toIsoTimestamp(startedAt),
        ended_at: endedAt ? toIsoTimestamp(endedAt) : null,
        cause: cause.trim() || 'Unspecified',
        notes: notes.trim() || null,
      })
      setRefreshKey((value) => value + 1)
      setFeederId('')
      setEndedAt('')
      setCause('')
      setNotes('')
    } catch (cause) {
      setError({
        datasetId: selectedDatasetId,
        message: cause instanceof Error ? cause.message : 'Could not save outage event.',
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="page">
      <div className="page-heading"><div><p className="eyebrow">SERVICE RELIABILITY</p><h1>Outage log and analysis</h1></div></div>
      <div className="notice"><ShieldCheck size={17} /><span>Outage events are manually logged and associated with the selected dataset. This app does not detect outages from live telemetry.</span></div>
      {selectedDatasetId === null ? (
        <div className="empty-feature panel"><div className="empty-icon"><AlertTriangle size={28} /></div><h2>Select an uploaded dataset</h2><p>Outage records are stored alongside the selected dataset.</p></div>
      ) : (
        <>
          {errorMessage && <div className="panel inline-error" role="alert">{errorMessage}</div>}
          <section className="metric-grid">
            <OutageMetric label="Logged events" value={current ? String(current.event_count) : '…'} />
            <OutageMetric label="Ongoing events" value={current ? String(current.ongoing_count) : '…'} />
            <OutageMetric label="Total duration" value={current ? `${(current.total_duration_minutes / 60).toFixed(1)} h` : '…'} />
          </section>
          <div className="outage-layout">
            {PUBLIC_DEMO_MODE ? (
              <div className="panel forecast-empty">
                <h2>Read-only public demo</h2>
                <p>Outage events are not fabricated for the demo, and logging new events is disabled.</p>
              </div>
            ) : (
            <form className="panel outage-form" onSubmit={submitOutage}>
              <div className="panel-header"><div><h2>Log an outage event</h2><p>Use a timezone-aware local date/time</p></div></div>
              <div className="profile-fields">
                <label>Feeder ID<input required value={feederId} onChange={(event) => setFeederId(event.target.value)} placeholder="F-101" /></label>
                <label>Start time<input type="datetime-local" required value={startedAt} onChange={(event) => setStartedAt(event.target.value)} /></label>
                <label>End time<input type="datetime-local" min={startedAt} value={endedAt} onChange={(event) => setEndedAt(event.target.value)} /></label>
                <label>Cause<input value={cause} onChange={(event) => setCause(event.target.value)} placeholder="Planned maintenance" /></label>
                <label className="outage-notes">Notes<input value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Optional details" /></label>
              </div>
              <div className="profile-actions"><button className="primary-button" type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save outage event'}</button></div>
            </form>
            )}

            <section className="panel outage-events">
              <div className="panel-header"><div><h2>Recorded events</h2><p>Newest first</p></div></div>
              {!current ? <p className="inline-empty">Loading events…</p> : current.events.length === 0 ? <p className="inline-empty">No outage events have been recorded for this dataset.</p> : (
                <div className="outage-event-list">
                  {current.events.map((event) => (
                    <article className="outage-event" key={event.id}>
                      <div className="outage-event-header"><strong>{event.feeder_id}</strong><span className={`meter-status ${event.is_ongoing ? 'alert' : ''}`}>{event.is_ongoing ? 'Ongoing' : `${(event.duration_minutes / 60).toFixed(1)} h`}</span></div>
                      <p>{event.cause}</p>
                      <small>{new Date(event.started_at).toLocaleString()} {event.ended_at ? `– ${new Date(event.ended_at).toLocaleString()}` : '– no end time'}</small>
                      {event.notes && <small>{event.notes}</small>}
                    </article>
                  ))}
                </div>
              )}
              {current && <div className="forecast-limitation">{current.limitation}</div>}
            </section>
          </div>
        </>
      )}
    </div>
  )
}

function OutageMetric({ label, value }: { label: string; value: string }) {
  return <div className="metric-card forecast-metric"><div className="metric-content"><span>{label}</span><strong>{value}</strong></div></div>
}
