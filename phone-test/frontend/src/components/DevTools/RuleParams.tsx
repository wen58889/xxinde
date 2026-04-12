import { Box, Select, MenuItem, TextField, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material'
import { Rule, ActionType, PositionMode } from '../../types/rule'
import { useRuleStore } from '../../stores/ruleStore'

const actionTypes: ActionType[] = ['点击', '滑屏', 'TTS']
const positionModes: PositionMode[] = ['中心', '坐标']

interface Props {
  rule: Rule
}

export default function RuleParams({ rule }: Props) {
  const updateRule = useRuleStore((s) => s.updateRule)
  const u = (p: Partial<Rule>) => updateRule(rule.id, p)

  const numField = (label: string, value: number, key: keyof Rule, width = 55) => (
    <TextField
      size="small"
      label={label}
      type="number"
      value={value}
      onChange={(e) => u({ [key]: Number(e.target.value) } as Partial<Rule>)}
      sx={{ width, '& input': { py: 0.5, fontSize: 12 }, '& label': { fontSize: 11 } }}
    />
  )

  return (
    <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center', flexWrap: 'wrap', py: 0.5 }}>
      <Select
        size="small"
        value={rule.actionType}
        onChange={(e) => u({ actionType: e.target.value as ActionType })}
        sx={{ height: 30, minWidth: 65, fontSize: 12 }}
      >
        {actionTypes.map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}
      </Select>

      <ToggleButtonGroup
        size="small"
        exclusive
        value={rule.positionMode}
        onChange={(_, v) => v && u({ positionMode: v as PositionMode })}
        sx={{ height: 28 }}
      >
        {positionModes.map((m) => (
          <ToggleButton key={m} value={m} sx={{ px: 1, fontSize: 11, textTransform: 'none' }}>
            {m}
          </ToggleButton>
        ))}
      </ToggleButtonGroup>

      {numField('X', rule.x, 'x')}
      {numField('Y', rule.y, 'y')}
      {numField('半径', rule.radius, 'radius')}
      {numField('次数', rule.count, 'count', 48)}
      {numField('长按', rule.longPress, 'longPress')}

      {rule.actionType === '滑屏' && (
        <>
          {numField('滑时', rule.slideDuration, 'slideDuration')}
          <Typography variant="caption" sx={{ color: '#888' }}>→</Typography>
          {numField('滑X', rule.slideX, 'slideX')}
          {numField('滑Y', rule.slideY, 'slideY')}
        </>
      )}

      {numField('等待min', rule.waitMin, 'waitMin', 62)}
      <Typography variant="caption" sx={{ color: '#888' }}>-</Typography>
      {numField('max', rule.waitMax, 'waitMax', 50)}
    </Box>
  )
}
