import { useContext } from 'react'

import type { ComponentState } from '../api'
import { SystemReadinessContext } from './SystemReadinessContext'

export function usePaperActionBlock(): ComponentState | null {
  const readiness = useContext(SystemReadinessContext)
  if (!readiness) return null
  return readiness.components?.find((component) => component.blocking) ?? null
}
