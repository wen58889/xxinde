import { Box, Button, TextField, Select, MenuItem, Checkbox, FormControlLabel, Tooltip, CircularProgress, Typography, Collapse } from '@mui/material'
import CircleIcon from '@mui/icons-material/Circle'
import VisibilityIcon from '@mui/icons-material/Visibility'
import PsychologyIcon from '@mui/icons-material/Psychology'
import PlayArrowIcon from '@mui/icons-material/PlayArrow'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import ErrorIcon from '@mui/icons-material/Error'
import { useDeviceStore } from '../../stores/deviceStore'
import { useLogStore } from '../../stores/logStore'
import { useAgentStore, AgentStepInfo } from '../../stores/agentStore'
import { wsClient } from '../../api/ws'
import { devicesApi, tasksApi, visionApi } from '../../api/devices'
import client from '../../api/client'
import { useState, useEffect } from 'react'
import { colors } from '../../theme'

const PHASE_ICON: Record<AgentStepInfo['phase'] | '', React.ReactNode> = {
  '': null,
  observing: <VisibilityIcon sx={{ fontSize: 14, color: '#2196f3' }} />,
  thinking: <PsychologyIcon sx={{ fontSize: 14, color: '#ff9800' }} />,
  acting: <PlayArrowIcon sx={{ fontSize: 14, color: '#4caf50' }} />,
  done: <CheckCircleIcon sx={{ fontSize: 14, color: colors.success }} />,
}

