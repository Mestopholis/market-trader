import { type FormEvent, useState } from 'react'

import type { LoginRequest } from './types'

type LoginViewProps = {
  message?: string
  onLogin: (request: LoginRequest) => Promise<void>
}

export default function LoginView({ message, onLogin }: LoginViewProps) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await onLogin({ username, password })
    } catch {
      setError('Authentication failed. Check the local operator credentials.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-panel" aria-labelledby="login-title">
        <h1 id="login-title">Local operator login</h1>
        {message ? <p role="alert" className="auth-alert">{message}</p> : null}
        {error ? <p role="alert" className="auth-alert">{error}</p> : null}
        <form className="auth-form" onSubmit={handleSubmit}>
          <label>
            <span>Username</span>
            <input
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.currentTarget.value)}
            />
          </label>
          <label>
            <span>Password</span>
            <input
              autoComplete="current-password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.currentTarget.value)}
            />
          </label>
          <button type="submit" className="paper-action-button" disabled={submitting}>
            Sign in
          </button>
        </form>
      </section>
    </main>
  )
}
