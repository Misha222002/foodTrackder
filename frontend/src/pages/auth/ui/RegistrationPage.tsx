import { useEffect, useState } from 'react'
import { Alert, Button, Link, Stack, TextField, Typography } from '@mui/material'
import { Link as RouterLink, useNavigate, useSearchParams } from 'react-router'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { PasswordField } from '../../../shared/ui/PasswordField'
import { applyFormErrors } from '../../../shared/api/form-errors'
import { errorText } from '../../../shared/api/error-text'
import {
  MailDeliveryNotice,
  authApi,
  type Challenge,
  useAuthDrafts,
  CodeRecipient,
} from '../../../features/auth'

const credentials = z.object({
  email: z.email('Введите email'),
  password: z.string().min(12, 'Не менее 12 символов').max(128, 'Не более 128 символов'),
})
const codeSchema = z.object({ code: z.string().regex(/^\d{6}$/, 'Введите 6 цифр из письма') })
export function RegistrationPage() {
  const [submit, result] = authApi.useRegisterMutation()
  const navigate = useNavigate()
  const drafts = useAuthDrafts()
  const alreadyRegistered =
    result.error &&
    'data' in result.error &&
    (result.error.data as { code?: string })?.code === 'EMAIL_ALREADY_REGISTERED'
  const pending = Object.values(drafts.challenges)
    .reverse()
    .find((request) => request.returnTo === '/register' && request.email === drafts.emails.register)
  const form = useForm<z.infer<typeof credentials>>({
    resolver: zodResolver(credentials),
    defaultValues: { email: drafts.emails.register, password: '' },
  })
  return (
    <Stack
      component="form"
      noValidate
      spacing={2}
      maxWidth={440}
      mx="auto"
      onSubmit={form.handleSubmit(async (values) => {
        try {
          const challenge = await submit(values).unwrap()
          drafts.rememberChallenge({ ...challenge, email: values.email, returnTo: '/register' })
          form.resetField('password')
          void navigate(`/verify-email?challenge=${challenge.challengeId}`)
        } catch (error) {
          applyFormErrors(error, form.setError, ['email', 'password'])
        }
      })}
    >
      <Typography variant="h4" component="h1">
        Создать аккаунт
      </Typography>
      <MailDeliveryNotice />
      <Typography>Подтвердите почту шестизначным кодом. Пароль — от 12 до 128 символов.</Typography>
      {result.error && <Alert severity="error">{errorText(result.error)}</Alert>}
      <TextField
        label="Email"
        type="email"
        autoComplete="email"
        {...form.register('email', {
          onChange: (event) => {
            drafts.setEmail('register', event.target.value)
            if (result.isError) result.reset()
          },
        })}
        error={!!form.formState.errors.email}
        helperText={form.formState.errors.email?.message}
      />
      <PasswordField
        label="Пароль"
        autoComplete="new-password"
        {...form.register('password')}
        error={!!form.formState.errors.password}
        helperText={form.formState.errors.password?.message}
      />
      <Button type="submit" variant="contained" disabled={result.isLoading}>
        {result.isLoading ? 'Отправляем код…' : 'Получить код'}
      </Button>
      {pending && !alreadyRegistered && (
        <Link component={RouterLink} to={`/verify-email?challenge=${pending.challengeId}`}>
          Продолжить подтверждение почты
        </Link>
      )}
      <Link
        component={RouterLink}
        to="/login"
        onClick={() => drafts.setEmail('login', form.getValues('email'))}
      >
        {alreadyRegistered ? 'Войти с этим email' : 'Уже есть аккаунт? Войти'}
      </Link>
      {alreadyRegistered && (
        <Link
          component={RouterLink}
          to="/forgot-password"
          onClick={() => drafts.setEmail('forgot', form.getValues('email'))}
        >
          Восстановить пароль
        </Link>
      )}
    </Stack>
  )
}
export function VerificationPage() {
  const [params] = useSearchParams()
  const challengeId = params.get('challenge') ?? ''
  const [verify, verification] = authApi.useVerifyEmailMutation()
  const [resend, resending] = authApi.useResendVerificationMutation()
  const drafts = useAuthDrafts()
  const saved = drafts.challenges[challengeId]
  const [resentChallenge, setResentChallenge] = useState<Challenge>()
  const challenge = resentChallenge?.challengeId === challengeId ? resentChallenge : saved
  const [seconds, setSeconds] = useState(0)
  const navigate = useNavigate()
  const form = useForm<z.infer<typeof codeSchema>>({ resolver: zodResolver(codeSchema) })
  useEffect(() => {
    const update = () =>
      setSeconds(
        Math.max(
          0,
          Math.ceil((Date.parse(challenge?.resendAvailableAt ?? '') - Date.now()) / 1000),
        ) || 0,
      )
    update()
    const timer = setInterval(update, 1000)
    return () => clearInterval(timer)
  }, [challenge])
  if (!challengeId)
    return (
      <Alert severity="warning">
        Сначала{' '}
        <Link component={RouterLink} to="/register">
          зарегистрируйтесь
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
      onSubmit={form.handleSubmit(async ({ code }) => {
        try {
          await verify({ challengeId, code }).unwrap()
          drafts.clear()
          form.reset()
          void navigate('/profile', { replace: true })
        } catch (error) {
          applyFormErrors(error, form.setError, ['code'])
        }
      })}
    >
      <Typography variant="h4" component="h1">
        Подтвердить почту
      </Typography>
      <MailDeliveryNotice />
      <CodeRecipient email={saved?.email} />
      <Typography>
        Введите код из письма. Если письмо не пришло, проверьте спам или запросите повторную
        отправку.
      </Typography>
      <Typography variant="body2" color="text.secondary">
        Если вы уже регистрировались с этим email, перейдите ко входу с паролем первой регистрации,
        чтобы продолжить подтверждение.
      </Typography>
      {(verification.error || resending.error) && (
        <Alert severity="error">{errorText(verification.error ?? resending.error)}</Alert>
      )}
      {challenge && (
        <Alert severity="success">
          Код запрошен. Действует до {new Date(challenge.expiresAt).toLocaleTimeString()}.
        </Alert>
      )}
      <TextField
        label="Код из письма"
        autoComplete="one-time-code"
        slotProps={{ htmlInput: { inputMode: 'numeric', maxLength: 6 } }}
        {...form.register('code')}
        error={!!form.formState.errors.code}
        helperText={form.formState.errors.code?.message}
      />
      <Button
        type="submit"
        variant="contained"
        disabled={verification.isLoading || resending.isLoading}
      >
        {verification.isLoading ? 'Подтверждаем…' : 'Подтвердить и войти'}
      </Button>
      <Button
        disabled={verification.isLoading || resending.isLoading || seconds > 0}
        onClick={async () => {
          try {
            const updated = await resend({ challengeId }).unwrap()
            setResentChallenge(updated)
            verification.reset()
            form.resetField('code')
            if (saved) drafts.rememberChallenge({ ...saved, ...updated })
          } catch {
            /* rendered */
          }
        }}
      >
        {resending.isLoading
          ? 'Отправляем…'
          : seconds > 0
            ? `Повторить через ${seconds} сек.`
            : 'Отправить код ещё раз'}
      </Button>
      {saved?.returnTo === '/register' && (
        <Link component={RouterLink} to="/register">
          Вернуться к регистрации
        </Link>
      )}
      <Link component={RouterLink} to="/login">
        Вернуться ко входу
      </Link>
    </Stack>
  )
}
