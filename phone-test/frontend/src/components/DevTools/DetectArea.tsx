import { Box, TextField, Button, Typography } from '@mui/material'
import { Rule } from '../../types/rule'
import { useRuleStore } from '../../stores/ruleStore'

interface Props {
  rule: Rule
}

export default function DetectArea({ rule }: Props) {
  const updateRule = useRuleStore((s) => s.updateRule)
  const da = rule.detectArea

  const setPoint = (idx: number, val: number) => {
    const next = [...da] as Rule['detectArea']
    next[idx] = val
    updateRule(rule.id, { detectArea: next })
  }

  const clear = () => updateRule(rule.id, { detectArea: [0, 0, 0, 0, 0, 0, 0, 0] })

  const labels = ['x1', 'y1', 'x2', 'y2', 'x3', 'y3', 'x4', 'y4']

  return (
    <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center', flexWrap: 'wrap', py: 0.5 }}>
      <Typography variant="caption" sx={{ color: '#888', mr: 0.5 }}>检测区域</Typography>
      {labels.map((l, i) => (
        <TextField
          key={l}
          size="small"
          label={l}
          type="number"
          value={da[i]}
          onChange={(e) => setPoint(i, Number(e.target.value))}
          sx={{ width: 60, '& input': { py: 0.5, fontSize: 11 }, '& label': { fontSize: 10 } }}
          inputProps={{ sx: { minWidth: 24 } }}
        />
      ))}
      <Button size="small" onClick={clear} sx={{ minWidth: 'auto', px: 1, fontSize: 11 }}>
        清零
      </Button>
    </Box>
  )
}
