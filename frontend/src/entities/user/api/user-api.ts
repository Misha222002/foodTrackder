import { baseApi } from '../../../shared/api/base-api'
import type { components } from '../../../shared/api/generated/schema'

export const userApi = baseApi.injectEndpoints({
  endpoints: (build) => ({
    updateMe: build.mutation<
      components['schemas']['UserResponse'],
      { userId: string; revision: number; body: components['schemas']['ProfileRequest'] }
    >({
      query: ({ revision, body }) => ({
        url: '/users/me',
        method: 'PUT',
        body,
        headers: { 'If-Match': `"profile-${revision}"` },
      }),
      async onQueryStarted({ userId }, { dispatch, queryFulfilled }) {
        try {
          const { data } = await queryFulfilled
          await dispatch(userApi.util.upsertQueryData('getMe', userId, data))
        } catch {
          /* UI renders errors */
        }
      },
    }),
    getMe: build.query<components['schemas']['UserResponse'], string>({ query: () => '/users/me' }),
  }),
})
