import { existsSync, readFileSync } from 'node:fs'
import react from '@vitejs/plugin-react'
import { loadEnv } from 'vite'
import { defineConfig } from 'vitest/config'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [react()],
    server: {
      https:
        existsSync('.certs/localhost.pem') && existsSync('.certs/localhost-key.pem')
          ? {
              cert: readFileSync('.certs/localhost.pem'),
              key: readFileSync('.certs/localhost-key.pem'),
            }
          : undefined,
      proxy: {
        '/api': { target: env.API_PROXY_TARGET || 'http://127.0.0.1:8000', changeOrigin: true },
      },
    },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/test/setup.ts'],
      env: { VITE_API_BASE_URL: 'http://localhost/api/v1', VITE_API_FRESHNESS_SECONDS: '30' },
      restoreMocks: true,
    },
  }
})
