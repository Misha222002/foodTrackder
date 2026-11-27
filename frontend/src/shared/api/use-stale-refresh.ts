import { useEffect } from 'react'
import { config } from '../config/env'

export function useStaleRefresh({
  fulfilledTimeStamp,
  isFetching,
  refetch,
  enabled = true,
}: {
  fulfilledTimeStamp?: number
  isFetching: boolean
  refetch: () => unknown
  enabled?: boolean
}) {
  useEffect(() => {
    function check() {
      if (!enabled || document.visibilityState === 'hidden' || isFetching) return
      if (!fulfilledTimeStamp || Date.now() - fulfilledTimeStamp >= config.freshnessSeconds * 1000)
        void refetch()
    }
    window.addEventListener('focus', check)
    window.addEventListener('online', check)
    document.addEventListener('visibilitychange', check)
    return () => {
      window.removeEventListener('focus', check)
      window.removeEventListener('online', check)
      document.removeEventListener('visibilitychange', check)
    }
  }, [fulfilledTimeStamp, isFetching, refetch, enabled])
}
