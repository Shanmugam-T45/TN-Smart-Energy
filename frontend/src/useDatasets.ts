import { useContext } from 'react'
import { DatasetContext } from './datasetStore'

export function useDatasets() {
  const context = useContext(DatasetContext)
  if (!context) throw new Error('useDatasets must be used within DatasetProvider.')
  return context
}
