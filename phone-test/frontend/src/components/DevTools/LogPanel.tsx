import { Box, Typography } from '@mui/material'
import { useLogStore, LogEntry } from '../../stores/logStore'
import { useEffect, useRef } from 'react'
import { colors } from '../../theme'

const levelColor: Record<LogEntry['level'], string> = {
  info: '#fff',
  success: colors.success,
  error: colors.danger,
  warn: colors.warning,
} as const

export default function LogPanel() {
  const logs = useLogStore((s) => s.logs)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs.length])

  const fmt = (t: string) => t

  return (
    <Box
      sx={{
        flexShrink: 0,
        height: 106,
        maxHeight: 106,
        bgcolor: '#111',
        borderRadius: 1,
        p: 1,
        overflow: 'auto',
        fontFamily: 'monospace',
        fontSize: 12,
        lineHeight: 1.5,
      }}
    >
      {logs.length === 0 && (
        <Typography variant="caption" sx={{ color: '#555' }}>暂无日志...</Typography>
      )}
      {logs.map((l) => (
        <Box key={l.id} sx={{ color: levelColor[l.level], lineHeight: 1.5 }}>
          <span style={{ color: '#666' }}>[{fmt(l.time)}]</span>{' '}{l.message}
        </Box>
      ))}
      <div ref={bottomRef} />
    </Box>
  )
}
