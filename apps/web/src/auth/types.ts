export type AuthenticatedSession = {
  authenticated: true
  username: string
}

export type UnauthenticatedSession = {
  authenticated: false
}

export type SessionState = AuthenticatedSession | UnauthenticatedSession

export type LoginRequest = {
  username: string
  password: string
}
