import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react'
import { config } from '../config/env'

export const baseApi = createApi({
  reducerPath: 'api',
  baseQuery: fetchBaseQuery({ baseUrl: config.apiBaseUrl, credentials: 'include' }),
  keepUnusedDataFor: config.freshnessSeconds,
  refetchOnMountOrArgChange: config.freshnessSeconds,
  endpoints: () => ({}),
})
