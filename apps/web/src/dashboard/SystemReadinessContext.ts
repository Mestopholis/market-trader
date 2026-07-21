import { createContext } from 'react'

import type { ReadinessResponse } from '../api'

export type SystemReadinessContextValue = ReadinessResponse | null

export const SystemReadinessContext = createContext<SystemReadinessContextValue>(null)
