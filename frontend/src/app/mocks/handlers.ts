import { http, HttpResponse } from 'msw'
import type { HealthResponse } from '../../shared/api'

export const handlers = [
  http.get('*/api/v1/auth/csrf', () => HttpResponse.json({ csrfToken: 'test-csrf' })),
  http.post('*/api/v1/auth/refresh', () =>
    HttpResponse.json(
      { code: 'SESSION_EXPIRED', message: 'Войдите', details: {}, requestId: 'mock' },
      { status: 401 },
    ),
  ),
  http.get('*/api/v1/health', () =>
    HttpResponse.json({ status: 'ok', database: 'ok' } satisfies HealthResponse),
  ),
]
