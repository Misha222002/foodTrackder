import { useEffect } from 'react'
import { useAuthClient, useSession } from '../../shared/auth/context'
import {
  RegistrationPage,
  VerificationPage,
  LoginPage,
  ForgotPasswordPage,
  ResetPasswordPage,
} from '../../pages/auth'
import { ProfilePage } from '../../pages/profile'
import { authApi } from '../../features/auth'
import { Alert, AppBar, Box, Button, Container, Toolbar, Typography } from '@mui/material'
import { Link, Route, Routes } from 'react-router'
import { HomePage } from '../../pages/home'
import { NotFoundPage } from '../../pages/not-found'

export function AppRoutes() {
  const auth = useAuthClient()
  const session = useSession()
  const [logout, logoutResult] = authApi.useLogoutMutation()
  useEffect(() => {
    auth.start()
  }, [auth])
  return (
    <>
      <AppBar
        position="static"
        color="inherit"
        elevation={0}
        sx={{ borderBottom: 1, borderColor: 'divider' }}
      >
        <Toolbar sx={{ gap: { xs: 1, sm: 3 }, flexWrap: 'wrap', py: 1 }}>
          <Typography
            variant="h6"
            component={Link}
            to="/"
            color="primary"
            sx={{ textDecoration: 'none', fontWeight: 700 }}
          >
            Ем по плану
          </Typography>
          <Box component="nav" aria-label="Основная навигация">
            <Button component={Link} to="/">
              Главная
            </Button>
            <Button component={Link} to="/profile">
              Профиль
            </Button>
            {session.status === 'authenticated' ? (
              <Button
                disabled={logoutResult.isLoading}
                onClick={() => {
                  void logout()
                }}
              >
                Выйти
              </Button>
            ) : (
              <Button component={Link} to="/login">
                Войти
              </Button>
            )}
          </Box>
        </Toolbar>
      </AppBar>
      <Container component="main" maxWidth="lg" sx={{ py: { xs: 4, md: 8 } }}>
        {session.status === 'guest' && session.notice && (
          <Alert
            severity="warning"
            sx={{ mb: 3 }}
            action={
              session.notice.includes('не подтверждён') ? (
                <Button
                  disabled={logoutResult.isLoading}
                  onClick={() => {
                    void logout()
                  }}
                >
                  Повторить выход
                </Button>
              ) : undefined
            }
          >
            {session.notice}
          </Alert>
        )}
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegistrationPage />} />
          <Route path="/verify-email" element={<VerificationPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </Container>
    </>
  )
}
