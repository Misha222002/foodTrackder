import { useState, type PropsWithChildren } from 'react'
import { AuthDraftsContext, type CodeRequestDraft, type EmailForm } from '../model/auth-drafts'

const emptyEmails = () => ({ register: '', login: '', forgot: '' })

export function AuthDraftsProvider({ children }: PropsWithChildren) {
  const [emails, setEmails] = useState(emptyEmails)
  const [challenges, setChallenges] = useState<Record<string, CodeRequestDraft>>({})
  return (
    <AuthDraftsContext.Provider
      value={{
        emails,
        challenges,
        setEmail: (form: EmailForm, email: string) =>
          setEmails((current) => ({ ...current, [form]: email })),
        rememberChallenge: (challenge) =>
          setChallenges((current) => ({
            ...Object.fromEntries(Object.entries(current).slice(-9)),
            [challenge.challengeId]: challenge,
          })),
        clear: () => {
          setEmails(emptyEmails())
          setChallenges({})
        },
      }}
    >
      {children}
    </AuthDraftsContext.Provider>
  )
}