const PHASE_LABEL: Record<AgentStepInfo['phase'], string> = {
  observing: '观察',
  thinking: '思考',
  acting: '执行',
  done: '完成',
}

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

  const agentRunning = useAgentStore((s) => s.running)
  const agentSteps = useAgentStore((s) => s.steps)
  const currentStep = useAgentStore((s) => s.currentStep)
  const currentPhase = useAgentStore((s) => s.currentPhase)
  const statusMessage = useAgentStore((s) => s.statusMessage)
  const agentSetRunning = useAgentStore((s) => s.setRunning)
  const agentReset = useAgentStore((s) => s.reset)
  const onObserve = useAgentStore((s) => s.onObserve)
  const onThink = useAgentStore((s) => s.onThink)
  const onStep = useAgentStore((s) => s.onStep)
  const onStatus = useAgentStore((s) => s.onStatus)

  const [ttsText, setTtsText] = useState('')
  const [agentTask, setAgentTask] = useState('')
  const [orientation, setOrientation] = useState('竖屏')
  const [loading, setLoading] = useState<string | null>(null)
  const [agentPanelOpen, setAgentPanelOpen] = useState(false)

  useEffect(() => {
    const unsub = wsClient.subscribe((event, data) => {
      const did = data.device_id as number
      if (selectedDeviceId && did !== selectedDeviceId) return
      switch (event) {
        case 'agent_status':
          onStatus(did, data.status as string, data as Record<string, unknown>)
          break
        case 'agent_observe':
          onObserve(did, data.step as number, (data.observation as string) || '')
          break
        case 'agent_think':
          onThink(did, data.step as number, (data.thought as string) || '', (data.action as string) || '')
          break
        case 'agent_step':
          onStep(did, data as Partial<AgentStepInfo> & { step: number })
          break
      }
    })
    return unsub
  }, [selectedDeviceId, onStatus, onObserve, onThink, onStep])

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
    try {
      const res = await client.post('/tts/synthesize', {
        text: ttsText.trim(),
        device_id: selectedDeviceId,
      }).then(r => r.data)
      const playedOn = res.played_on ? ` → ${res.played_on} 播放中` : ''
      addLog(`TTS: "${ttsText.trim()}" (${res.duration_ms}ms${playedOn})`, 'success')
    } catch (e: any) {
      const detail = e?.response?.data?.detail || (e instanceof Error ? e.message : String(e))
      addLog(`TTS失败: ${detail}`, 'error')
    }
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

  const handleAgentStart = async () => {
    if (!selectedDeviceId) { addLog('请先选择设备', 'warn'); return }
    if (!agentTask.trim()) { addLog('请输入AI任务描述', 'warn'); return }
    agentReset()
    try {
      await client.post(`/agent/devices/${selectedDeviceId}/start`, { task: agentTask.trim(), max_steps: 30 })
      agentSetRunning(true)
      setAgentPanelOpen(true)
      addLog(`AI Agent 已启动: "${agentTask.trim()}"`, 'success')
    } catch (e: any) {
      const detail = e?.response?.data?.detail || (e instanceof Error ? e.message : String(e))
      addLog(`Agent启动失败: ${detail}`, 'error')
    }
  }

  const handleAgentStop = async () => {
    if (!selectedDeviceId) return
    try {
      await client.post(`/agent/devices/${selectedDeviceId}/stop`)
    } catch (e: any) {
      const status = e?.response?.status
      if (status !== 404) {
        addLog(`Agent停止失败: ${e?.response?.data?.detail || e.message}`, 'error')
      }
    }
    agentSetRunning(false)
    addLog('AI Agent 已停止', 'warn')
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
      <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center' }}>
        <TextField
          size="small"
          placeholder="AI任务: 如 自动回复微信消息"
          value={agentTask}
          onChange={(e) => setAgentTask(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !agentRunning) handleAgentStart() }}
          sx={{ flex: 1, '& input': { py: 0.5, fontSize: 13 } }}
          disabled={agentRunning}
        />
        <Button size="small" variant="contained"
          onClick={agentRunning ? handleAgentStop : handleAgentStart}
          sx={{ minWidth: 48, bgcolor: agentRunning ? colors.danger : '#9c27b0' }}
        >
          {agentRunning ? '停止' : 'AI'}
        </Button>
        {agentSteps.length > 0 && (
          <Button size="small" variant="text"
            onClick={() => setAgentPanelOpen(!agentPanelOpen)}
            sx={{ minWidth: 32, fontSize: 11, color: '#aaa' }}
          >
            {agentPanelOpen ? '收起' : `${agentSteps.length}步`}
          </Button>
        )}
      </Box>

      <Collapse in={agentPanelOpen} unmountOnExit>
        <Box sx={{
          mt: 0.5,
          maxHeight: 200,
          overflowY: 'auto',
          bgcolor: 'rgba(0,0,0,0.06)',
          borderRadius: 1,
          p: 0.5,
          fontSize: 11,
        }}>
          {statusMessage && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.5, color: agentRunning ? '#ff9800' : colors.success }}>
              {agentRunning ? <CircularProgress size={10} /> : (currentPhase === 'done' ? <CheckCircleIcon sx={{ fontSize: 12 }} /> : <ErrorIcon sx={{ fontSize: 12 }} />)}
              <Typography sx={{ fontSize: 11 }}>{statusMessage}</Typography>
            </Box>
          )}
          {agentSteps.map((s) => (
            <Box key={s.step} sx={{
              display: 'flex',
              flexDirection: 'column',
              gap: 0.25,
              mb: 0.5,
              p: 0.5,
              borderRadius: 0.5,
              bgcolor: s.step === currentStep ? 'rgba(156,39,176,0.08)' : 'transparent',
              borderLeft: `2px solid ${s.phase === 'done' ? colors.success : s.phase === 'acting' ? '#4caf50' : s.phase === 'thinking' ? '#ff9800' : '#2196f3'}`,
            }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                {PHASE_ICON[s.phase]}
                <Typography sx={{ fontSize: 11, fontWeight: 600 }}>
                  Step {s.step} — {PHASE_LABEL[s.phase]}
                </Typography>
                {s.action && <Typography sx={{ fontSize: 10, color: '#888', ml: 'auto' }}>{s.action}</Typography>}
              </Box>
              {s.observation && (
                <Typography sx={{ fontSize: 10, color: '#666', lineHeight: 1.3, wordBreak: 'break-all' }}>
                  👁 {s.observation.length > 120 ? s.observation.slice(0, 120) + '...' : s.observation}
                </Typography>
              )}
              {s.thought && (
                <Typography sx={{ fontSize: 10, color: '#888', lineHeight: 1.3, wordBreak: 'break-all' }}>
                  🧠 {s.thought.length > 120 ? s.thought.slice(0, 120) + '...' : s.thought}
                </Typography>
              )}
              {s.result && (
                <Typography sx={{ fontSize: 10, color: '#4caf50', lineHeight: 1.3 }}>
                  ✓ {s.result.length > 100 ? s.result.slice(0, 100) + '...' : s.result}
                </Typography>
              )}
            </Box>
          ))}
        </Box>
      </Collapse>
    </Box>
  )
}
