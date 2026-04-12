import CircleIcon from '@mui/icons-material/Circle'
import { Tooltip } from '@mui/material'
import { DeviceStatus } from '../../types/device'
import { colors } from '../../theme'

const statusMap: Record<DeviceStatus, { color: string; label: string }> = {
  ONLINE: { color: colors.success, label: '在线' },
  OFFLINE: { color: '#555', label: '离线' },
  SUSPECT: { color: colors.warning, label: '疑似掉线' },
  RECOVERING: { color: '#42a5f5', label: '恢复中' },
  ESTOP: { color: colors.danger, label: '急停' },
}

interface Props {
  status: DeviceStatus
  size?: number
}

export default function StatusIndicator({ status, size = 12 }: Props) {
  const info = statusMap[status] || statusMap.OFFLINE
  return (
    <Tooltip title={info.label}>
      <CircleIcon sx={{ color: info.color, fontSize: size }} />
    </Tooltip>
  )
}
