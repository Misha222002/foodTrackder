import { configureStore } from '@reduxjs/toolkit'
import { baseApi } from '../../shared/api'

export function createStore() {
  return configureStore({
    reducer: { [baseApi.reducerPath]: baseApi.reducer },
    middleware: (getDefaultMiddleware) => getDefaultMiddleware().concat(baseApi.middleware),
  })
}

export type AppStore = ReturnType<typeof createStore>
