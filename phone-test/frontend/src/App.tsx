import { useEffect } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { ThemeProvider, CssBaseline } from '@mui/material'
import { theme } from './theme'
import ControlCenter from './pages/ControlCenter'
import DevTools from './pages/DevTools'
import GroupControl from './pages/GroupControl'
import Calibration from './pages/Calibration'
import Settings from './pages/Settings'
import VisionTest from './pages/VisionTest'
import EmergencyStop from './components/common/EmergencyStop'
import { wsClient } from './api/ws'
import { ensureToken } from './api/client'
import { useDeviceStore } from './stores/deviceStore'
import { DeviceStatus } from './types/device'

export default function App() {
  const updateDeviceStatus = useDeviceStore((s) => s.updateDeviceStatus)

  useEffect(() => {
    ensureToken()
      .then(() => wsClient.connect())
      .catch(console.error)

    const unsub = wsClient.subscribe((event, data) => {
      if (event === 'device_status') {
        updateDeviceStatus(data.device_id as number, data.status as DeviceStatus)
      }
    })

    return () => {
      unsub()
      wsClient.disconnect()
    }
  }, [])

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<ControlCenter />} />
          <Route path="/devtools" element={<DevTools />} />
          <Route path="/group" element={<GroupControl />} />
          <Route path="/calibration" element={<Calibration />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/vision-test" element={<VisionTest />} />
        </Routes>
        <EmergencyStop />
      </BrowserRouter>
    </ThemeProvider>
  )
}
