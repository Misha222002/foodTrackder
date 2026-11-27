import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router'
import { AppProviders } from '../../app/providers/AppProviders'
import { AppRoutes } from '../../app/router/AppRoutes'
import { createStore } from '../../app/store/store'
import { AuthClient } from '../../shared/auth/client'
import { server } from '../../test/setup'

it('waits for bootstrap, edits settings, shows conflict and reloads the current version', async () => {
  const auth = new AuthClient({ lock: (work) => work() })
  let user = {
    id: 'me',
    email: 'me@example.org',
    displayName: 'Михаил',
    timezone: 'UTC',
    revision: 1,
    mealTimes: { breakfast: '08:00', lunch: '13:00', dinner: '19:00', snack: '16:00' },
  }
  let edits = 0
  let finishRestore: (() => void) | undefined
  const restored = new Promise<void>((resolve) => {
    finishRestore = resolve
  })
  server.use(
    http.post('*/api/v1/auth/refresh', async () => {
      await restored
      return HttpResponse.json({
        status: 'authenticated',
        userId: 'me',
        accessToken: 'access',
        tokenType: 'Bearer',
        expiresAt: new Date(Date.now() + 900_000).toISOString(),
        expiresIn: 900,
      })
    }),
    http.get('*/api/v1/users/me', () => HttpResponse.json(user)),
    http.put('*/api/v1/users/me', async ({ request }) => {
      edits++
      expect(request.headers.get('If-Match')).toBe('"profile-1"')
      const values = (await request.json()) as Partial<typeof user>
      expect(values.timezone).toBe('Europe/Moscow')
      if (edits === 1) return HttpResponse.error()
      user = { ...user, displayName: 'Серверное имя', revision: 2 }
      return HttpResponse.json(
        { code: 'PROFILE_REVISION_CONFLICT', message: 'Профиль изменён в другом окне' },
        { status: 412 },
      )
    }),
  )
  render(
    <AppProviders store={createStore(auth)}>
      <MemoryRouter initialEntries={['/profile']}>
        <AppRoutes />
      </MemoryRouter>
    </AppProviders>,
  )
  expect(screen.getByLabelText('Восстанавливаем сессию')).toBeVisible()
  expect(screen.queryByRole('heading', { name: 'Войти' })).not.toBeInTheDocument()
  finishRestore!()
  expect(await screen.findByLabelText('Имя')).toHaveValue('Михаил')
  await userEvent.clear(screen.getByLabelText('Часовой пояс'))
  await userEvent.type(screen.getByLabelText('Часовой пояс'), 'Europe/Moscow')
  await userEvent.click(screen.getByRole('button', { name: 'Сохранить настройки' }))
  expect(await screen.findByText(/Не удалось связаться/)).toBeVisible()
  expect(screen.getByLabelText('Часовой пояс')).toHaveValue('Europe/Moscow')
  await userEvent.click(screen.getByRole('button', { name: 'Сохранить настройки' }))
  expect(await screen.findByText('Профиль изменён в другом окне')).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Загрузить актуальный профиль' }))
  await waitFor(() => expect(screen.getByLabelText('Имя')).toHaveValue('Серверное имя'))
})
