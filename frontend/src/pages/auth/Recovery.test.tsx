import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router'
import { AppProviders } from '../../app/providers/AppProviders'
import { AppRoutes } from '../../app/router/AppRoutes'
import { createStore } from '../../app/store/store'
import { AuthClient } from '../../shared/auth/client'
import { server } from '../../test/setup'

it('recovers by code and new password and returns to ordinary login', async () => {
  const auth = new AuthClient({ lock: (work) => work() })
  let resets = 0
  server.use(
    http.post('*/api/v1/auth/password/forgot', () =>
      HttpResponse.json(
        {
          challengeId: 'reset',
          expiresAt: new Date(Date.now() + 600_000).toISOString(),
          resendAvailableAt: new Date(Date.now() + 60_000).toISOString(),
        },
        { status: 202 },
      ),
    ),
    http.post('*/api/v1/auth/password/reset', async ({ request }) => {
      resets++
      expect(await request.json()).toEqual({
        challengeId: 'reset',
        code: '123456',
        newPassword: 'brand new password 123',
      })
      return resets === 1
        ? HttpResponse.json({ message: 'Срок кода истёк' }, { status: 400 })
        : HttpResponse.json({ status: 'password_reset' })
    }),
  )
  render(
    <AppProviders store={createStore(auth)}>
      <MemoryRouter initialEntries={['/forgot-password']}>
        <AppRoutes />
      </MemoryRouter>
    </AppProviders>,
  )
  await userEvent.type(screen.getByLabelText('Email'), 'me@example.org')
  await userEvent.click(screen.getByRole('button', { name: 'Получить код' }))
  expect(await screen.findByRole('heading', { name: 'Новый пароль' })).toBeVisible()
  await userEvent.type(screen.getByLabelText('Код из письма'), '123456')
  await userEvent.type(screen.getByLabelText('Новый пароль'), 'brand new password 123')
  await userEvent.click(screen.getByRole('button', { name: 'Сохранить пароль' }))
  expect(await screen.findByText('Срок кода истёк')).toBeVisible()
  expect(screen.getByLabelText('Новый пароль')).toHaveValue('brand new password 123')
  await userEvent.click(screen.getByRole('button', { name: 'Сохранить пароль' }))
  expect(await screen.findByRole('heading', { name: 'Войти' })).toBeVisible()
  expect(screen.getByLabelText('Пароль')).toHaveValue('')
  expect(auth.snapshot().status).toBe('guest')
})

it.each([
  {
    status: 404,
    code: 'EMAIL_NOT_FOUND',
    message: 'Аккаунт с таким email не найден',
    helper: 'Проверьте адрес или зарегистрируйтесь',
  },
  {
    status: 409,
    code: 'EMAIL_NOT_VERIFIED',
    message: 'Сначала подтвердите почту аккаунта',
    helper: 'Войдите с паролем регистрации и запросите код подтверждения',
  },
])(
  'keeps the recovery form on $code and allows correcting the email',
  async ({ status, code, message, helper }) => {
    const auth = new AuthClient({ lock: (work) => work() })
    let requests = 0
    server.use(
      http.post('*/api/v1/auth/password/forgot', async ({ request }) => {
        requests++
        const body = (await request.json()) as { email: string }
        if (body.email === 'missing@example.org')
          return HttpResponse.json(
            {
              code,
              message,
              details: { fields: [{ path: 'email', message: helper }] },
              requestId: 'test',
            },
            { status },
          )
        expect(body.email).toBe('existing@example.org')
        return HttpResponse.json(
          {
            challengeId: 'known-account',
            expiresAt: new Date(Date.now() + 600_000).toISOString(),
            resendAvailableAt: new Date(Date.now() + 60_000).toISOString(),
          },
          { status: 202 },
        )
      }),
    )
    render(
      <AppProviders store={createStore(auth)}>
        <MemoryRouter initialEntries={['/forgot-password']}>
          <AppRoutes />
        </MemoryRouter>
      </AppProviders>,
    )
    await userEvent.type(screen.getByLabelText('Email'), 'missing@example.org')
    await userEvent.click(screen.getByRole('button', { name: 'Получить код' }))
    expect(await screen.findByText(message)).toBeVisible()
    expect(screen.getByRole('heading', { name: 'Восстановить пароль' })).toBeVisible()
    expect(screen.queryByRole('heading', { name: 'Новый пароль' })).not.toBeInTheDocument()
    expect(screen.getByLabelText('Email')).toHaveValue('missing@example.org')
    expect(screen.getByLabelText('Email')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByLabelText('Email')).toHaveAccessibleDescription(helper)
    expect(screen.getByLabelText('Email')).toHaveFocus()
    if (status === 404)
      expect(screen.getByRole('link', { name: 'Создать аккаунт с этим email' })).toBeVisible()
    else
      expect(
        screen.queryByRole('link', { name: 'Создать аккаунт с этим email' }),
      ).not.toBeInTheDocument()
    await userEvent.clear(screen.getByLabelText('Email'))
    expect(screen.queryByText(message)).not.toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Email'), 'existing@example.org')
    await userEvent.click(screen.getByRole('button', { name: 'Получить код' }))
    expect(await screen.findByRole('heading', { name: 'Новый пароль' })).toBeVisible()
    expect(screen.getByText('existing@example.org')).toBeVisible()
    expect(requests).toBe(2)
  },
)

it('offers signup with the unknown email already filled in', async () => {
  const auth = new AuthClient({ lock: (work) => work() })
  server.use(
    http.post('*/api/v1/auth/password/forgot', () =>
      HttpResponse.json(
        {
          code: 'EMAIL_NOT_FOUND',
          message: 'Аккаунт с таким email не найден',
          details: {},
          requestId: 'test',
        },
        { status: 404 },
      ),
    ),
  )
  render(
    <AppProviders store={createStore(auth)}>
      <MemoryRouter initialEntries={['/forgot-password']}>
        <AppRoutes />
      </MemoryRouter>
    </AppProviders>,
  )
  await userEvent.type(screen.getByLabelText('Email'), 'new-account@example.org')
  await userEvent.click(screen.getByRole('button', { name: 'Получить код' }))
  await userEvent.click(await screen.findByRole('link', { name: 'Создать аккаунт с этим email' }))
  expect(await screen.findByRole('heading', { name: 'Создать аккаунт' })).toBeVisible()
  expect(screen.getByLabelText('Email')).toHaveValue('new-account@example.org')
  expect(screen.getByLabelText('Пароль')).toHaveValue('')
})
