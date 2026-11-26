import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { delay, http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router'
import type { ApiError, HealthResponse } from '../shared/api'
import { server } from '../test/setup'
import { AppProviders } from './providers/AppProviders'
import { AppRoutes } from './router/AppRoutes'
import { createStore } from './store/store'

function openApp(path = '/') {
  const store = createStore()
  const view = render(
    <AppProviders store={store}>
      <MemoryRouter initialEntries={[path]}><AppRoutes /></MemoryRouter>
    </AppProviders>,
  )
  return { ...view, store }
}

it('shows loading, then a response received through the API layer', async () => {
  server.use(http.get('*/api/v1/health', async () => {
    await delay(80)
    return HttpResponse.json({ status: 'ok', database: 'ok' } satisfies HealthResponse)
  }))
  openApp()
  expect(screen.getByRole('status')).toHaveTextContent('Проверяем соединение')
  expect(screen.getByRole('button', { name: 'Проверить снова' })).toBeDisabled()
  expect(await screen.findByText('Сервис доступен')).toBeVisible()
})

it.each(['server', 'network'])('allows retry after a %s error', async (kind) => {
  server.use(http.get('*/api/v1/health', () => kind === 'network'
    ? HttpResponse.error()
    : HttpResponse.json({
      code: 'DATABASE_UNAVAILABLE',
      message: 'Сервис временно недоступен. Попробуйте позже.',
      details: {},
      requestId: 'test-request',
    } satisfies ApiError, { status: 503 })))
  openApp()
  expect(await screen.findByRole('alert')).toHaveTextContent('Не удалось связаться')
  server.resetHandlers()
  await userEvent.click(screen.getByRole('button', { name: 'Проверить снова' }))
  expect(await screen.findByText('Сервис доступен')).toBeVisible()
})

it('returns to the home page from an unknown route', async () => {
  openApp('/missing')
  expect(screen.getByRole('heading', { name: 'Страница не найдена' })).toBeVisible()
  await userEvent.click(screen.getByRole('link', { name: 'На главную' }))
  expect(await screen.findByText('Сервис доступен')).toBeVisible()
})

it('uses fresh cache on remount and refreshes stale cache on remount', async () => {
  let requests = 0
  server.use(http.get('*/api/v1/health', () => {
    requests++
    return HttpResponse.json({ status: 'ok', database: 'ok' } satisfies HealthResponse)
  }))
  const { store, unmount } = openApp()
  await screen.findByText('Сервис доступен')
  unmount()
  function remount() {
    return render(<AppProviders store={store}><MemoryRouter><AppRoutes /></MemoryRouter></AppProviders>)
  }
  const next = remount()
  await screen.findByText('Сервис доступен')
  expect(requests).toBe(1)
  next.unmount()
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(Date.now() + 31_000)
  remount()
  await waitFor(() => expect(requests).toBe(2))
  await screen.findByText('Сервис доступен')
})

it.each(['focus', 'online'])('checks response age on %s', async (event) => {
  let requests = 0
  server.use(http.get('*/api/v1/health', () => {
    requests++
    return HttpResponse.json({ status: 'ok', database: 'ok' } satisfies HealthResponse)
  }))
  openApp()
  await screen.findByText('Сервис доступен')
  fireEvent(window, new Event(event))
  expect(requests).toBe(1)
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(Date.now() + 31_000)
  fireEvent(window, new Event(event))
  await waitFor(() => expect(requests).toBe(2))
  await screen.findByText('Сервис доступен')
})
