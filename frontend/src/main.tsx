import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import { AppProviders } from './app/providers/AppProviders'
import { AppRoutes } from './app/router/AppRoutes'
import { createStore } from './app/store/store'

async function bootstrap() {
  if (import.meta.env.DEV && import.meta.env.VITE_ENABLE_MSW === 'true') {
    const { worker } = await import('./app/mocks/browser')
    await worker.start({ onUnhandledRequest: 'bypass' })
  }
  const store = createStore()
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <AppProviders store={store}>
        <BrowserRouter><AppRoutes /></BrowserRouter>
      </AppProviders>
    </StrictMode>,
  )
}

void bootstrap()
