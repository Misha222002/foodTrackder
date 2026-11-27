import { createContext, useContext } from 'react'
import type { Challenge } from '../api/auth-api'

export type EmailForm = 'register' | 'login' | 'forgot'
export type CodeRequestDraft = Challenge & {
  email: string
  returnTo: '/register' | '/login' | '/forgot-password'
}
export type AuthDrafts = {
  emails: Record<EmailForm, string>
  challenges: Record<string, CodeRequestDraft>
  setEmail: (form: EmailForm, email: string) => void
  rememberChallenge: (challenge: CodeRequestDraft) => void
  clear: () => void
}
export const AuthDraftsContext = createContext<AuthDrafts | null>(null)
export function useAuthDrafts() {
  const drafts = useContext(AuthDraftsContext)
  if (!drafts) throw new Error('Missing AuthDraftsProvider')
  return drafts
}
