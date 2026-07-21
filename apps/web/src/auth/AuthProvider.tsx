import { createContext, type ReactNode } from 'react'

import type { AuthenticatedSession } from './types'

type AuthContextValue = {
  session: AuthenticatedSession
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

type AuthProviderProps = AuthContextValue & {
  children: ReactNode
}

export default function AuthProvider({ children, session, signOut }: AuthProviderProps) {
  return (
    <AuthContext.Provider value={{ session, signOut }}>
      {children}
    </AuthContext.Provider>
  )
}

