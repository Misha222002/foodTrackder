import { Alert, Box, Button, Card, CardContent, CircularProgress, Stack, Typography } from '@mui/material'
import { useGetHealthQuery } from '../../../shared/api'

export function HomePage() {
  const { data, isFetching, isError, refetch } = useGetHealthQuery()
  return (
    <Stack spacing={3}>
      <Box>
        <Typography component="h1" variant="h3" sx={{ fontSize: { xs: '2rem', md: '3rem' }, fontWeight: 700 }}>
          Ем по плану
        </Typography>
        <Typography color="text.secondary" sx={{ mt: 2, maxWidth: 560 }}>
          Здесь появятся ваши продукты, любимые блюда, план питания и дневник.
        </Typography>
      </Box>
      <Card sx={{ maxWidth: 640 }}>
        <CardContent>
          <Typography component="h2" variant="h6" gutterBottom>Начало работы</Typography>
          <Typography color="text.secondary" sx={{ mb: 3 }}>
            Мы готовим приложение. Проверка соединения поможет убедиться, что сервис доступен.
          </Typography>
          {isFetching ? (
            <Stack direction="row" spacing={2} alignItems="center" role="status">
              <CircularProgress size={20} aria-label="Проверка соединения" />
              <Typography>Проверяем соединение…</Typography>
            </Stack>
          ) : isError ? (
            <Alert severity="error">Не удалось связаться с сервисом. Попробуйте ещё раз.</Alert>
          ) : data?.status === 'ok' ? (
            <Alert severity="success">Сервис доступен</Alert>
          ) : null}
          <Button variant="outlined" onClick={() => void refetch()} disabled={isFetching} sx={{ mt: 2 }}>
            Проверить снова
          </Button>
        </CardContent>
      </Card>
    </Stack>
  )
}
