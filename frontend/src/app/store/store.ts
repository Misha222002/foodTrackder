import { configureStore } from '@reduxjs/toolkit'
import { AuthClient } from '../../shared/auth/client'
import { baseApi } from '../../shared/api'

export function createStore(auth = new AuthClient()) {
  const store = configureStore({
    devTools: false,
    reducer: { [baseApi.reducerPath]: baseApi.reducer },
    middleware: (getDefaultMiddleware) =>
      getDefaultMiddleware({ thunk: { extraArgument: { auth } } }).concat(baseApi.middleware),
  })
  auth.onIdentityChange = () => {
    store.dispatch(baseApi.util.resetApiState())
  }
  return Object.assign(store, { auth })
}

export type AppStore = ReturnType<typeof createStore>
