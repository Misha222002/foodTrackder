const freshness = Number(import.meta.env.VITE_API_FRESHNESS_SECONDS || 30)
if (!Number.isFinite(freshness) || freshness <= 0) {
  throw new Error('VITE_API_FRESHNESS_SECONDS must be a positive number')
}

export const config = {
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  freshnessSeconds: freshness,
}
