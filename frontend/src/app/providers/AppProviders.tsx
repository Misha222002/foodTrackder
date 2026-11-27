import type { PropsWithChildren } from 'react'
import { Provider } from 'react-redux'
import { CssBaseline, ThemeProvider } from '@mui/material'
import { AuthDraftsProvider } from '../../features/auth'
import { AuthContext } from '../../shared/auth/context'
import type { AppStore } from '../store/store'
import { theme } from '../theme/theme'

export function AppProviders({ store, children }: PropsWithChildren<{ store: AppStore }>) {
  return (
    <Provider store={store}>
      <AuthContext.Provider value={store.auth}>
        <ThemeProvider theme={theme}>
          <CssBaseline />
          <AuthDraftsProvider>{children}</AuthDraftsProvider>
        </ThemeProvider>
      </AuthContext.Provider>
    </Provider>
  )
}
