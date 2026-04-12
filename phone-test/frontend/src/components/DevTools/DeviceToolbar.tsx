import { useEffect } from 'react'
import { Box, Select, MenuItem, Button, TextField } from '@mui/material'
import SearchIcon from '@mui/icons-material/Search'
import { useDeviceStore } from '../../stores/deviceStore'
import { useLogStore } from '../../stores/logStore'
import { devicesApi } from '../../api/devices'
import { ensureToken } from '../../api/client'

export default function DeviceToolbar() {
  const { devices, selectedDeviceId, setDevices, selectDevice, fetchDevices } = useDeviceStore()
  const addLog = useLogStore((s) => s.addLog)

  // Auto-scan on mount (wait for token first)
  useEffect(() => {
    ensureToken().then(() => fetchDevices()).catch(() => {})
  }, [])

  // Auto-select first device when list loads
  useEffect(() => {
    if (devices.length > 0 && !selectedDeviceId) {
      selectDevice(devices[0].id)
    }
  }, [devices.length])

  const handleScan = async () => {
    await ensureToken()
    addLog('正在扫描局域网设备...')
    try {
      const list = await devicesApi.scan()
      setDevices(list)
      const online = list.filter((d) => d.status === 'ONLINE').length
      addLog(`扫描完成，${list.length} 台设备中 ${online} 台在线`, online > 0 ? 'success' : 'warn')
      const first = list.find((d) => d.status === 'ONLINE')
      if (first && !selectedDeviceId) selectDevice(first.id)
    } catch (e) {
      addLog(`扫描失败: ${e}`, 'error')
    }
  }

  const selected = devices.find((d) => d.id === selectedDeviceId)

  return (
    <Box sx={{ display: 'flex', flexWrap: 'nowrap', gap: 0.5, mb: 1, alignItems: 'center' }}>
      <Button size="small" variant="contained" startIcon={<SearchIcon />} onClick={handleScan}>
        扫描设备
      </Button>
      <TextField
        size="small"
        placeholder="IP地址"
        value={selected?.ip || ''}
        sx={{ width: 130, '& input': { py: 0.5, fontSize: 13 } }}
        slotProps={{ input: { readOnly: true } }}
      />
      <Select
        size="small"
        value={selectedDeviceId || ''}
        onChange={(e) => selectDevice(Number(e.target.value))}
        displayEmpty
        sx={{ minWidth: 120, height: 32 }}
      >
        {devices.map((d) => (
          <MenuItem key={d.id} value={d.id}>{d.hostname} ({d.ip})</MenuItem>
        ))}
      </Select>
    </Box>
  )
}
