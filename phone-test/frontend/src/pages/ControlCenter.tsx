import { useState, useEffect } from 'react'
import {
  Box, Typography, Grid, Card, CardActionArea, CardContent,
  TextField, Button, Paper, Chip, CircularProgress,
} from '@mui/material'
import { useNavigate } from 'react-router-dom'
import BuildIcon from '@mui/icons-material/Build'
import GroupWorkIcon from '@mui/icons-material/GroupWork'
import TuneIcon from '@mui/icons-material/Tune'
import SettingsIcon from '@mui/icons-material/Settings'
import BiotechIcon from '@mui/icons-material/Biotech'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import CancelIcon from '@mui/icons-material/Cancel'
import BlockIcon from '@mui/icons-material/Block'
import SendIcon from '@mui/icons-material/Send'
import RefreshIcon from '@mui/icons-material/Refresh'
import { colors } from '../theme'
import { useDeviceStore } from '../stores/deviceStore'
import { useLogStore } from '../stores/logStore'
import { tasksApi } from '../api/devices'

const pages = [
  { path: '/devtools', label: '开发者工具', desc: '单设备脚本调试', icon: <BuildIcon sx={{ fontSize: 40 }} /> },
  { path: '/group', label: '群控中心', desc: '批量任务管理', icon: <GroupWorkIcon sx={{ fontSize: 40 }} /> },
  { path: '/calibration', label: '标定工具', desc: '坐标映射校准', icon: <TuneIcon sx={{ fontSize: 40 }} /> },
  { path: '/settings', label: '系统设置', desc: '全局配置', icon: <SettingsIcon sx={{ fontSize: 40 }} /> },
  { path: '/vision-test', label: '视觉模型测试', desc: 'vLLM 部署与推理验证', icon: <BiotechIcon sx={{ fontSize: 40 }} /> },
]

export default function ControlCenter() {
  const nav = useNavigate()
  const devices = useDeviceStore((s) => s.devices)
  const fetchDevices = useDeviceStore((s) => s.fetchDevices)
  const addLog = useLogStore((s) => s.addLog)
  const [nlpInput, setNlpInput] = useState('')
  const [nlpLoading, setNlpLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)

  useEffect(() => { fetchDevices() }, [])

  const online = devices.filter(d => d.status === 'ONLINE').length
  const offline = devices.filter(d => d.status === 'OFFLINE').length
  const suspect = devices.filter(d => d.status === 'SUSPECT' || d.status === 'RECOVERING').length
  const estop = devices.filter(d => d.status === 'ESTOP').length

  const handleRefresh = async () => {
    setRefreshing(true)
    await fetchDevices().catch(() => {})
    setRefreshing(false)
  }

  const handleNlp = async () => {
    if (!nlpInput.trim()) return
    setNlpLoading(true)
    try {
      const res = await tasksApi.natural(nlpInput)
      addLog((res as any).data.message, 'success')
      setNlpInput('')
    } catch (e) {
      addLog(`指令执行失败: ${e}`, 'error')
    } finally {
      setNlpLoading(false)
    }
  }

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: colors.bg, p: 3, maxWidth: 820, mx: 'auto' }}>
      <Typography variant="h4" sx={{ mb: 3, fontWeight: 700, textAlign: 'center' }}>
        手机自动化测试平台
      </Typography>

      {/* Device status stats */}
      <Paper sx={{ p: 2, mb: 3, bgcolor: colors.card }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1.5 }}>
          <Typography variant="subtitle2" sx={{ color: '#aaa' }}>
            设备状态（共 {devices.length} 台）
          </Typography>
          <Button
            size="small" startIcon={refreshing ? <CircularProgress size={12} /> : <RefreshIcon sx={{ fontSize: 14 }} />}
            onClick={handleRefresh} disabled={refreshing}
            sx={{ fontSize: 12, color: '#aaa', textTransform: 'none' }}
          >
            刷新
          </Button>
        </Box>
        <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap' }}>
          <Chip
            icon={<CheckCircleIcon sx={{ fontSize: 16 }} />}
            label={`在线 ${online}`}
            sx={{ bgcolor: '#1b5e20', color: '#69f0ae', '& .MuiChip-icon': { color: '#69f0ae' } }}
          />
          <Chip
            icon={<CancelIcon sx={{ fontSize: 16 }} />}
            label={`离线 ${offline}`}
            sx={{ bgcolor: '#37474f', color: '#90a4ae', '& .MuiChip-icon': { color: '#90a4ae' } }}
          />
          {suspect > 0 && (
            <Chip
              label={`恢复中 ${suspect}`}
              sx={{ bgcolor: '#4e342e', color: '#ffccbc' }}
            />
          )}
          {estop > 0 && (
            <Chip
              icon={<BlockIcon sx={{ fontSize: 16 }} />}
              label={`急停 ${estop}`}
              sx={{ bgcolor: '#b71c1c', color: '#ffcdd2', '& .MuiChip-icon': { color: '#ffcdd2' } }}
            />
          )}
        </Box>
      </Paper>

      {/* Natural language input */}
      <Paper sx={{ p: 2, mb: 3, bgcolor: colors.card }}>
        <Typography variant="subtitle2" sx={{ mb: 1.5, color: '#aaa' }}>
          自然语言指令
        </Typography>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <TextField
            fullWidth size="small"
            placeholder="例如：让设备1打开微信并发消息"
            value={nlpInput}
            onChange={(e) => setNlpInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) handleNlp() }}
            disabled={nlpLoading}
          />
          <Button
            variant="contained"
            onClick={handleNlp}
            disabled={nlpLoading || !nlpInput.trim()}
            endIcon={nlpLoading ? <CircularProgress size={16} /> : <SendIcon />}
            sx={{ minWidth: 80 }}
          >
            执行
          </Button>
        </Box>
      </Paper>

      {/* Navigation cards */}
      <Grid container spacing={3}>
        {pages.map((p) => (
          <Grid item xs={6} key={p.path}>
            <Card sx={{ bgcolor: colors.card, border: '1px solid #333', '&:hover': { borderColor: colors.highlight } }}>
              <CardActionArea onClick={() => nav(p.path)}>
                <CardContent sx={{ textAlign: 'center', py: 4 }}>
                  {p.icon}
                  <Typography variant="h6" sx={{ mt: 1 }}>{p.label}</Typography>
                  <Typography variant="caption" sx={{ color: '#888' }}>{p.desc}</Typography>
                </CardContent>
              </CardActionArea>
            </Card>
          </Grid>
        ))}
      </Grid>
    </Box>
  )
}
