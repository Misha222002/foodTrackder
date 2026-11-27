import { delay, http, HttpResponse } from 'msw'
import { createStore } from '../../app/store/store'
import { baseApi } from '../api/base-api'
import { userApi } from '../../entities/user'
import { authApi } from '../../features/auth'
import { server } from '../../test/setup'
import { AuthClient } from './client'

const credentials = (accessToken: string, userId = 'me') => ({
  status: 'authenticated' as const,
  accessToken,
  userId,
  tokenType: 'Bearer' as const,
  expiresIn: 900,
  expiresAt: new Date(Date.now() + 900_000).toISOString(),
})
function client() {
  return new AuthClient({ lock: (work) => work() })
}
const testsApi = baseApi.injectEndpoints({
  endpoints: (build) => ({
    another: build.query<unknown, void>({ query: () => '/another' }),
  }),
})

it('restores before personal data and keeps credentials outside Redux', async () => {
  const auth = client()
  const store = createStore(auth)
  server.use(
    http.post('*/api/v1/auth/refresh', async () => {
      await delay(40)
      return HttpResponse.json(credentials('restored'))
    }),
  )
  const pending = auth.refresh()
  expect(auth.snapshot().status).toBe('checking')
  await pending
  expect(auth.access()).toBe('restored')
  expect(auth.snapshot().status).toBe('authenticated')
  expect(JSON.stringify(store.getState())).not.toContain('restored')
})

it('shares one refresh for parallel 401s and retries each original only once', async () => {
  const auth = client()
  const store = createStore(auth)
  auth.accept(credentials('old'))
  let refreshes = 0
  let requests = 0
  server.use(
    http.post('*/api/v1/auth/refresh', async () => {
      refreshes++
      await delay(40)
      return HttpResponse.json(credentials('new'))
    }),
    ...['/users/me', '/another'].map((path) =>
      http.get(`*/api/v1${path}`, ({ request }) => {
        requests++
        return request.headers.get('Authorization') === 'Bearer new'
          ? HttpResponse.json({ id: 'me' })
          : HttpResponse.json({}, { status: 401 })
      }),
    ),
  )
  const results = await Promise.all([
    store.dispatch(userApi.endpoints.getMe.initiate('me')),
    store.dispatch(testsApi.endpoints.another.initiate()),
  ])
  expect(results.every((result) => !result.error)).toBe(true)
  expect(refreshes).toBe(1)
  expect(requests).toBe(4)
})

it('does not refresh on 403 or failed login, and clears personal cache on logout network error', async () => {
  const auth = client()
  const store = createStore(auth)
  auth.accept(credentials('private-access'))
  let refreshes = 0
  server.use(
    http.get('*/api/v1/users/me', () => HttpResponse.json({ email: 'private@example.org' })),
    http.get('*/api/v1/another', () => HttpResponse.json({}, { status: 403 })),
    http.post('*/api/v1/auth/login', () => HttpResponse.json({}, { status: 401 })),
    http.post('*/api/v1/auth/refresh', () => {
      refreshes++
      return HttpResponse.json({}, { status: 401 })
    }),
    http.post('*/api/v1/auth/logout', () => HttpResponse.error()),
  )
  await store.dispatch(userApi.endpoints.getMe.initiate('me'))
  expect(JSON.stringify(store.getState())).toContain('private@example.org')
  await store.dispatch(testsApi.endpoints.another.initiate())
  await store.dispatch(
    authApi.endpoints.login.initiate({ email: 'a@example.org', password: 'wrong' }),
  )
  expect(refreshes).toBe(0)
  await store.dispatch(authApi.endpoints.logout.initiate())
  expect(auth.snapshot().status).toBe('guest')
  expect(auth.snapshot().notice).toContain('не подтверждён')
  expect(auth.access()).toBeUndefined()
  expect(JSON.stringify(store.getState())).not.toContain('private@example.org')
})

it('stops after the repeated 401 and clears session', async () => {
  const auth = client()
  const store = createStore(auth)
  auth.accept(credentials('old'))
  let refreshes = 0
  let requests = 0
  server.use(
    http.post('*/api/v1/auth/refresh', () => {
      refreshes++
      return HttpResponse.json(credentials('new'))
    }),
    http.get('*/api/v1/users/me', () => {
      requests++
      return HttpResponse.json({}, { status: 401 })
    }),
  )
  await store.dispatch(userApi.endpoints.getMe.initiate('me'))
  expect(refreshes).toBe(1)
  expect(requests).toBe(2)
  expect(auth.snapshot().status).toBe('guest')
})

it('serializes tab refreshes and restores the new account after a session-change notification', async () => {
  const listeners = [
    new Set<(event: MessageEvent) => void>(),
    new Set<(event: MessageEvent) => void>(),
  ]
  let queue = Promise.resolve()
  const broadcasts: unknown[] = []
  function coordinator(index: number) {
    return {
      lock<T>(work: () => Promise<T>): Promise<T> {
        const result = queue.then(work)
        queue = result.then(
          () => {},
          () => {},
        )
        return result
      },
      channel: {
        postMessage(data: unknown) {
          broadcasts.push(data)
          listeners[1 - index].forEach((listener) => listener({ data } as MessageEvent))
        },
        addEventListener(_type: string, listener: EventListenerOrEventListenerObject) {
          listeners[index].add(listener as (event: MessageEvent) => void)
        },
        removeEventListener() {},
        close() {},
      },
    }
  }
  const first = new AuthClient(coordinator(0))
  const second = new AuthClient(coordinator(1))
  let refreshes = 0
  let active = 0
  let maxActive = 0
  let currentUser = 'me'
  server.use(
    http.post('*/api/v1/auth/refresh', async () => {
      refreshes++
      active++
      maxActive = Math.max(maxActive, active)
      await delay(20)
      active--
      return HttpResponse.json(credentials(`access-${refreshes}`, currentUser))
    }),
  )
  await Promise.all([first.refresh(), second.refresh()])
  expect(refreshes).toBe(2)
  expect(maxActive).toBe(1)
  expect(first.access()).toBe('access-1')
  expect(second.access()).toBe('access-2')
  currentUser = 'another-user'
  first.accept(credentials('login-new-account', currentUser))
  expect(second.snapshot().status).toBe('checking')
  await vi.waitFor(() => expect(second.snapshot().userId).toBe('another-user'))
  expect(second.access()).toBe('access-3')
  expect(broadcasts.every((data) => !JSON.stringify(data).includes('accessToken'))).toBe(true)
  first.clear()
  expect(second.snapshot().status).toBe('guest')
})

it('keeps a recoverable offline state when refresh fails over the network', async () => {
  const auth = client()
  const store = createStore(auth)
  auth.accept(credentials('old'))
  server.use(
    http.get('*/api/v1/users/me', () => HttpResponse.json({}, { status: 401 })),
    http.post('*/api/v1/auth/refresh', () => HttpResponse.error()),
  )
  await store.dispatch(userApi.endpoints.getMe.initiate('me'))
  expect(auth.snapshot().status).toBe('offline')
  expect(auth.access()).toBeUndefined()
})
