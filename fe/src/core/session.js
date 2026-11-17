import { config } from './config'

// Anonymous session: no sign-up. The server issues a token once and the browser keeps it.
export async function getToken() {
  const stored = localStorage.getItem('token')
  if (stored) return stored
  const response = await fetch(`${config.apiUrl}/v1/session`, { method: 'POST' })
  if (!response.ok) throw new Error('Could not create a session')
  const data = await response.json()
  localStorage.setItem('token', data.token)
  return data.token
}
