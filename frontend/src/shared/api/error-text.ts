export function errorText(error: unknown): string {
  if (typeof error === 'object' && error && 'data' in error) {
    const data = error.data as { message?: string; details?: { retryAfterSeconds?: number } }
    if (data.message)
      return `${data.message}${data.details?.retryAfterSeconds ? ` (${data.details.retryAfterSeconds} сек.)` : ''}`
  }
  return 'Не удалось связаться с сервером. Проверьте соединение и повторите.'
}
