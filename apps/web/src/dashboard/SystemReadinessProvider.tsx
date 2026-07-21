import type { ReactNode } from 'react'

import { SystemReadinessContext, type SystemReadinessContextValue } from './SystemReadinessContext'

type SystemReadinessProviderProps = {
  children: ReactNode
  value: SystemReadinessContextValue
}

export default function SystemReadinessProvider({ children, value }: SystemReadinessProviderProps) {
  return (
    <SystemReadinessContext.Provider value={value}>
      {children}
    </SystemReadinessContext.Provider>
  )
}
