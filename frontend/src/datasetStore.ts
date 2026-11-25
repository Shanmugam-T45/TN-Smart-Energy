import { createContext } from 'react'
import type { DatasetMetadata, DatasetSummary } from './datasetApi'

export interface DatasetContextValue {
  datasets: DatasetMetadata[]
  selectedDatasetId: number | null
  selectedSummary: DatasetSummary | null
  isLoadingSummary: boolean
  apiError: string | null
  selectDataset: (id: number | null) => void
  registerDataset: (dataset: DatasetMetadata) => void
}

export const DatasetContext = createContext<DatasetContextValue | null>(null)
