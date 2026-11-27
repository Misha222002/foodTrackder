import { Button, Stack, Typography } from '@mui/material'
import { Link } from 'react-router'

export function NotFoundPage() {
  return (
    <Stack spacing={2} alignItems="flex-start">
      <Typography component="h1" variant="h4">Страница не найдена</Typography>
      <Button component={Link} to="/" variant="contained">На главную</Button>
    </Stack>
  )
}
