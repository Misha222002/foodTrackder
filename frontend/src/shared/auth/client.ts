import { config } from '../config/env'
import type { components } from '../api/generated/schema'

type Credentials = components['schemas']['TokenResponse']
export type SessionState = {
  status: 'checking' | 'guest' | 'authenticated' | 'offline' | 'unsupported'
  userId?: string
  notice?: string
}
type Coordinator = {
  lock<T>(work: () => Promise<T>): Promise<T>
  channel?: Pick<
    BroadcastChannel,
    'postMessage' | 'addEventListener' | 'removeEventListener' | 'close'
  >
}

export class AuthClient {
  private credentials?: Credentials
  private csrf?: string
  private csrfPending?: Promise<string>
  private pending?: Promise<boolean>
  private started = false
  private epoch = 0
  private listeners = new Set<() => void>()
  private state: SessionState = { status: 'checking' }
  onIdentityChange = () => {}
  private coordinator?: Coordinator

  constructor(coordinator?: Coordinator) {
    this.coordinator =
      coordinator ??
      (typeof navigator !== 'undefined' && navigator.locks
        ? {
            lock: (work) => navigator.locks.request('food-tracker-session', work),
            channel:
              typeof window.BroadcastChannel === 'function'
                ? new window.BroadcastChannel('food-tracker-session')
                : undefined,
          }
        : undefined)
    this.coordinator?.channel?.addEventListener('message', this.receive)
  }
  subscribe = (listener: () => void) => {
    this.listeners.add(listener)
    return () => {
      this.listeners.delete(listener)
    }
  }
  snapshot = () => this.state
  access = () => this.credentials?.accessToken
  private emit(state: SessionState) {
    this.state = state
    this.listeners.forEach((listener) => listener())
  }
  accept = (credentials: Credentials, broadcast = true) => {
    if (this.state.userId && this.state.userId !== credentials.userId) this.onIdentityChange()
    this.credentials = credentials
    this.emit({ status: 'authenticated', userId: credentials.userId })
    if (broadcast) this.coordinator?.channel?.postMessage({ type: 'session-changed' })
  }
  clear = (notice?: string, broadcast = true) => {
    this.epoch++
    this.credentials = undefined
    if (this.state.userId) this.onIdentityChange()
    this.emit({ status: 'guest', notice })
    if (broadcast) this.coordinator?.channel?.postMessage({ type: 'logout', notice })
  }
  private receive = (event: MessageEvent) => {
    const message = event.data as { type?: string; notice?: string }
    if (message.type === 'session-changed') {
      // Read the authoritative HttpOnly cookie under the shared lock. Never accept a
      // delayed access-token broadcast from a previous account/session.
      this.epoch++
      this.credentials = undefined
      this.onIdentityChange()
      this.emit({ status: 'checking' })
      void (this.pending ?? Promise.resolve()).then(() => this.refresh())
    } else if (message.type === 'logout') {
      this.clear(message.notice, false)
    }
  }
  private fresh() {
    return this.credentials && Date.parse(this.credentials.expiresAt) > Date.now() + 5_000
  }
  lock<T>(work: () => Promise<T>): Promise<T> {
    return this.coordinator ? this.coordinator.lock(work) : work()
  }
  async csrfToken(force = false): Promise<string> {
    if (force) this.csrf = undefined
    if (this.csrf) return this.csrf
    this.csrfPending ??= (async () => {
      const response = await fetch(`${config.apiBaseUrl}/auth/csrf`, { credentials: 'include' })
      if (!response.ok) throw new Error('Не удалось подготовить безопасный запрос')
      this.csrf = ((await response.json()) as { csrfToken: string }).csrfToken
      return this.csrf
    })().finally(() => {
      this.csrfPending = undefined
    })
    return this.csrfPending
  }
  start = () => {
    if (this.started) return
    this.started = true
    void this.refresh()
  }
  refresh = (rejectedAccess?: string): Promise<boolean> => {
    if (this.pending) return this.pending
    if (!this.coordinator) {
      this.emit({
        status: 'unsupported',
        notice: 'Для восстановления сессии нужен браузер с Web Locks и HTTPS.',
      })
      return Promise.resolve(false)
    }
    const epoch = this.epoch
    this.pending = this.lock(async () => {
      if (epoch !== this.epoch) return false
      // Within a tab, reuse a refresh that finished before a later 401 arrived.
      // Other tabs rotate serially using the latest shared HttpOnly cookie.
      if (this.fresh() && this.access() !== rejectedAccess) return true
      try {
        let response: Response | undefined
        for (let attempt = 0; attempt < 2; attempt++) {
          response = await fetch(`${config.apiBaseUrl}/auth/refresh`, {
            method: 'POST',
            credentials: 'include',
            headers: { 'X-CSRF-Token': await this.csrfToken(attempt === 1) },
          })
          if (response.status !== 403 || attempt === 1) break
          const error = (await response.clone().json()) as { code?: string }
          if (error.code !== 'CSRF_INVALID') break
        }
        if (epoch !== this.epoch) return false
        if (response?.ok) {
          this.accept((await response.json()) as Credentials, false)
          return true
        }
        if (response && response.status >= 500) throw new Error('Сервис недоступен')
        this.clear()
      } catch {
        if (epoch === this.epoch) {
          this.credentials = undefined
          this.onIdentityChange()
          this.emit({
            status: 'offline',
            notice: 'Не удалось восстановить сессию. Проверьте соединение и повторите.',
          })
        }
      }
      return false
    }).finally(() => {
      this.pending = undefined
    })
    return this.pending
  }
  dispose() {
    this.coordinator?.channel?.removeEventListener('message', this.receive)
    this.coordinator?.channel?.close()
  }
}
