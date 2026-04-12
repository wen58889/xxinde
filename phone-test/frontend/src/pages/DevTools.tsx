import { Box, LinearProgress, Typography } from '@mui/material'
import { useEffect, useState, useCallback } from 'react'
import DeviceToolbar from '../components/DevTools/DeviceToolbar'
import PhonePreview from '../components/DevTools/PhonePreview'
import DeviceControls from '../components/DevTools/DeviceControls'
import LogPanel from '../components/DevTools/LogPanel'
import ScriptToolbar from '../components/DevTools/ScriptToolbar'
import RuleCard from '../components/DevTools/RuleCard'
import TemplateMatchDialog from '../components/DevTools/TemplateMatchDialog'
import { useRuleStore } from '../stores/ruleStore'
import { useDeviceStore } from '../stores/deviceStore'
import { useLogStore } from '../stores/logStore'
import { wsClient } from '../api/ws'
import { colors } from '../theme'

export default function DevTools() {
  const rules = useRuleStore((s) => s.rules)
  const selectedDeviceId = useDeviceStore((s) => s.selectedDeviceId)
  const setVisionTargets = useDeviceStore((s) => s.setVisionTargets)
  const addLog = useLogStore((s) => s.addLog)
  const [taskProgress, setTaskProgress] = useState<{ step: number; total: number; action: string } | null>(null)

  const [matchDialogOpen, setMatchDialogOpen] = useState(false)

  const handleMatchResults = useCallback((results: Array<{ label: string; x: number; y: number; w: number; h: number; confidence: number }>) => {
    const targets = results.map(r => ({
      label: r.label,
      x: r.x,
      y: r.y,
      w: r.w,
      h: r.h,
      kind: 'template' as const,
      confidence: r.confidence,
    }))
    setVisionTargets(targets)
  }, [setVisionTargets])

  useEffect(() => {
    const unsub = wsClient.subscribe((event, data) => {
      const devId = data.device_id as number
      if (selectedDeviceId && devId !== selectedDeviceId) return

      if (event === 'task_progress') {
        setTaskProgress({
          step: data.step as number,
          total: data.total as number,
          action: data.action as string,
        })
        addLog(`步骤 ${data.step}/${data.total}: ${data.action}`, 'info')
      } else if (event === 'task_complete') {
        setTaskProgress(null)
        const status = data.status as string
        if (status === 'SUCCESS') addLog('任务执行完成 ✓', 'success')
        else if (status === 'STOPPED') addLog('任务已停止', 'warn')
        else addLog(`任务失败: ${status}`, 'error')
      }
    })
    return unsub
  }, [selectedDeviceId])

  return (
    <Box sx={{ display: 'flex', height: '100vh', bgcolor: colors.bg }}>
      {/* Left: Device preview & control */}
      <Box sx={{ width: 460, display: 'flex', flexDirection: 'column', p: 1, borderRight: '1px solid #333' }}>
        <DeviceToolbar />
        <PhonePreview />
        <DeviceControls
          onOpenMatchDialog={() => setMatchDialogOpen(true)}
        />
        {taskProgress && (
          <Box sx={{ px: 0.5, py: 0.5, flexShrink: 0 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.3 }}>
              <Typography sx={{ fontSize: 11, color: '#aaa' }}>{taskProgress.action}</Typography>
              <Typography sx={{ fontSize: 11, color: '#aaa' }}>{taskProgress.step}/{taskProgress.total}</Typography>
            </Box>
            <LinearProgress
              variant="determinate"
              value={taskProgress.total > 0 ? (taskProgress.step / taskProgress.total) * 100 : 0}
              sx={{ height: 3, borderRadius: 1 }}
            />
          </Box>
        )}
        <LogPanel />
      </Box>

      {/* Right: Script editor */}
      <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', p: 1, overflow: 'hidden' }}>
        <ScriptToolbar />
        <Box sx={{ flex: 1, overflow: 'auto', mt: 1 }}>
          {rules.map((rule, idx) => (
            <RuleCard key={rule.id} rule={rule} index={idx} />
          ))}
        </Box>
      </Box>

      {/* Template match dialog */}
      <TemplateMatchDialog
        open={matchDialogOpen}
        onClose={() => setMatchDialogOpen(false)}
        onMatchResults={handleMatchResults}
      />
    </Box>
  )
}
