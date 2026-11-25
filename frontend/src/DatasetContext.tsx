import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { getDatasetSummary, listDatasets, type DatasetMetadata, type DatasetSummary } from './datasetApi'
import { DatasetContext } from './datasetStore'

export function DatasetProvider({ children }: { children: ReactNode }) {
  const [datasets, setDatasets] = useState<DatasetMetadata[]>([])
  const [selectedDatasetId, setSelectedDatasetId] = useState<number | null>(null)
  const [summaryState, setSummaryState] = useState<{
    datasetId: number
    summary?: DatasetSummary
  } | null>(null)
  const [apiError, setApiError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    listDatasets()
      .then((items) => {
        if (!active) return
        setDatasets(items)
        setSelectedDatasetId((current) => current ?? items[0]?.id ?? null)
        setApiError(null)
      })
      .catch((error: unknown) => {
        if (active) setApiError(error instanceof Error ? error.message : 'Could not load saved datasets.')
      })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (selectedDatasetId === null) return

    let active = true
    getDatasetSummary(selectedDatasetId)
      .then((summary) => {
        if (active) {
          setSummaryState({ datasetId: selectedDatasetId, summary })
          setApiError(null)
        }
      })
      .catch((error: unknown) => {
        if (active) {
          setSummaryState({ datasetId: selectedDatasetId })
          setApiError(error instanceof Error ? error.message : 'Could not load the selected dataset.')
        }
      })
    return () => {
      active = false
    }
  }, [selectedDatasetId])

  const registerDataset = useCallback((dataset: DatasetMetadata) => {
    setDatasets((current) => [dataset, ...current.filter((item) => item.id !== dataset.id)])
    setSelectedDatasetId(dataset.id)
    setApiError(null)
  }, [])
  const selectDataset = useCallback((id: number | null) => {
    setSelectedDatasetId(id)
    setApiError(null)
  }, [])
  const selectedSummary =
    summaryState?.datasetId === selectedDatasetId ? summaryState.summary ?? null : null
  const isLoadingSummary =
    selectedDatasetId !== null && summaryState?.datasetId !== selectedDatasetId

  const value = useMemo(
    () => ({
      datasets,
      selectedDatasetId,
      selectedSummary,
      isLoadingSummary,
      apiError,
      selectDataset,
      registerDataset,
    }),
    [datasets, selectedDatasetId, selectedSummary, isLoadingSummary, apiError, selectDataset, registerDataset],
  )

  return <DatasetContext.Provider value={value}>{children}</DatasetContext.Provider>
}
