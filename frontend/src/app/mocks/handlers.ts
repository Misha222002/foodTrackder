import { http, HttpResponse } from 'msw'
import type { HealthResponse } from '../../shared/api'

export const handlers = [
  http.get('*/api/v1/health', () =>
    HttpResponse.json({ status: 'ok', database: 'ok' } satisfies HealthResponse),
  ),
]
