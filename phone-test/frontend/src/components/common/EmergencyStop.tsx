import { Fab, Tooltip } from '@mui/material'
import { emergencyApi } from '../../api/devices'
import { useLogStore } from '../../stores/logStore'
import { colors } from '../../theme'

export default function EmergencyStop() {
  const addLog = useLogStore((s) => s.addLog)

  const handleStop = async () => {
    try {
      await emergencyApi.stopAll()
      addLog('紧急停止已触发！所有设备停止', 'error')
    } catch (e) {
      addLog(`紧急停止失败: ${e}`, 'error')
    }
  }

  return (
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
  )
}
