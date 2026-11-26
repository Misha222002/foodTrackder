import { useEffect } from 'react'
import { config } from '../config/env'
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
  const { fulfilledTimeStamp, isFetching, refetch } = query
  useEffect(() => {
    function checkFreshness() {
      if (document.visibilityState === 'hidden' || isFetching) return
      if (!fulfilledTimeStamp || Date.now() - fulfilledTimeStamp >= config.freshnessSeconds * 1000) {
        void refetch()
      }
    }
    window.addEventListener('focus', checkFreshness)
    window.addEventListener('online', checkFreshness)
    document.addEventListener('visibilitychange', checkFreshness)
    return () => {
      window.removeEventListener('focus', checkFreshness)
      window.removeEventListener('online', checkFreshness)
      document.removeEventListener('visibilitychange', checkFreshness)
    }
  }, [fulfilledTimeStamp, isFetching, refetch])
  return query
}
