import { Alert, Link } from '@mui/material'
import { config } from '../../../shared/config/env'

export function MailDeliveryNotice() {
  if (!config.devMailboxUrl) return null
  return (
    <Alert severity="info">
      В локальной версии письма с кодом находятся в{' '}
      <Link href={config.devMailboxUrl} target="_blank" rel="noreferrer">
        Mailpit
      </Link>
      . В обычный почтовый ящик они не отправляются.
    </Alert>
  )
}
