import { useEffect, useState } from 'react'

import { fetchHealth } from './api'
import AuthProvider from './auth/AuthProvider'
import { fetchSession, login, logout } from './auth/api'
import type { AuthenticatedSession, LoginRequest } from './auth/types'
import LoginView from './auth/LoginView'
import DashboardShell from './dashboard/DashboardShell'
import './index.css'

type LoadState =
  | { kind: 'loading' }
  | { kind: 'ready'; session: AuthenticatedSession }
  | { kind: 'login'; message?: string }
  | { kind: 'error' }

export default function App() {
  const [state, setState] = useState<LoadState>({ kind: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    async function load() {
      try {
        await fetchHealth(controller.signal)
        const session = await fetchSession(controller.signal)
        if (session.authenticated) {
          setState({ kind: 'ready', session })
        } else {
          setState({ kind: 'login' })
        }
      } catch {
        if (!controller.signal.aborted) setState({ kind: 'error' })
      }
    }
    void load()
    return () => controller.abort()
  }, [])

  async function handleLogin(request: LoginRequest) {
    const session = await login(request)
    setState({ kind: 'ready', session })
  }

  async function handleLogout() {
    await logout()
    setState({ kind: 'login', message: 'Session expired. Sign in again.' })
  }

  if (state.kind === 'loading') {
    return <main><p>Checking system safety state...</p></main>
  }

  if (state.kind === 'error') {
    return (
      <main>
        <section role="alert" className="unavailable">
          <h1>Trading controls unavailable</h1>
          <p>The backend safety state could not be verified.</p>
        </section>
      </main>
    )
  }

  if (state.kind === 'login') {
    return <LoginView message={state.message} onLogin={handleLogin} />
  }

  return (
    <AuthProvider session={state.session} signOut={handleLogout}>
      <DashboardShell onSignOut={handleLogout} />
    </AuthProvider>
  )
}
