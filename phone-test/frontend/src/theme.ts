import { createTheme } from '@mui/material/styles'

const theme = createTheme({
  palette: {
    mode: 'dark',
    background: { default: '#1a1a2e', paper: '#16213e' },
    primary: { main: '#0096ff' },
    secondary: { main: '#0f3460' },
    success: { main: '#00c853' },
    error: { main: '#ff1744' },
    warning: { main: '#ff9100' },
    text: { primary: '#e0e0e0', secondary: '#aaaaaa' },
  },
  components: {
    MuiButton: {
      styleOverrides: { root: { textTransform: 'none', fontWeight: 600 } },
    },
    MuiCard: {
      styleOverrides: { root: { backgroundColor: '#16213e', borderRadius: 8 } },
    },
    MuiPaper: {
      styleOverrides: { root: { backgroundColor: '#16213e' } },
    },
  },
})

export default theme
export { theme }

// Color constants for direct use
export const colors = {
  bg: '#1a1a2e',
  card: '#16213e',
  cardBg: '#16213e',
  cardBgAlt: '#0f3460',
  highlight: '#0096ff',
  success: '#00c853',
  danger: '#ff1744',
  warning: '#ff9100',
  orange: '#ff9100',
  text: '#e0e0e0',
  logError: '#ff5252',
  logSuccess: '#69f0ae',
}
