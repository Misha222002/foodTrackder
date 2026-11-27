import { createContext, useContext, useSyncExternalStore } from 'react'
import type { AuthClient } from './client'

export const AuthContext = createContext<AuthClient | null>(null)
export function useAuthClient() {
  const client = useContext(AuthContext)
  if (!client) throw new Error('Missing AuthContext')
  return client
}
export function useSession() {
  const client = useAuthClient()
  return useSyncExternalStore(client.subscribe, client.snapshot)
}
