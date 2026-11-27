import { Alert, Button, Link, Stack, TextField, Typography } from '@mui/material'
import { Link as RouterLink, useNavigate } from 'react-router'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { PasswordField } from '../../../shared/ui/PasswordField'
import { applyFormErrors } from '../../../shared/api/form-errors'
import { authApi, useAuthDrafts } from '../../../features/auth'
import { errorText } from '../../../shared/api/error-text'

const schema = z.object({
  email: z.email('Введите email'),
  password: z.string().min(1, 'Введите пароль').max(128),
})
export function LoginPage() {
  const [login, result] = authApi.useLoginMutation()
  const navigate = useNavigate()
  const drafts = useAuthDrafts()
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { email: drafts.emails.login, password: '' },
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
          const response = await login(values).unwrap()
          form.resetField('password')
          if (response.status === 'email_verification_required') {
            drafts.rememberChallenge({ ...response, email: values.email, returnTo: '/login' })
            void navigate(`/verify-email?challenge=${response.challengeId}`)
          } else {
            drafts.clear()
            void navigate('/profile', { replace: true })
          }
        } catch (error) {
          applyFormErrors(error, form.setError, ['email', 'password'])
        }
      })}
    >
      <Typography component="h1" variant="h4">
        Войти
      </Typography>
      {result.error && <Alert severity="error">{errorText(result.error)}</Alert>}
      <TextField
        label="Email"
        type="email"
        autoComplete="email"
        {...form.register('email', {
          onChange: (event) => drafts.setEmail('login', event.target.value),
        })}
        error={!!form.formState.errors.email}
        helperText={form.formState.errors.email?.message}
      />
      <PasswordField
        label="Пароль"
        autoComplete="current-password"
        {...form.register('password')}
        error={!!form.formState.errors.password}
        helperText={form.formState.errors.password?.message}
      />
      <Button type="submit" variant="contained" disabled={result.isLoading}>
        {result.isLoading ? 'Входим…' : 'Войти'}
      </Button>
      <Link component={RouterLink} to="/forgot-password">
        Забыли пароль?
      </Link>
      <Link component={RouterLink} to="/register">
        Создать аккаунт
      </Link>
    </Stack>
  )
}
