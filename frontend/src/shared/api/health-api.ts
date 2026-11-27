import { useStaleRefresh } from './use-stale-refresh'
import { baseApi } from './base-api'
import type { components } from './generated/schema'

export type HealthResponse = components['schemas']['HealthResponse']
export type ApiError = components['schemas']['ApiError']

export const healthApi = baseApi.injectEndpoints({
  endpoints: (build) => ({
    getHealth: build.query<HealthResponse, void>({ query: () => '/health' }),
  }),
})

export function useGetHealthQuery() {
  const query = healthApi.useGetHealthQuery()
  useStaleRefresh(query)
  return query
}
