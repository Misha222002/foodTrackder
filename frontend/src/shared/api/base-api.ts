import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react'
import type { BaseQueryFn, FetchArgs, FetchBaseQueryError } from '@reduxjs/toolkit/query'
import { config } from '../config/env'
import type { AuthClient } from '../auth/client'
import type { components } from './generated/schema'

const send = fetchBaseQuery({ baseUrl: config.apiBaseUrl, credentials: 'include' })
const baseQuery: BaseQueryFn<string | FetchArgs, unknown, FetchBaseQueryError> = async (
  args,
  api,
  options,
) => {
  const auth = (api.extra as { auth: AuthClient }).auth
  const original = typeof args === 'string' ? { url: args } : args
  const isAuth = original.url.startsWith('/auth/')
  const mutates = (original.method ?? 'GET') !== 'GET'
  async function request(forceCsrf = false) {
    const headers = new Headers(original.headers as HeadersInit | undefined)
    if (!isAuth && auth.access()) headers.set('Authorization', `Bearer ${auth.access()}`)
    if (isAuth && mutates) {
      try {
        headers.set('X-CSRF-Token', await auth.csrfToken(forceCsrf))
      } catch {
        return {
          error: { status: 'FETCH_ERROR' as const, error: 'Не удалось связаться с сервером' },
        }
      }
    }
    return send({ ...original, headers }, api, options)
  }
  const work = async () => {
    const oldAccess = auth.access()
    let result = await request()
    if (
      isAuth &&
      result.error?.status === 403 &&
      (result.error.data as { code?: string })?.code === 'CSRF_INVALID'
    )
      result = await request(true)
    if (!isAuth && result.error?.status === 401) {
      if (await auth.refresh(oldAccess)) {
        result = await request()
        if (result.error?.status === 401) auth.clear()
      }
    }
    if (
      isAuth &&
      !result.error &&
      ['verify-email', 'login'].includes(original.url.split('/').at(-1)!)
    ) {
      if ((result.data as { status: string }).status === 'authenticated') {
        auth.accept(result.data as components['schemas']['TokenResponse'])
        // The wire token must never enter RTK Query/Redux caches.
        const { accessToken: _token, ...publicResult } =
          result.data as components['schemas']['TokenResponse']
        void _token
        result = { ...result, data: publicResult }
      }
    }
    if (original.url === '/auth/logout') {
      auth.clear(
        result.error
          ? 'Вы вышли на этом устройстве, но серверный отзыв сессии не подтверждён. Повторите выход после восстановления связи.'
          : undefined,
      )
    }
    if (original.url === '/auth/password/reset' && !result.error)
      auth.clear('Пароль изменён. Войдите с новым паролем.')
    return result
  }
  return isAuth && ['/auth/login', '/auth/verify-email', '/auth/logout'].includes(original.url)
    ? auth.lock(work)
    : work()
}

export const baseApi = createApi({
  reducerPath: 'api',
  baseQuery,
  keepUnusedDataFor: config.freshnessSeconds,
  refetchOnMountOrArgChange: config.freshnessSeconds,
  endpoints: () => ({}),
})
