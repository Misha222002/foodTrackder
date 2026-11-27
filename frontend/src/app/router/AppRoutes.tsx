import { AppBar, Box, Button, Container, Toolbar, Typography } from '@mui/material'
import { Link, Route, Routes } from 'react-router'
import { HomePage } from '../../pages/home'
import { NotFoundPage } from '../../pages/not-found'

export function AppRoutes() {
  return (
    <>
      <AppBar position="static" color="inherit" elevation={0} sx={{ borderBottom: 1, borderColor: 'divider' }}>
        <Toolbar sx={{ gap: 3 }}>
          <Typography variant="h6" component={Link} to="/" color="primary" sx={{ textDecoration: 'none', fontWeight: 700 }}>
            Food Tracker
          </Typography>
          <Box component="nav" aria-label="Основная навигация">
            <Button component={Link} to="/">Главная</Button>
          </Box>
        </Toolbar>
      </AppBar>
      <Container component="main" maxWidth="lg" sx={{ py: { xs: 4, md: 8 } }}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </Container>
    </>
  )
}
