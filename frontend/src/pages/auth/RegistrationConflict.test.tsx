import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router'
import { AppProviders } from '../../app/providers/AppProviders'
import { AppRoutes } from '../../app/router/AppRoutes'
import { createStore } from '../../app/store/store'
import { AuthClient } from '../../shared/auth/client'
import { server } from '../../test/setup'

const password = 'a long password 123'
const conflict = () =>
  HttpResponse.json(
    {
      code: 'EMAIL_ALREADY_REGISTERED',
      message: 'Аккаунт с таким email уже зарегистрирован',
      details: {
        fields: [
          {
            path: 'email',
            type: 'email_already_registered',
            message: 'Войдите в аккаунт или восстановите пароль',
          },
        ],
      },
      requestId: 'test',
    },
    { status: 409 },
  )

function openSignup() {
  const auth = new AuthClient({ lock: (work) => work() })
  const store = createStore(auth)
  render(
    <AppProviders store={store}>
      <MemoryRouter initialEntries={['/register']}>
        <AppRoutes />
      </MemoryRouter>
    </AppProviders>,
  )
  return { auth, store }
}
async function fillSignup(email: string) {
  await userEvent.type(screen.getByLabelText('Email'), email)
  await userEvent.type(screen.getByLabelText('Пароль'), password)
}

