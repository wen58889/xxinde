import { useState, useEffect } from 'react'
import {
  Box, Button, Checkbox, Slider, Select, MenuItem, Typography,
  IconButton, CircularProgress,
} from '@mui/material'
import { useNavigate } from 'react-router-dom'
import ScreenRotationIcon from '@mui/icons-material/ScreenRotation'
import PublicIcon from '@mui/icons-material/Public'
import PlayArrowIcon from '@mui/icons-material/PlayArrow'
import StopIcon from '@mui/icons-material/Stop'
import AddIcon from '@mui/icons-material/Add'
import SaveIcon from '@mui/icons-material/Save'
import VolumeUpIcon from '@mui/icons-material/VolumeUp'
import OpenInFullIcon from '@mui/icons-material/OpenInFull'
import FiberManualRecordIcon from '@mui/icons-material/FiberManualRecord'
import ViewModuleIcon from '@mui/icons-material/ViewModule'
import FolderIcon from '@mui/icons-material/Folder'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import CancelIcon from '@mui/icons-material/Cancel'
import { useDeviceStore } from '../stores/deviceStore'
import { useLogStore } from '../stores/logStore'
import { devicesApi, templatesApi, tasksApi } from '../api/devices'
import { wsClient } from '../api/ws'
import type { Device } from '../types/device'

/* ─── Constants ─── */
const SIDEBAR_W = 210
const CARD_MIN_W = 150
const CARD_MAX_W = 420

