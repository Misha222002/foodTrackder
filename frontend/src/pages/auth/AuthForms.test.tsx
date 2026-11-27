import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter, useLocation, useNavigate } from 'react-router'
import { AppProviders } from '../../app/providers/AppProviders'
import { AppRoutes } from '../../app/router/AppRoutes'
import { createStore } from '../../app/store/store'
import { AuthClient } from '../../shared/auth/client'
import { server } from '../../test/setup'

function BrowserHistory() {
  const navigate = useNavigate()
  const location = useLocation()
  return (
    <>
      <button
        onClick={() => {
          void navigate(-1)
        }}
      >
        Назад в истории
      </button>
      <button
        onClick={() => {
          void navigate(1)
        }}
      >
        Вперёд в истории
      </button>
      <output aria-label="Адрес страницы">
        {location.pathname}
        {location.search}
      </output>
    </>
  )
}
function open(path: string) {
  const store = createStore(new AuthClient({ lock: (work) => work() }))
  return render(
    <AppProviders store={store}>
      <MemoryRouter initialEntries={[path]}>
        <BrowserHistory />
        <AppRoutes />
      </MemoryRouter>
    </AppProviders>,
  )
}
function challenge(id: string) {
  return {
    challengeId: id,
    expiresAt: new Date(Date.now() + 600_000).toISOString(),
    resendAvailableAt: new Date(Date.now() + 60_000).toISOString(),
  }
}

it('keeps email on back, clears the password, and binds the displayed recipient to each challenge', async () => {
  let requests = 0
  server.use(
    http.post('*/api/v1/auth/register', () => {
      requests++
      return HttpResponse.json(challenge(`request-${requests}`), { status: 202 })
    }),
  )
  open('/register')
  await userEvent.type(screen.getByLabelText('Email'), 'first@example.org')
  const password = screen.getByLabelText('Пароль')
  await userEvent.type(password, 'long password for test')
  expect(password).toHaveAttribute('type', 'password')
  await userEvent.click(screen.getByRole('button', { name: 'Показать пароль' }))
  expect(password).toHaveAttribute('type', 'text')
  expect(password).toHaveValue('long password for test')
  expect(requests).toBe(0)
  await userEvent.click(screen.getByRole('button', { name: 'Скрыть пароль' }))
  expect(password).toHaveAttribute('type', 'password')
  await userEvent.click(screen.getByRole('button', { name: 'Получить код' }))
  expect(await screen.findByText('first@example.org')).toBeVisible()
  expect(screen.getByLabelText('Адрес страницы')).not.toHaveTextContent('first@example.org')
  await userEvent.click(screen.getByRole('button', { name: 'Назад в истории' }))
  expect(await screen.findByLabelText('Email')).toHaveValue('first@example.org')
  expect(screen.getByLabelText('Пароль')).toHaveValue('')
  expect(screen.getByLabelText('Пароль')).toHaveAttribute('type', 'password')
  await userEvent.click(screen.getByRole('button', { name: 'Вперёд в истории' }))
  expect(await screen.findByText('first@example.org')).toBeVisible()
  await userEvent.click(screen.getByRole('link', { name: 'Вернуться к регистрации' }))
  expect(await screen.findByLabelText('Email')).toHaveValue('first@example.org')
  await userEvent.click(screen.getByRole('link', { name: 'Продолжить подтверждение почты' }))
  expect(await screen.findByText('first@example.org')).toBeVisible()
  expect(requests).toBe(1)
  await userEvent.click(screen.getByRole('link', { name: 'Вернуться к регистрации' }))
  await userEvent.clear(screen.getByLabelText('Email'))
  await userEvent.type(screen.getByLabelText('Email'), 'second@example.org')
  expect(
    screen.queryByRole('link', { name: 'Продолжить подтверждение почты' }),
  ).not.toBeInTheDocument()
  await userEvent.type(screen.getByLabelText('Пароль'), 'another password for test')
  await userEvent.click(screen.getByRole('button', { name: 'Получить код' }))
  expect(await screen.findByText('second@example.org')).toBeVisible()
  expect(screen.queryByText('first@example.org')).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Назад в истории' }))
  expect(await screen.findByLabelText('Email')).toHaveValue('second@example.org')
  await userEvent.click(screen.getByRole('button', { name: 'Назад в истории' }))
  expect(await screen.findByText('first@example.org')).toBeVisible()
  expect(screen.queryByText('second@example.org')).not.toBeInTheDocument()
})

