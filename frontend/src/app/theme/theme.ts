import { createTheme } from '@mui/material/styles'

export const theme = createTheme({
  palette: {
    primary: { main: '#276749' },
    background: { default: '#f5f7f4', paper: '#ffffff' },
    text: { primary: '#203129', secondary: '#56645c' },
  },
  typography: { fontFamily: 'system-ui, -apple-system, "Segoe UI", sans-serif' },
  shape: { borderRadius: 12 },
  components: {
    MuiButton: { defaultProps: { disableElevation: true }, styleOverrides: { root: { textTransform: 'none' } } },
    MuiTextField: { defaultProps: { fullWidth: true, size: 'small' } },
    MuiCard: { defaultProps: { variant: 'outlined' } },
  },
})