/* ─── Device Preview Card ─── */
function DeviceCard({
  device, cardWidth, isRunning, taskResult,
}: {
  device: Device
  cardWidth: number
  isRunning?: boolean
  taskResult?: 'success' | 'failed'
}) {
  const [imgSrc, setImgSrc] = useState('')

  useEffect(() => {
    let active = true
    let objectUrl = ''
    const fetchFrame = async () => {
      const token = localStorage.getItem('token') || ''
      try {
        const res = await fetch(`/api/v1/devices/${device.id}/snapshot?t=${Date.now()}`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (!res.ok || !active) return
        const blob = await res.blob()
        const url = URL.createObjectURL(blob)
        if (objectUrl) URL.revokeObjectURL(objectUrl)
        objectUrl = url
        if (active) setImgSrc(url)
      } catch {
        // 网络失败静默处理
      }
    }
    fetchFrame()
    return () => {
      active = false
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [device.id])

  const phoneH = Math.round(cardWidth * 1.95)

  return (
    <Box sx={{
      width: cardWidth,
      border: '1px solid #2a3a4a',
      borderRadius: '4px',
      overflow: 'hidden',
      bgcolor: '#0f1520',
      flexShrink: 0,
    }}>
      {/* Card header */}
      <Box sx={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        px: 1,
        height: 32,
        bgcolor: '#182232',
        borderBottom: '1px solid #2a3a4a',
      }}>
        <Typography sx={{ fontSize: 12, color: '#d0d0d0', fontWeight: 500, lineHeight: 1 }}>
          {device.ip}
        </Typography>
        <Box sx={{ display: 'flex', gap: 0.25 }}>
          <IconButton size="small" sx={{ p: 0.25, color: '#7a8a9a' }}>
            <VolumeUpIcon sx={{ fontSize: 16 }} />
          </IconButton>
          <IconButton size="small" sx={{ p: 0.25, color: '#7a8a9a' }}>
            <OpenInFullIcon sx={{ fontSize: 14 }} />
          </IconButton>
        </Box>
      </Box>
      {/* Phone screen */}
      <Box sx={{
        width: '100%',
        height: phoneH,
        bgcolor: '#000',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        position: 'relative',
      }}>
        {imgSrc ? (
          <img
            src={imgSrc}
            alt={device.ip}
            style={{ width: '100%', height: '100%', objectFit: 'contain' }}
          />
        ) : (
          <Typography sx={{ fontSize: 11, color: '#333' }}>无信号</Typography>
        )}
        {/* Running overlay */}
        {isRunning && (
          <Box sx={{
            position: 'absolute', inset: 0,
            bgcolor: 'rgba(0,0,0,0.55)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <CircularProgress size={28} sx={{ color: '#42a5f5' }} />
          </Box>
        )}
        {/* Result badge */}
        {!isRunning && taskResult === 'success' && (
          <Box sx={{
            position: 'absolute', bottom: 4, right: 4,
            bgcolor: '#1b5e20', borderRadius: '50%', p: '2px', lineHeight: 0,
          }}>
            <CheckCircleIcon sx={{ fontSize: 16, color: '#69f0ae' }} />
          </Box>
        )}
        {!isRunning && taskResult === 'failed' && (
          <Box sx={{
            position: 'absolute', bottom: 4, right: 4,
            bgcolor: '#b71c1c', borderRadius: '50%', p: '2px', lineHeight: 0,
          }}>
            <CancelIcon sx={{ fontSize: 16, color: '#ffcdd2' }} />
          </Box>
        )}
      </Box>
    </Box>
  )
}

/* ─── Group Control Page ─── */
export default function GroupControl() {
  const nav = useNavigate()
  const devices = useDeviceStore((s) => s.devices)
  const fetchDevices = useDeviceStore((s) => s.fetchDevices)
  const addLog = useLogStore((s) => s.addLog)

  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [viewScale, setViewScale] = useState(35)
  const [selectedScript, setSelectedScript] = useState('')
  const [scripts, setScripts] = useState<{ id: number; name: string; yaml_content: string }[]>([])
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [scanning, setScanning] = useState(false)
  const [runningIds, setRunningIds] = useState<Set<number>>(new Set())
  const [taskResults, setTaskResults] = useState<Record<number, 'success' | 'failed'>>({})  

  const cardWidth = CARD_MIN_W + (viewScale / 100) * (CARD_MAX_W - CARD_MIN_W)

  /* Visible devices = checked only, or all if nothing is checked */
  const visibleDevices = selectedIds.size > 0
    ? devices.filter((d) => selectedIds.has(d.id))
    : devices
  const totalPages = Math.ceil(visibleDevices.length / pageSize) || 1
  const pagedDevices = visibleDevices.slice((page - 1) * pageSize, page * pageSize)

  /* ── handlers ── */
  const toggleDevice = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }

  const toggleAll = () => {
    if (selectedIds.size === devices.length) setSelectedIds(new Set())
    else setSelectedIds(new Set(devices.map((d) => d.id)))
  }

  const handleScan = async () => {
    setScanning(true)
    try {
      await fetchDevices()
      addLog('设备扫描完成', 'success')
    } catch (e) {
      addLog(`扫描失败: ${e}`, 'error')
    } finally {
      setScanning(false)
    }
  }

  const handleRunAll = async () => {
    if (!selectedScript) { addLog('请先选择脚本', 'warn'); return }
    const tpl = scripts.find(s => s.name === selectedScript)
    if (!tpl?.yaml_content) { addLog('脚本内容为空', 'warn'); return }

    const targetIds = selectedIds.size > 0 ? [...selectedIds] : devices.map(d => d.id)
    const onlineIds = devices
      .filter(d => targetIds.includes(d.id) && d.status === 'ONLINE')
      .map(d => d.id)

    if (onlineIds.length === 0) { addLog('没有在线设备可运行', 'warn'); return }

    setRunningIds(new Set(onlineIds))
    setTaskResults({})
    try {
      await tasksApi.batchRun(onlineIds, tpl.yaml_content)
      addLog(`已向 ${onlineIds.length} 台在线设备下发脚本`, 'success')
    } catch (e) {
      addLog(`批量运行失败: ${e}`, 'error')
      setRunningIds(new Set())
    }
  }

  const handleStopAll = async () => {
    try {
      for (const d of devices) { await tasksApi.stop(d.id).catch(() => {}) }
      addLog('全部已停止', 'warn')
    } catch (e) {
      addLog(`停止失败: ${e}`, 'error')
    }
  }

  useEffect(() => {
    fetchDevices()
    templatesApi.list().then((list: any[]) => {
      setScripts(list.map((t) => ({ id: t.id, name: t.name, yaml_content: t.yaml_content })))
    }).catch(() => {})
  }, [])

  // WS subscription: track task running/complete per device
  useEffect(() => {
    const unsub = wsClient.subscribe((event, data) => {
      const deviceId = data.device_id as number
      if (event === 'task_progress') {
        setRunningIds(prev => new Set([...prev, deviceId]))
      } else if (event === 'task_complete') {
        setRunningIds(prev => { const s = new Set(prev); s.delete(deviceId); return s })
        const status = data.status as string
        if (status === 'SUCCESS') {
          setTaskResults(prev => ({ ...prev, [deviceId]: 'success' }))
        } else if (status === 'FAILED' || status === 'STOPPED') {
          setTaskResults(prev => ({ ...prev, [deviceId]: 'failed' }))
        }
      }
    })
    return unsub
  }, [])

  useEffect(() => {
    if (devices.length > 0 && selectedIds.size === 0) {
      setSelectedIds(new Set(devices.map((d) => d.id)))
    }
  }, [devices.length])

  return (
    <Box sx={{ display: 'flex', height: '100vh', bgcolor: '#111827' }}>

      {/* ══════════════ Left Sidebar ══════════════ */}
      <Box sx={{
        width: SIDEBAR_W,
        flexShrink: 0,
        bgcolor: '#0c1219',
        borderRight: '1px solid #1e293b',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}>
        {/* ─ 返回主页 ─ */}
        <Box sx={{ px: 1.5, pt: 1.5, pb: 0.75 }}>
          <Typography
            onClick={() => nav('/')}
            sx={{
              fontSize: 13, color: '#4da3ff', cursor: 'pointer',
              '&:hover': { textDecoration: 'underline' },
            }}
          >
            {'< 返回主页'}
          </Typography>
        </Box>

        {/* ─ 全局控制 ─ */}
        <Box sx={{ px: 1.5, pb: 1.5 }}>
          <Typography sx={{ fontSize: 13, fontWeight: 700, color: '#e0e0e0', mb: 1 }}>
            全局控制
          </Typography>
          <Button
            fullWidth variant="contained" onClick={handleScan} disabled={scanning}
            startIcon={
              <FiberManualRecordIcon sx={{ fontSize: '10px !important', color: '#4caf50' }} />
            }
            sx={{
              bgcolor: '#1976d2', textTransform: 'none',
              fontSize: 13, fontWeight: 500, height: 34, borderRadius: '4px', mb: 1,
              '&:hover': { bgcolor: '#1565c0' },
            }}
          >
            扫描设备
          </Button>
          <Box sx={{ display: 'flex', justifyContent: 'center' }}>
            <Button
              variant="text"
              startIcon={<ScreenRotationIcon sx={{ fontSize: 16 }} />}
              sx={{
                color: '#90a4ae', textTransform: 'none',
                fontSize: 12, height: 28,
              }}
            >
              屏幕旋转
            </Button>
          </Box>
        </Box>

        {/* ─ 视图设置 ─ */}
        <Box sx={{ px: 1.5, pb: 1.5 }}>
          <Typography sx={{ fontSize: 13, fontWeight: 700, color: '#e0e0e0', mb: 0.75 }}>
            视图设置
          </Typography>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Typography sx={{ fontSize: 11, color: '#777', flexShrink: 0 }}>小</Typography>
            <Slider
              value={viewScale}
              onChange={(_, v) => setViewScale(v as number)}
              size="small"
              sx={{
                color: '#1976d2',
                '& .MuiSlider-thumb': { width: 14, height: 14 },
                '& .MuiSlider-track': { height: 3 },
                '& .MuiSlider-rail': { height: 3, bgcolor: '#2a3a4a' },
              }}
            />
            <Typography sx={{ fontSize: 11, color: '#777', flexShrink: 0 }}>大</Typography>
          </Box>
        </Box>

        {/* ─ 全局脚本 ─ */}
        <Box sx={{ px: 1.5, pb: 1.5 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.75 }}>
            <PublicIcon sx={{ fontSize: 16, color: '#4da3ff' }} />
            <Typography sx={{ fontSize: 13, fontWeight: 700, color: '#e0e0e0' }}>
              全局脚本
            </Typography>
          </Box>
          <Select
            value={selectedScript} onChange={(e) => setSelectedScript(e.target.value)}
            displayEmpty fullWidth size="small"
            sx={{
              height: 32, fontSize: 12, bgcolor: '#111d2c', mb: 1,
              color: '#99a',
              '& .MuiSelect-select': { py: 0.75 },
              '& fieldset': { borderColor: '#1e293b' },
            }}
            MenuProps={{ PaperProps: { sx: { bgcolor: '#1a2332' } } }}
          >
            <MenuItem value="" disabled sx={{ fontSize: 12 }}>
              <em style={{ color: '#667' }}>选择脚本...</em>
            </MenuItem>
            {scripts.map((s) => (
              <MenuItem key={s.id} value={s.name} sx={{ fontSize: 12 }}>{s.name}</MenuItem>
            ))}
          </Select>
          <Box sx={{ display: 'flex', gap: 0.5 }}>
            <Button
              variant="contained" onClick={handleRunAll}
              startIcon={<PlayArrowIcon sx={{ fontSize: '14px !important' }} />}
              sx={{
                bgcolor: '#388e3c', textTransform: 'none', fontSize: 12,
                height: 30, flex: 1, fontWeight: 600,
                '&:hover': { bgcolor: '#2e7d32' },
              }}
            >
              运行全部
            </Button>
            <Button
              variant="contained" onClick={handleStopAll}
              sx={{
                bgcolor: '#d32f2f', minWidth: 34, width: 34, height: 30, p: 0,
                '&:hover': { bgcolor: '#c62828' },
              }}
            >
              <StopIcon sx={{ fontSize: 16 }} />
            </Button>
          </Box>
        </Box>

        {/* ─ 设备与分组 ─ */}
        <Box sx={{ px: 1.5, flex: 1, overflow: 'auto', pb: 1 }}>
          <Box sx={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5,
          }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
              <FolderIcon sx={{ fontSize: 15, color: '#ffb74d' }} />
              <Typography sx={{ fontSize: 13, fontWeight: 700, color: '#e0e0e0' }}>
                设备与分组 ({devices.length})
              </Typography>
            </Box>
            <Box sx={{ display: 'flex', gap: 0 }}>
              <IconButton size="small" sx={{ color: '#7a8a9a', p: 0.3 }}>
                <AddIcon sx={{ fontSize: 16 }} />
              </IconButton>
              <IconButton size="small" sx={{ color: '#7a8a9a', p: 0.3 }}>
                <SaveIcon sx={{ fontSize: 15 }} />
              </IconButton>
            </Box>
          </Box>

          {/* Group: 未分组 */}
          <Box
            onClick={toggleAll}
            sx={{
              display: 'flex', alignItems: 'center', gap: 0.5,
              py: 0.3, px: 0.5, cursor: 'pointer', borderRadius: '3px',
              '&:hover': { bgcolor: '#152030' },
            }}
          >
            <Box sx={{
              width: 10, height: 10, bgcolor: '#4a5568', borderRadius: '2px', flexShrink: 0,
            }} />
            <Typography sx={{ fontSize: 12, color: '#b0bec5' }}>
              未分组 ({devices.length})
            </Typography>
          </Box>

          {/* Device list */}
          <Box sx={{ pl: 0.25 }}>
            {devices.map((d) => (
              <Box
                key={d.id}
                onClick={() => toggleDevice(d.id)}
                sx={{
                  display: 'flex', alignItems: 'center',
                  py: 0.15, pr: 0.5, cursor: 'pointer', borderRadius: '3px',
                  '&:hover': { bgcolor: '#152030' },
                }}
              >
                <Checkbox
                  checked={selectedIds.has(d.id)}
                  size="small"
                  sx={{
                    p: 0.3, color: '#4a5568',
                    '&.Mui-checked': { color: '#1976d2' },
                    '& .MuiSvgIcon-root': { fontSize: 16 },
                  }}
                />
                <Typography sx={{ fontSize: 12, color: '#cfd8dc', flex: 1, lineHeight: 1 }}>
                  {d.ip}
                </Typography>
                <FiberManualRecordIcon
                  sx={{
                    fontSize: 8,
                    color: d.status === 'ONLINE' ? '#4caf50'
                      : d.status === 'ESTOP' ? '#f44336' : '#37474f',
                  }}
                />
              </Box>
            ))}
          </Box>
        </Box>
      </Box>

      {/* ══════════════ Main Content ══════════════ */}
      <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

        {/* ─ Tab bar ─ */}
        <Box sx={{ borderBottom: '1px solid #1e293b', px: 2 }}>
          <Box sx={{
            display: 'inline-flex', alignItems: 'center', gap: 0.5,
            py: 1.25, borderBottom: '2px solid #1976d2',
          }}>
            <ViewModuleIcon sx={{ fontSize: 16, color: '#4da3ff' }} />
            <Typography sx={{ fontSize: 13, fontWeight: 600, color: '#e0e0e0' }}>
              投屏监控墙
            </Typography>
          </Box>
        </Box>

        {/* ─ Device grid ─ */}
        <Box sx={{
          flex: 1, overflow: 'auto', p: 2,
          display: 'flex', flexWrap: 'wrap', gap: 2,
          alignContent: 'flex-start',
        }}>
          {pagedDevices.map((d) => (
            <DeviceCard
              key={d.id}
              device={d}
              cardWidth={cardWidth}
              isRunning={runningIds.has(d.id)}
              taskResult={taskResults[d.id]}
            />
          ))}
          {pagedDevices.length === 0 && (
            <Typography sx={{ color: '#4a5568', fontSize: 13, m: 'auto' }}>
              暂无设备，请点击"扫描设备"
            </Typography>
          )}
        </Box>

        {/* ─ Pagination ─ */}
        <Box sx={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          gap: 1.5, py: 0.75,
          borderTop: '1px solid #1e293b', bgcolor: '#0c1219',
        }}>
          <Button
            size="small" disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
            sx={{ color: '#7a8a9a', textTransform: 'none', fontSize: 12, minWidth: 'auto' }}
          >
            上一页
          </Button>
          <Typography sx={{ fontSize: 12, color: '#b0bec5', mx: 0.5 }}>
            {page} / {totalPages}
          </Typography>
          <Button
            size="small" disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
            sx={{ color: '#7a8a9a', textTransform: 'none', fontSize: 12, minWidth: 'auto' }}
          >
            下一页
          </Button>
          <Select
            value={pageSize}
            onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1) }}
            size="small"
            sx={{
              height: 26, fontSize: 12, color: '#b0bec5',
              '& .MuiSelect-select': { py: 0.25, px: 1 },
              '& fieldset': { borderColor: '#1e293b' },
            }}
            MenuProps={{ PaperProps: { sx: { bgcolor: '#1a2332' } } }}
          >
            {[10, 20, 50, 100].map((n) => (
              <MenuItem key={n} value={n} sx={{ fontSize: 12 }}>{n}/页</MenuItem>
            ))}
          </Select>
        </Box>
      </Box>
    </Box>
  )
}
