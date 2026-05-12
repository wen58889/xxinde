import { useState, useEffect } from 'react'
import { Box, Select, MenuItem, Button, TextField, IconButton, Tooltip, Dialog, DialogTitle, DialogContent, Typography } from '@mui/material'
import SearchIcon from '@mui/icons-material/Search'
import AddIcon from '@mui/icons-material/AddCircleOutline'
import DeleteIcon from '@mui/icons-material/DeleteOutline'
import DiagnoseIcon from '@mui/icons-material/Troubleshoot'
import { useDeviceStore } from '../../stores/deviceStore'
import { useLogStore } from '../../stores/logStore'
import { devicesApi } from '../../api/devices'
import { ensureToken } from '../../api/client'

export default function DeviceToolbar() {
  const { devices, selectedDeviceId, setDevices, selectDevice, fetchDevices } = useDeviceStore()
  const addLog = useLogStore((s) => s.addLog)
  const [manualIp, setManualIp] = useState('')
  const [adding, setAdding] = useState(false)
  const [diagOpen, setDiagOpen] = useState(false)
  const [diagResult, setDiagResult] = useState<Record<string, unknown> | null>(null)
  const [diagLoading, setDiagLoading] = useState(false)

  useEffect(() => {
    ensureToken().then(() => fetchDevices()).catch(() => {})
  }, [])

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

  const handleAddDevice = async () => {
    const ip = manualIp.trim()
    if (!ip || !/^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(ip)) {
      addLog('请输入正确的IP地址', 'warn')
      return
    }
    setAdding(true)
    try {
      await ensureToken()
      const dev = await devicesApi.create(ip)
      addLog(`设备已添加: ${dev.hostname} (${dev.ip}) 状态=${dev.status}`, 'success')
      setManualIp('')
      const list = await devicesApi.list()
      setDevices(list)
      selectDevice(dev.id)
    } catch (e: any) {
      const msg = e?.response?.data?.detail || String(e)
      addLog(`添加设备失败: ${msg}`, 'error')
    } finally {
      setAdding(false)
    }
  }

  const handleDeleteDevice = async () => {
    if (!selectedDeviceId) return
    const sel = devices.find((d) => d.id === selectedDeviceId)
    if (!sel) return
    if (!confirm(`确认删除设备 ${sel.hostname} (${sel.ip})？`)) return
    try {
      await ensureToken()
      await devicesApi.delete(selectedDeviceId)
      addLog(`设备已删除: ${sel.hostname} (${sel.ip})`, 'success')
      const list = await devicesApi.list()
      setDevices(list)
      if (list.length > 0) selectDevice(list[0].id)
    } catch (e) {
      addLog(`删除设备失败: ${e}`, 'error')
    }
  }

  const handleDiagnose = async () => {
    if (!selectedDeviceId) return
    setDiagLoading(true)
    setDiagOpen(true)
    setDiagResult(null)
    try {
      await ensureToken()
      const result = await devicesApi.diagnose(selectedDeviceId)
      setDiagResult(result as unknown as Record<string, unknown>)
      const mk = result.moonraker?.reachable
      const cam = result.camera?.go2rtc_reachable
      const snap = result.camera?.snapshot_ok
      addLog(`诊断 ${result.ip}: Moonraker=${mk ? 'OK' : 'FAIL'} go2rtc=${cam ? 'OK' : 'FAIL'} 截图=${snap ? 'OK' : 'FAIL'}`, mk && cam && snap ? 'success' : 'warn')
    } catch (e) {
      addLog(`诊断失败: ${e}`, 'error')
    } finally {
      setDiagLoading(false)
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
        placeholder="输入IP添加设备"
        value={manualIp}
        onChange={(e) => setManualIp(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') handleAddDevice() }}
        sx={{ width: 150, '& input': { py: 0.5, fontSize: 13 } }}
      />
      <IconButton size="small" onClick={handleAddDevice} disabled={adding || !manualIp.trim()} sx={{ color: '#4caf50' }}>
        <AddIcon sx={{ fontSize: 18 }} />
      </IconButton>
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
      {selected && (
        <Tooltip title="诊断设备连通性">
          <IconButton size="small" onClick={handleDiagnose} disabled={diagLoading} sx={{ color: '#ff9800' }}>
            <DiagnoseIcon sx={{ fontSize: 16 }} />
          </IconButton>
        </Tooltip>
      )}
      {selected && (
        <Tooltip title="删除此设备">
          <IconButton size="small" onClick={handleDeleteDevice} sx={{ color: '#ef5350' }}>
            <DeleteIcon sx={{ fontSize: 16 }} />
          </IconButton>
        </Tooltip>
      )}

      <Dialog open={diagOpen} onClose={() => setDiagOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>设备连通性诊断</DialogTitle>
        <DialogContent>
          {diagLoading ? <Typography>正在检测...</Typography> : diagResult && (
            <Box sx={{ fontFamily: 'monospace', fontSize: 13, whiteSpace: 'pre-wrap' }}>
              <Typography fontWeight="bold" sx={{ mb: 1 }}>IP: {(diagResult as any).ip} | 状态: {(diagResult as any).status}</Typography>
              <Typography fontWeight="bold">Moonraker (端口7125):</Typography>
              <Typography sx={{ ml: 2, color: (diagResult as any).moonraker?.reachable ? 'success.main' : 'error.main' }}>
                {(diagResult as any).moonraker?.reachable ? '✅ 可连接' : '❌ 不可连接'}
                {(diagResult as any).moonraker?.klippy_connected !== undefined && ` | klippy_connected=${(diagResult as any).moonraker.klippy_connected}`}
                {(diagResult as any).moonraker?.error && ` | 错误: ${(diagResult as any).moonraker.error}`}
              </Typography>
              <Typography fontWeight="bold" sx={{ mt: 1 }}>go2rtc 摄像头 (端口1984):</Typography>
              <Typography sx={{ ml: 2, color: (diagResult as any).camera?.go2rtc_reachable ? 'success.main' : 'error.main' }}>
                {(diagResult as any).camera?.go2rtc_reachable ? '✅ go2rtc可连接' : '❌ go2rtc不可连接'}
                {(diagResult as any).camera?.streams?.length > 0 && ` | 流: ${(diagResult as any).camera.streams.join(', ')}`}
              </Typography>
              <Typography sx={{ ml: 2, color: (diagResult as any).camera?.snapshot_ok ? 'success.main' : 'error.main' }}>
                {(diagResult as any).camera?.snapshot_ok ? '✅ 截图正常' : '❌ 截图失败'}
                {(diagResult as any).camera?.snapshot_status && ` | HTTP ${(diagResult as any).camera.snapshot_status}`}
                {(diagResult as any).camera?.snapshot_error && ` | 错误: ${(diagResult as any).camera.snapshot_error}`}
              </Typography>
              {!((diagResult as any).moonraker?.reachable) && (
                <Typography color="warning.main" sx={{ mt: 2 }}>
                  ⚠ Moonraker不可连接，请检查：1) N1设备是否开机 2) IP是否正确 3) Moonraker服务是否运行 (SSH: systemctl status moonraker)
                </Typography>
              )}
              {(diagResult as any).moonraker?.reachable && !((diagResult as any).camera?.go2rtc_reachable) && (
                <Typography color="warning.main" sx={{ mt: 2 }}>
                  ⚠ go2rtc不可连接，请SSH到N1设备检查：1) systemctl status go2rtc 2) ls /dev/video* 3) 摄像头USB是否插好
                </Typography>
              )}
            </Box>
          )}
        </DialogContent>
      </Dialog>
    </Box>
  )
}
