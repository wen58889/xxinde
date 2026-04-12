import { Box, Button, TextField, Select, MenuItem, Checkbox, FormControlLabel, Tooltip, CircularProgress } from '@mui/material'
import CircleIcon from '@mui/icons-material/Circle'
import { useDeviceStore } from '../../stores/deviceStore'
import { useLogStore } from '../../stores/logStore'
import { devicesApi, tasksApi, visionApi } from '../../api/devices'
import { useState } from 'react'
import { colors } from '../../theme'

interface Props {
  onOpenMatchDialog?: () => void
}

export default function DeviceControls({ onOpenMatchDialog }: Props) {
  const selectedDeviceId = useDeviceStore((s) => s.selectedDeviceId)
  const device = useDeviceStore((s) => s.selectedDevice())
  const setVisionTargets = useDeviceStore((s) => s.setVisionTargets)
  const clearVisionTargets = useDeviceStore((s) => s.clearVisionTargets)
  const armLinkEnabled = useDeviceStore((s) => s.armLinkEnabled)
  const setArmLinkEnabled = useDeviceStore((s) => s.setArmLinkEnabled)
  const addLog = useLogStore((s) => s.addLog)
  const [ttsText, setTtsText] = useState('')
  const [orientation, setOrientation] = useState('竖屏')
  const [loading, setLoading] = useState<string | null>(null)

  const btn = (label: string, action: () => void, loadKey?: string) => (
    <Button
      size="small" variant="outlined" onClick={action}
      disabled={loading === loadKey}
      sx={{ minWidth: 'auto', px: 1 }}
    >
      {loading === loadKey ? <CircularProgress size={12} /> : label}
    </Button>
  )

  const withLoad = (key: string, fn: () => Promise<void>) => async () => {
    setLoading(key)
    try {
      await fn()
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      addLog(`操作失败: ${msg}`, 'error')
    } finally {
      setLoading(null)
    }
  }

  const handleHome = withLoad('home', async () => {
    if (!selectedDeviceId) { addLog('请先选择设备', 'warn'); return }
    addLog('发送 G28 归位指令...', 'info')
    await devicesApi.home(selectedDeviceId)
    addLog('机械臂归位完成 (G28)', 'success')
  })

  const handleReboot = withLoad('reboot', async () => {
    if (!selectedDeviceId) { addLog('请先选择设备', 'warn'); return }
    await visionApi.firmwareRestart(selectedDeviceId)
    addLog('设备固件重启中，请等待约10秒...', 'warn')
  })

  const handleSendText = withLoad('send', async () => {
    if (!selectedDeviceId) { addLog('请先选择设备', 'warn'); return }
    if (!ttsText.trim()) { addLog('请输入要发送的文字', 'warn'); return }
    await tasksApi.natural(`在当前输入框中输入文字: ${ttsText}`, selectedDeviceId)
    addLog(`文字指令已发送: ${ttsText}`, 'info')
    setTtsText('')
  })

  const handleDetectTargets = withLoad('vision_icon', async () => {
    if (!selectedDeviceId) { addLog('请先选择设备', 'warn'); return }
    addLog('识图: OpenCV模板匹配识别中...', 'info')
    try {
      const res = await visionApi.inspect(selectedDeviceId, 'detect_targets', { app: '_common' }) as any
      const targets = (res.result || []) as Array<{
        label: string; x: number; y: number; w: number; h: number; kind?: string; confidence?: number
      }>
      if (targets.length > 0) {
        setVisionTargets(targets)
        addLog(`识图: 模板匹配找到 ${targets.length} 个目标`, 'success')
      } else {
        setVisionTargets([])
        addLog('识图: 未匹配到模板目标，请确认模板图库已上传', 'warn')
      }
    } catch (e: unknown) {
      setVisionTargets([])
      const msg = e instanceof Error ? e.message : String(e)
      addLog(`识图失败: ${msg}`, 'error')
    }
  })

  const handleOCR = withLoad('vision_ocr', async () => {
    if (!selectedDeviceId) { addLog('请先选择设备', 'warn'); return }
    addLog('识字: PaddleOCR识别中...', 'info')
    const res = await visionApi.inspect(selectedDeviceId, 'read_text') as any
    const texts = res.result as Array<{ text: string; x: number; y: number; w: number; h: number; confidence: number }>
    if (!texts || texts.length === 0) {
      addLog('识字: 未找到文字', 'warn')
    } else {
      texts.slice(0, 8).forEach(t =>
        addLog(`识字: 「${t.text}」(${Math.round(t.x)},${Math.round(t.y)}) ${t.confidence ? `${(t.confidence * 100).toFixed(0)}%` : ''}`, 'info')
      )
      if (texts.length > 8) addLog(`...共 ${texts.length} 处文字`, 'info')
      // Show OCR results as vision targets for clicking
      const ocrTargets = texts
        .filter(t => t.text && t.text.trim())
        .slice(0, 24)
        .map(t => ({
          label: t.text.trim(),
          x: t.x, y: t.y,
          w: t.w || Math.max(64, t.text.trim().length * 20),
          h: t.h || 44,
          kind: 'text' as const,
          confidence: t.confidence || 0.5,
        }))
      setVisionTargets(ocrTargets)
    }
  })

  const handleRefreshImage = () => {
    if (!selectedDeviceId) { addLog('请先选择设备', 'warn'); return }
    clearVisionTargets()
    useDeviceStore.getState().triggerRefresh()
  }

  const statusColor = device?.status === 'ONLINE' ? colors.success
    : device?.status === 'ESTOP' ? colors.danger
    : '#888'

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5, mt: 1 }}>
      <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', alignItems: 'center' }}>
        {btn('重启', handleReboot, 'reboot')}
        {btn('复位', handleHome, 'home')}
        {btn('属性', () => addLog(`设备: ${device?.ip || '-'} | ${device?.hostname || '-'} | ${device?.status || 'OFFLINE'}`))} 
        <FormControlLabel
          control={<Checkbox size="small" checked={armLinkEnabled} onChange={(e) => setArmLinkEnabled(e.target.checked)} sx={{ color: armLinkEnabled ? colors.success : undefined, '&.Mui-checked': { color: colors.success } }} />}
          label="联动"
          sx={{ '& .MuiTypography-root': { fontSize: 13, color: armLinkEnabled ? colors.success : undefined } }}
        />
      </Box>
      <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center' }}>
        <TextField
          size="small"
          placeholder="图标名 / 输入文字..."
          value={ttsText}
          onChange={(e) => setTtsText(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') handleSendText() }}
          sx={{ flex: 1, '& input': { py: 0.5, fontSize: 13 } }}
        />
        <Button size="small" variant="contained" onClick={handleSendText}
          disabled={loading === 'send'}
          sx={{ minWidth: 48 }}>
          {loading === 'send' ? <CircularProgress size={12} /> : '发送'}
        </Button>
      </Box>
      <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', alignItems: 'center' }}>
        <Select
          size="small"
          value={orientation}
          onChange={(e) => setOrientation(e.target.value)}
          sx={{ height: 30, minWidth: 70, fontSize: 13 }}
        >
          <MenuItem value="竖屏">竖屏</MenuItem>
          <MenuItem value="横屏">横屏</MenuItem>
        </Select>
        <Tooltip title={device?.status || 'OFFLINE'}>
          <CircleIcon sx={{ color: statusColor, fontSize: 16 }} />
        </Tooltip>
        {btn('识图', onOpenMatchDialog || handleDetectTargets, 'vision_icon')}
        {btn('识字', handleOCR, 'vision_ocr')}
        {btn('刷新图像', handleRefreshImage, 'refresh_img')}
      </Box>
    </Box>
  )
}
