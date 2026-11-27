import type { PropsWithChildren } from 'react'
import { Provider } from 'react-redux'
import { CssBaseline, ThemeProvider } from '@mui/material'
import type { AppStore } from '../store/store'
import { theme } from '../theme/theme'

export function AppProviders({ store, children }: PropsWithChildren<{ store: AppStore }>) {
  return (
    <Provider store={store}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        {children}
      </ThemeProvider>
    </Provider>
  )
}
