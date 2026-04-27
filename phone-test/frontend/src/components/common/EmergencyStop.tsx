import { Fab, Tooltip } from '@mui/material'
import { emergencyApi } from '../../api/devices'
import { useDeviceStore } from '../../stores/deviceStore'
import { useLogStore } from '../../stores/logStore'
import { colors } from '../../theme'

export default function EmergencyStop() {
  const addLog = useLogStore((s) => s.addLog)
  const devices = useDeviceStore((s) => s.devices)
  const fetchDevices = useDeviceStore((s) => s.fetchDevices)
  const hasEstop = devices.some(d => d.status === 'ESTOP')

  const handleStop = async () => {
    try {
      await emergencyApi.stopAll()
      addLog('紧急停止已触发！所有设备停止', 'error')
      fetchDevices()
    } catch (e: any) {
      addLog(`紧急停止失败: ${e?.response?.data?.detail || e}`, 'error')
    }
  }

  const handleReset = async () => {
    try {
      addLog('正在复位：重启Klipper固件并恢复设备...', 'warn')
      await emergencyApi.resetAll()
      addLog('固件重启指令已发送，等待设备恢复...', 'success')
      setTimeout(() => fetchDevices(), 3000)
      setTimeout(() => fetchDevices(), 8000)
    } catch (e: any) {
      addLog(`复位失败: ${e?.response?.data?.detail || e}`, 'error')
    }
  }

  return (
    <>
      {hasEstop && (
        <Tooltip title="复位 (重启固件+解除急停)">
          <Fab
            size="medium"
            onClick={handleReset}
            sx={{
              position: 'fixed',
              bottom: 24,
              right: 80,
              bgcolor: '#f57c00',
              color: '#fff',
              fontWeight: 900,
              fontSize: 14,
              '&:hover': { bgcolor: '#e65100' },
              zIndex: 9999,
            }}
          >
            ↻
          </Fab>
        </Tooltip>
      )}
      <Tooltip title="紧急停止 (所有设备)">
        <Fab
          size="medium"
          onClick={handleStop}
          sx={{
            position: 'fixed',
            bottom: 24,
            right: 24,
            bgcolor: colors.danger,
            color: '#fff',
            fontWeight: 900,
            fontSize: 18,
            '&:hover': { bgcolor: '#b71c1c' },
            zIndex: 9999,
          }}
        >
          ■
        </Fab>
      </Tooltip>
    </>
  )
}
