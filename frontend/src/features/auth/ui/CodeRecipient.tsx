import { Typography } from '@mui/material'

export function CodeRecipient({ email }: { email?: string }) {
  if (!email) return null
  return (
    <Typography sx={{ overflowWrap: 'anywhere' }}>
      Код запрошен для <strong>{email}</strong>.
    </Typography>
  )
}