it('shows the recipient after login with unverified email and supports keyboard password visibility', async () => {
  let requests = 0
  server.use(
    http.post('*/api/v1/auth/login', () => {
      requests++
      return HttpResponse.json({
        ...challenge('login-request'),
        status: 'email_verification_required',
      })
    }),
  )
  open('/login')
  await userEvent.type(screen.getByLabelText('Email'), 'unverified@example.org')
  const password = screen.getByLabelText('Пароль')
  await userEvent.type(password, 'my login password')
  await userEvent.tab()
  expect(screen.getByRole('button', { name: 'Показать пароль' })).toHaveFocus()
  await userEvent.keyboard(' ')
  expect(password).toHaveAttribute('type', 'text')
  await userEvent.keyboard(' ')
  expect(password).toHaveAttribute('type', 'password')
  expect(password).toHaveValue('my login password')
  expect(requests).toBe(0)
  await userEvent.click(screen.getByRole('button', { name: 'Войти' }))
  expect(await screen.findByText('unverified@example.org')).toBeVisible()
  await userEvent.click(screen.getByRole('link', { name: 'Вернуться ко входу' }))
  await waitFor(() => expect(screen.getByLabelText('Email')).toHaveValue('unverified@example.org'))
  expect(screen.getByLabelText('Пароль')).toHaveValue('')
})

it('keeps recovery email on back and reveals the new password without sending the reset form', async () => {
  let resets = 0
  server.use(
    http.post('*/api/v1/auth/password/forgot', () =>
      HttpResponse.json(challenge('reset-request'), { status: 202 }),
    ),
    http.post('*/api/v1/auth/password/reset', () => {
      resets++
      return HttpResponse.json({ status: 'password_reset' })
    }),
  )
  open('/forgot-password')
  await userEvent.type(screen.getByLabelText('Email'), 'recover@example.org')
  await userEvent.click(screen.getByRole('button', { name: 'Получить код' }))
  expect(await screen.findByText('recover@example.org')).toBeVisible()
  await userEvent.type(screen.getByLabelText('Новый пароль'), 'new private password')
  await userEvent.click(screen.getByRole('button', { name: 'Показать пароль' }))
  expect(screen.getByLabelText('Новый пароль')).toHaveAttribute('type', 'text')
  expect(screen.getByLabelText('Новый пароль')).toHaveValue('new private password')
  expect(resets).toBe(0)
  await userEvent.click(screen.getByRole('button', { name: 'Назад в истории' }))
  expect(await screen.findByLabelText('Email')).toHaveValue('recover@example.org')
  await userEvent.click(screen.getByRole('button', { name: 'Вперёд в истории' }))
  expect(await screen.findByLabelText('Новый пароль')).toHaveValue('')
  expect(screen.getByLabelText('Новый пароль')).toHaveAttribute('type', 'password')
})

it.each([
  ['CODE_INVALID', 'Неверный код'],
  ['CODE_EXPIRED', 'Срок кода истёк. Запросите новый код'],
])('handles %s and clears the old code/error after successful resend', async (code, message) => {
  server.use(
    http.post('*/api/v1/auth/register', () =>
      HttpResponse.json(
        {
          ...challenge('error-request'),
          resendAvailableAt: new Date(Date.now() - 1_000).toISOString(),
        },
        { status: 202 },
      ),
    ),
    http.post('*/api/v1/auth/verify-email', () =>
      HttpResponse.json({ code, message, details: {}, requestId: 'test' }, { status: 400 }),
    ),
    http.post('*/api/v1/auth/verification/resend', async ({ request }) => {
      expect(await request.json()).toEqual({ challengeId: 'error-request' })
      return HttpResponse.json(challenge('error-request'))
    }),
  )
  open('/register')
  await userEvent.type(screen.getByLabelText('Email'), 'code-errors@example.org')
  await userEvent.type(screen.getByLabelText('Пароль'), 'long password for test')
  await userEvent.click(screen.getByRole('button', { name: 'Получить код' }))
  await screen.findByRole('heading', { name: 'Подтвердить почту' })
  await userEvent.type(screen.getByLabelText('Код из письма'), '123456')
  await userEvent.click(screen.getByRole('button', { name: 'Подтвердить и войти' }))
  expect(await screen.findByText(message)).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Отправить код ещё раз' }))
  expect(await screen.findByRole('button', { name: /Повторить через/ })).toBeDisabled()
  expect(screen.queryByText(message)).not.toBeInTheDocument()
  expect(screen.getByLabelText('Код из письма')).toHaveValue('')
  expect(screen.getByText('code-errors@example.org')).toBeVisible()
})