it.each(['existing@example.org', 'EXISTING@EXAMPLE.ORG'])(
  'shows the duplicate error for %s, preserves input, prevents duplicate submits and allows correction',
  async (email) => {
    let requests = 0
    let finish: (() => void) | undefined
    const pending = new Promise<void>((resolve) => {
      finish = resolve
    })
    server.use(
      http.post('*/api/v1/auth/register', async ({ request }) => {
        requests++
        const body = (await request.json()) as { email: string; password: string }
        expect(body.password).toBe(password)
        if (body.email.toLowerCase() === 'existing@example.org') {
          expect(body.email).toBe(email)
          await pending
          return conflict()
        }
        expect(body.email).toBe('available@example.org')
        return HttpResponse.json(
          {
            challengeId: 'available',
            expiresAt: new Date(Date.now() + 600_000).toISOString(),
            resendAvailableAt: new Date(Date.now() + 60_000).toISOString(),
          },
          { status: 202 },
        )
      }),
    )
    const { auth } = openSignup()
    await fillSignup(email)
    await userEvent.click(screen.getByRole('button', { name: 'Получить код' }))
    await waitFor(() => expect(requests).toBe(1))
    const sending = screen.getByRole('button', { name: 'Отправляем код…' })
    expect(sending).toBeDisabled()
    await userEvent.keyboard('{Enter}')
    expect(requests).toBe(1)
    finish!()
    expect(await screen.findByText('Аккаунт с таким email уже зарегистрирован')).toBeVisible()
    expect(screen.getByRole('heading', { name: 'Создать аккаунт' })).toBeVisible()
    expect(screen.queryByRole('heading', { name: 'Подтвердить почту' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Код из письма')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Email')).toHaveValue(email)
    expect(screen.getByLabelText('Email')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByLabelText('Email')).toHaveAccessibleDescription(
      'Войдите в аккаунт или восстановите пароль',
    )
    expect(screen.getByLabelText('Email')).toHaveFocus()
    expect(screen.getByLabelText('Пароль')).toHaveValue(password)
    expect(screen.getByRole('link', { name: 'Войти с этим email' })).toBeVisible()
    expect(screen.getByRole('link', { name: 'Восстановить пароль' })).toBeVisible()
    expect(auth.access()).toBeUndefined()
    await userEvent.clear(screen.getByLabelText('Email'))
    expect(screen.queryByText('Аккаунт с таким email уже зарегистрирован')).not.toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Email'), 'available@example.org')
    await userEvent.click(screen.getByRole('button', { name: 'Получить код' }))
    expect(await screen.findByRole('heading', { name: 'Подтвердить почту' })).toBeVisible()
    expect(screen.getByText('available@example.org')).toBeVisible()
    expect(requests).toBe(2)
  },
)

it('offers normal login for a registered email; wrong password fails and the original password works', async () => {
  let registrations = 0
  let logins = 0
  server.use(
    http.post('*/api/v1/auth/register', () => {
      registrations++
      return conflict()
    }),
    http.post('*/api/v1/auth/login', async ({ request }) => {
      logins++
      const body = (await request.json()) as { email: string; password: string }
      expect(body.email).toBe('existing@example.org')
      if (body.password !== password)
        return HttpResponse.json(
          {
            code: 'INVALID_CREDENTIALS',
            message: 'Неверный email или пароль',
            details: {},
            requestId: 'test',
          },
          { status: 401 },
        )
      return HttpResponse.json({
        status: 'authenticated',
        accessToken: 'normal-login-access',
        userId: 'me',
        tokenType: 'Bearer',
        expiresIn: 900,
        expiresAt: new Date(Date.now() + 900_000).toISOString(),
      })
    }),
    http.get('*/api/v1/users/me', ({ request }) => {
      expect(request.headers.get('Authorization')).toBe('Bearer normal-login-access')
      return HttpResponse.json({
        id: 'me',
        email: 'existing@example.org',
        emailVerifiedAt: new Date().toISOString(),
        role: 'USER',
        displayName: '',
        timezone: 'UTC',
        revision: 1,
        mealTimes: { breakfast: '08:00', lunch: '13:00', dinner: '19:00', snack: '16:00' },
      })
    }),
  )
  const { auth, store } = openSignup()
  await fillSignup('existing@example.org')
  await userEvent.click(screen.getByRole('button', { name: 'Получить код' }))
  await userEvent.click(await screen.findByRole('link', { name: 'Войти с этим email' }))
  expect(await screen.findByRole('heading', { name: 'Войти' })).toBeVisible()
  expect(screen.getByLabelText('Email')).toHaveValue('existing@example.org')
  expect(screen.getByLabelText('Пароль')).toHaveValue('')
  await userEvent.type(screen.getByLabelText('Пароль'), 'wrong password')
  await userEvent.click(screen.getByRole('button', { name: 'Войти' }))
  expect(await screen.findByText('Неверный email или пароль')).toBeVisible()
  expect(screen.getByRole('heading', { name: 'Войти' })).toBeVisible()
  await userEvent.clear(screen.getByLabelText('Пароль'))
  await userEvent.type(screen.getByLabelText('Пароль'), password)
  await userEvent.click(screen.getByRole('button', { name: 'Войти' }))
  expect(await screen.findByRole('heading', { name: 'Профиль' })).toBeVisible()
  expect(screen.getByText('existing@example.org')).toBeVisible()
  expect(screen.queryByLabelText('Код из письма')).not.toBeInTheDocument()
  expect(auth.snapshot().status).toBe('authenticated')
  expect(JSON.stringify(store.getState())).not.toContain('normal-login-access')
  expect(registrations).toBe(1)
  expect(logins).toBe(2)
})

it('offers password recovery with the registered email already filled without sending automatically', async () => {
  let recoveryRequests = 0
  server.use(
    http.post('*/api/v1/auth/register', conflict),
    http.post('*/api/v1/auth/password/forgot', () => {
      recoveryRequests++
      return HttpResponse.json({})
    }),
  )
  openSignup()
  await fillSignup('existing@example.org')
  await userEvent.click(screen.getByRole('button', { name: 'Получить код' }))
  await userEvent.click(await screen.findByRole('link', { name: 'Восстановить пароль' }))
  expect(await screen.findByRole('heading', { name: 'Восстановить пароль' })).toBeVisible()
  expect(screen.getByLabelText('Email')).toHaveValue('existing@example.org')
  expect(screen.queryByLabelText('Пароль')).not.toBeInTheDocument()
  expect(recoveryRequests).toBe(0)
})
