import { Alert, Button, Link, Stack, TextField, Typography } from '@mui/material'
import { Link as RouterLink, useNavigate, useSearchParams } from 'react-router'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { PasswordField } from '../../../shared/ui/PasswordField'
import { applyFormErrors } from '../../../shared/api/form-errors'
import { MailDeliveryNotice, authApi, useAuthDrafts, CodeRecipient } from '../../../features/auth'
import { errorText } from '../../../shared/api/error-text'

const emailSchema = z.object({ email: z.email('Введите email') })
const resetSchema = z.object({
  code: z.string().regex(/^\d{6}$/, 'Введите 6 цифр из письма'),
  newPassword: z.string().min(12, 'Не менее 12 символов').max(128, 'Не более 128 символов'),
})
export function ForgotPasswordPage() {
  const [send, result] = authApi.useForgotPasswordMutation()
  const navigate = useNavigate()
  const drafts = useAuthDrafts()
  const form = useForm<z.infer<typeof emailSchema>>({
    resolver: zodResolver(emailSchema),
    defaultValues: { email: drafts.emails.forgot },
  })
  const missingAccount =
    result.error &&
    'data' in result.error &&
    (result.error.data as { code?: string })?.code === 'EMAIL_NOT_FOUND'
  return (
    <Stack
      component="form"
      noValidate
      spacing={2}
      maxWidth={440}
      mx="auto"
      onSubmit={form.handleSubmit(async (body) => {
        try {
          const challenge = await send(body).unwrap()
          drafts.rememberChallenge({
            ...challenge,
            email: body.email,
            returnTo: '/forgot-password',
          })
          void navigate(`/reset-password?challenge=${challenge.challengeId}`)
        } catch (error) {
          applyFormErrors(error, form.setError, ['email'])
        }
      })}
    >
      <Typography component="h1" variant="h4">
        Восстановить пароль
      </Typography>
      <MailDeliveryNotice />
      <Typography>Введите email аккаунта — отправим код для смены пароля.</Typography>
      {result.error && <Alert severity="error">{errorText(result.error)}</Alert>}
      <TextField
        label="Email"
        type="email"
        autoComplete="email"
        {...form.register('email', {
          onChange: (event) => {
            drafts.setEmail('forgot', event.target.value)
            if (result.isError) result.reset()
          },
        })}
        error={!!form.formState.errors.email}
        helperText={form.formState.errors.email?.message}
      />
      <Button type="submit" variant="contained" disabled={result.isLoading}>
        {result.isLoading ? 'Отправляем код…' : 'Получить код'}
      </Button>
      {missingAccount && (
        <Link
          component={RouterLink}
          to="/register"
          onClick={() => drafts.setEmail('register', form.getValues('email'))}
        >
          Создать аккаунт с этим email
        </Link>
      )}
      <Link component={RouterLink} to="/login">
        Вернуться ко входу
      </Link>
    </Stack>
  )
}
export function ResetPasswordPage() {
  const [params] = useSearchParams()
  const challengeId = params.get('challenge') ?? ''
  const drafts = useAuthDrafts()
  const state = drafts.challenges[challengeId]
  const [reset, result] = authApi.useResetPasswordMutation()
  const navigate = useNavigate()
  const form = useForm<z.infer<typeof resetSchema>>({ resolver: zodResolver(resetSchema) })
  if (!challengeId)
    return (
      <Alert severity="warning">
        Сначала{' '}
        <Link component={RouterLink} to="/forgot-password">
          запросите код
        </Link>
        .
      </Alert>
    )
  return (
    <Stack
      component="form"
      noValidate
      spacing={2}
      maxWidth={440}
      mx="auto"
      onSubmit={form.handleSubmit(async (values) => {
        try {
          await reset({ ...values, challengeId }).unwrap()
          drafts.clear()
          form.reset()
          void navigate('/login', { replace: true })
        } catch (error) {
          applyFormErrors(error, form.setError, ['code', 'newPassword'])
        }
      })}
    >
      <Typography component="h1" variant="h4">
        Новый пароль
      </Typography>
      <MailDeliveryNotice />
      <CodeRecipient email={state?.email} />
      <Typography>
        Введите код из письма и новый пароль. После смены пароля все сеансы завершатся. Затем
        войдите заново.
      </Typography>
      {state?.expiresAt && (
        <Typography>Код действует до {new Date(state.expiresAt).toLocaleTimeString()}.</Typography>
      )}
      {result.error && <Alert severity="error">{errorText(result.error)}</Alert>}
      <TextField
        label="Код из письма"
        autoComplete="one-time-code"
        slotProps={{ htmlInput: { inputMode: 'numeric', maxLength: 6 } }}
        {...form.register('code')}
        error={!!form.formState.errors.code}
        helperText={form.formState.errors.code?.message}
      />
      <PasswordField
        label="Новый пароль"
        autoComplete="new-password"
        {...form.register('newPassword')}
        error={!!form.formState.errors.newPassword}
        helperText={form.formState.errors.newPassword?.message}
      />
      <Button type="submit" variant="contained" disabled={result.isLoading}>
        {result.isLoading ? 'Сохраняем…' : 'Сохранить пароль'}
      </Button>
      <Link component={RouterLink} to="/forgot-password">
        Запросить новый код
      </Link>
      <Link component={RouterLink} to="/login">
        Вернуться ко входу
      </Link>
    </Stack>
  )
}
