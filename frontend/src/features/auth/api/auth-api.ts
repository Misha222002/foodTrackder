import { baseApi } from '../../../shared/api/base-api'
import type { components } from '../../../shared/api/generated/schema'

type Schema = components['schemas']
export type Challenge = Schema['ChallengeResponse']
export const authApi = baseApi.injectEndpoints({
  endpoints: (build) => ({
    forgotPassword: build.mutation<Challenge, Schema['ForgotPasswordRequest']>({
      query: (body) => ({ url: '/auth/password/forgot', method: 'POST', body }),
    }),
    resetPassword: build.mutation<Schema['PasswordResetResponse'], Schema['ResetPasswordRequest']>({
      query: (body) => ({ url: '/auth/password/reset', method: 'POST', body }),
    }),
    login: build.mutation<
      Omit<Schema['TokenResponse'], 'accessToken'> | Schema['VerificationRequired'],
      Schema['LoginRequest']
    >({
      query: (body) => ({ url: '/auth/login', method: 'POST', body }),
    }),
    logout: build.mutation<void, void>({ query: () => ({ url: '/auth/logout', method: 'POST' }) }),
    register: build.mutation<Challenge, Schema['RegisterRequest']>({
      query: (body) => ({ url: '/auth/register', method: 'POST', body }),
    }),
    verifyEmail: build.mutation<
      Omit<Schema['TokenResponse'], 'accessToken'>,
      Schema['CodeRequest']
    >({
      query: (body) => ({ url: '/auth/verify-email', method: 'POST', body }),
    }),
    resendVerification: build.mutation<Challenge, Schema['ResendRequest']>({
      query: (body) => ({ url: '/auth/verification/resend', method: 'POST', body }),
    }),
  }),
})
