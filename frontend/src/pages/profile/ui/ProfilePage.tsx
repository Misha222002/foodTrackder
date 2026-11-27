import { Alert, Button, CircularProgress, Stack, TextField, Typography } from '@mui/material'
import { Navigate } from 'react-router'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { userApi } from '../../../entities/user'
import { useAuthClient, useSession } from '../../../shared/auth/context'
import { errorText } from '../../../shared/api/error-text'
import { applyFormErrors } from '../../../shared/api/form-errors'
import { useStaleRefresh } from '../../../shared/api/use-stale-refresh'
import type { components } from '../../../shared/api/generated/schema'

const time = z.string().regex(/^([01]\d|2[0-3]):[0-5]\d$/, 'Время в формате ЧЧ:ММ')
const schema = z.object({
  displayName: z.string().max(100, 'Не более 100 символов'),
  timezone: z
    .string()
    .min(1, 'Укажите часовой пояс')
    .refine((value) => {
      try {
        new Intl.DateTimeFormat('ru', { timeZone: value })
        return true
      } catch {
        return false
      }
    }, 'Укажите часовой пояс IANA, например Europe/Moscow'),
  mealTimes: z.object({ breakfast: time, lunch: time, dinner: time, snack: time }),
})
const meals = { breakfast: 'Завтрак', lunch: 'Обед', dinner: 'Ужин', snack: 'Перекус' } as const
const fields = [
  'displayName',
  'timezone',
  'mealTimes.breakfast',
  'mealTimes.lunch',
  'mealTimes.dinner',
  'mealTimes.snack',
] as const

function ProfileEditor({
  user,
  reload,
}: {
  user: components['schemas']['UserResponse']
  reload: () => unknown
}) {
  const [update, result] = userApi.useUpdateMeMutation()
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: {
      displayName: user.displayName,
      timezone: user.timezone,
      mealTimes: user.mealTimes as z.infer<typeof schema>['mealTimes'],
    },
  })
  const conflict = result.error && 'status' in result.error && result.error.status === 412
  return (
    <Stack
      component="form"
      noValidate
      spacing={2}
      maxWidth={540}
      onSubmit={form.handleSubmit(async (body) => {
        try {
          await update({ userId: user.id, revision: user.revision, body }).unwrap()
        } catch (error) {
          applyFormErrors(error, form.setError, fields)
        }
      })}
    >
      <Typography component="h1" variant="h4">
        Профиль
      </Typography>
      <Typography>{user.email}</Typography>
      <Alert severity="success">Почта подтверждена</Alert>
      {result.error && <Alert severity="error">{errorText(result.error)}</Alert>}
      {conflict && (
        <Button
          onClick={() => {
            void reload()
          }}
        >
          Загрузить актуальный профиль
        </Button>
      )}
      <TextField
        label="Имя"
        autoComplete="nickname"
        {...form.register('displayName')}
        error={!!form.formState.errors.displayName}
        helperText={form.formState.errors.displayName?.message}
      />
      <TextField
        label="Часовой пояс"
        {...form.register('timezone')}
        error={!!form.formState.errors.timezone}
        helperText={
          form.formState.errors.timezone?.message ??
          'Например Europe/Moscow. Время приёмов пищи относится к этому поясу.'
        }
      />
      <Typography component="h2" variant="h6">
        Обычное время приёмов пищи
      </Typography>
      {(Object.keys(meals) as (keyof typeof meals)[]).map((key) => (
        <TextField
          key={key}
          label={meals[key]}
          type="time"
          slotProps={{ inputLabel: { shrink: true } }}
          {...form.register(`mealTimes.${key}`)}
          error={!!form.formState.errors.mealTimes?.[key]}
          helperText={form.formState.errors.mealTimes?.[key]?.message}
        />
      ))}
      <Button
        type="submit"
        variant="contained"
        disabled={result.isLoading || !form.formState.isDirty}
      >
        {result.isLoading ? 'Сохраняем…' : 'Сохранить настройки'}
      </Button>
      <Typography variant="body2" color="text.secondary">
        Настройки применяются к будущим записям. История питания сохраняется.
      </Typography>
    </Stack>
  )
}
export function ProfilePage() {
  const session = useSession()
  const auth = useAuthClient()
  const profile = userApi.useGetMeQuery(session.userId ?? '', {
    skip: session.status !== 'authenticated',
  })
  useStaleRefresh({ ...profile, enabled: session.status === 'authenticated' })
  if (session.status === 'checking') return <CircularProgress aria-label="Восстанавливаем сессию" />
  if (session.status === 'offline' || session.status === 'unsupported')
    return (
      <Stack spacing={2}>
        <Alert severity="warning">{session.notice}</Alert>
        <Button
          onClick={() => {
            void auth.refresh()
          }}
        >
          Повторить восстановление
        </Button>
      </Stack>
    )
  if (session.status !== 'authenticated') return <Navigate to="/login" replace />
  if (profile.isLoading) return <CircularProgress aria-label="Загружаем профиль" />
  if (profile.error)
    return (
      <Alert
        severity="error"
        action={
          <Button
            onClick={() => {
              void profile.refetch()
            }}
          >
            Повторить
          </Button>
        }
      >
        {errorText(profile.error)}
      </Alert>
    )
  if (!profile.data) return null
  return (
    <ProfileEditor
      key={`${profile.data.id}:${profile.data.revision}`}
      user={profile.data}
      reload={profile.refetch}
    />
  )
}
