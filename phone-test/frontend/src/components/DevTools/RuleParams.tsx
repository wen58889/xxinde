import { Box, Select, MenuItem, TextField, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material'
import { Rule, ActionType, PositionMode } from '../../types/rule'
import { useRuleStore } from '../../stores/ruleStore'

const actionTypes: ActionType[] = ['点击', '滑屏', '识图', '识字', 'TTS']
const positionModes: PositionMode[] = ['中心', '相对', '坐标']

interface Props {
  rule: Rule
}

export default function RuleParams({ rule }: Props) {
  const updateRule = useRuleStore((s) => s.updateRule)
  const u = (p: Partial<Rule>) => updateRule(rule.id, p)

  const numField = (label: string, value: number, key: keyof Rule, width = 68) => (
    <TextField
      size="small"
      label={label}
      type="number"
      value={value}
      onChange={(e) => u({ [key]: Number(e.target.value) } as Partial<Rule>)}
      sx={{ width, '& input': { py: 0.5, fontSize: 12 }, '& label': { fontSize: 11 } }}
      inputProps={{ sx: { minWidth: 28 } }}
    />
  )

  return (
    <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center', flexWrap: 'wrap', py: 0.5 }}>
      {/* 动作类型 */}
      <Select
        size="small"
        value={rule.actionType}
        onChange={(e) => u({ actionType: e.target.value as ActionType })}
        sx={{ height: 30, minWidth: 65, fontSize: 12 }}
      >
        {actionTypes.map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}
      </Select>

      {/* 坐标模式 */}
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

      {/* 坐标 - 需要更宽以显示0~1280的值 */}
      {numField('X', rule.x, 'x', 72)}
      {numField('Y', rule.y, 'y', 72)}

      {/* 随机偏移 */}
      {numField('随机', rule.radius, 'radius', 62)}

      {/* 次数 */}
      {numField('次数', rule.count, 'count', 55)}

      {/* 长按/秒 */}
      {numField('长按/秒', rule.longPress, 'longPress', 65)}

      {/* 滑屏专用参数 */}
      {rule.actionType === '滑屏' && (
        <>
          <Typography variant="caption" sx={{ color: '#888' }}>→</Typography>
          {numField('滑X', rule.slideX, 'slideX', 72)}
          {numField('滑Y', rule.slideY, 'slideY', 72)}
          {numField('滑时', rule.slideDuration, 'slideDuration', 62)}
        </>
      )}

      {/* 识图专用 */}
      {rule.actionType === '识图' && (
        <>
          <TextField
            size="small"
            label="模板名称"
            value={rule.templateName || ''}
            onChange={(e) => u({ templateName: e.target.value })}
            sx={{ flex: 1, minWidth: 100, '& input': { py: 0.5, fontSize: 12 }, '& label': { fontSize: 11 } }}
          />
          {numField('阈值', rule.threshold, 'threshold', 62)}
        </>
      )}

      {/* 识字专用 */}
      {rule.actionType === '识字' && (
        <TextField
          size="small"
          label="查找文字"
          value={rule.keyword || ''}
          onChange={(e) => u({ keyword: e.target.value })}
          sx={{ flex: 1, minWidth: 100, '& input': { py: 0.5, fontSize: 12 }, '& label': { fontSize: 11 } }}
        />
      )}

      {/* TTS 专用 */}
      {rule.actionType === 'TTS' && (
        <TextField
          size="small"
          label="语音文本"
          value={rule.ttsText || ''}
          onChange={(e) => u({ ttsText: e.target.value })}
          sx={{ flex: 1, minWidth: 100, '& input': { py: 0.5, fontSize: 12 }, '& label': { fontSize: 11 } }}
        />
      )}

      {/* 定时/秒 */}
      {numField('定时/秒', rule.timer, 'timer', 65)}

      {/* 概率 */}
      {numField('概率', rule.probability, 'probability', 55)}

      {/* 等待/秒 min - max */}
      {numField('等待min', rule.waitMin, 'waitMin', 68)}
      <Typography variant="caption" sx={{ color: '#888' }}>-</Typography>
      {numField('max', rule.waitMax, 'waitMax', 55)}
    </Box>
  )
}
