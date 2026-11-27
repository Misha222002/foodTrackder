import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router'
import { AppProviders } from '../../app/providers/AppProviders'
import { AppRoutes } from '../../app/router/AppRoutes'
import { createStore } from '../../app/store/store'
import { AuthClient } from '../../shared/auth/client'
import { server } from '../../test/setup'

it('registers, validates and confirms a code, then opens the real profile query', async () => {
  const auth = new AuthClient({ lock: (work) => work() })
  const store = createStore(auth)
  let requests = 0
  server.use(
    http.post('*/api/v1/auth/register', async ({ request }) => {
      requests++
      expect(await request.json()).toEqual({
        email: 'me@example.org',
        password: 'a long password 123',
      })
      return HttpResponse.json(
        {
          challengeId: 'challenge',
          expiresAt: new Date(Date.now() + 600_000).toISOString(),
          resendAvailableAt: new Date(Date.now() + 60_000).toISOString(),
        },
        { status: 202 },
      )
    }),
    http.post('*/api/v1/auth/verify-email', async ({ request }) => {
      expect(await request.json()).toEqual({ challengeId: 'challenge', code: '123456' })
      return HttpResponse.json({
        status: 'authenticated',
        accessToken: 'memory-access',
        userId: 'me',
        tokenType: 'Bearer',
        expiresIn: 900,
        expiresAt: new Date(Date.now() + 900_000).toISOString(),
      })
    }),
    http.post('*/api/v1/auth/logout', () => new HttpResponse(null, { status: 204 })),
    http.get('*/api/v1/users/me', ({ request }) => {
      expect(request.headers.get('Authorization')).toBe('Bearer memory-access')
      return HttpResponse.json({
        id: 'me',
        email: 'me@example.org',
        timezone: 'UTC',
        displayName: '',
        revision: 1,
        mealTimes: { breakfast: '08:00', lunch: '13:00', dinner: '19:00', snack: '16:00' },
      })
    }),
  )
  render(
    <AppProviders store={store}>
      <MemoryRouter initialEntries={['/register']}>
        <AppRoutes />
      </MemoryRouter>
    </AppProviders>,
  )
  await userEvent.click(screen.getByRole('button', { name: 'Получить код' }))
  expect(requests).toBe(0)
  expect(await screen.findByText('Введите email')).toBeVisible()
  expect(screen.getByLabelText('Email')).toHaveFocus()
  await userEvent.type(screen.getByLabelText('Email'), 'me@example.org')
  await userEvent.type(screen.getByLabelText('Пароль'), 'a long password 123')
  await userEvent.click(screen.getByRole('button', { name: 'Получить код' }))
  expect(await screen.findByRole('heading', { name: 'Подтвердить почту' })).toBeVisible()
  expect(screen.getByRole('button', { name: /Повторить через/ })).toBeDisabled()
  await userEvent.type(screen.getByLabelText('Код из письма'), '123456')
  await userEvent.click(screen.getByRole('button', { name: 'Подтвердить и войти' }))
  expect(await screen.findByText('me@example.org')).toBeVisible()
  expect(JSON.stringify(store.getState())).not.toContain('memory-access')
  await userEvent.click(screen.getByRole('button', { name: 'Выйти' }))
  await screen.findByRole('heading', { name: 'Войти' })
  await userEvent.click(screen.getByRole('link', { name: 'Создать аккаунт' }))
  expect(await screen.findByLabelText('Email')).toHaveValue('')
  expect(screen.getByLabelText('Пароль')).toHaveValue('')
})
