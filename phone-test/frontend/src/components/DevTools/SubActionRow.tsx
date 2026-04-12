import { Box, Select, MenuItem, TextField, IconButton, Typography } from '@mui/material'
import DragIndicatorIcon from '@mui/icons-material/DragIndicator'
import CloseIcon from '@mui/icons-material/Close'
import { SubAction, ActionType } from '../../types/rule'
import { useRuleStore } from '../../stores/ruleStore'
import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'

const actionTypes: ActionType[] = ['点击', '滑屏', 'TTS']

const badges = ['❶', '❷', '❸', '❹', '❺', '❻', '❼', '❽', '❾', '❿']

interface Props {
  ruleId: string
  sub: SubAction
  index: number
}

export default function SubActionRow({ ruleId, sub, index }: Props) {
  const updateSubAction = useRuleStore((s) => s.updateSubAction)
  const removeSubAction = useRuleStore((s) => s.removeSubAction)

  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: sub.id,
  })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  }

  const u = (p: Partial<SubAction>) => updateSubAction(ruleId, sub.id, p)

  const numField = (label: string, value: number, key: keyof SubAction, width = 52) => (
    <TextField
      size="small"
      label={label}
      type="number"
      value={value}
      onChange={(e) => u({ [key]: Number(e.target.value) } as Partial<SubAction>)}
      sx={{ width, '& input': { py: 0.5, fontSize: 11 }, '& label': { fontSize: 10 } }}
    />
  )

  return (
    <Box
      ref={setNodeRef}
      style={style}
      sx={{
        display: 'flex',
        gap: 0.5,
        alignItems: 'center',
        flexWrap: 'wrap',
        py: 0.3,
        px: 0.5,
        bgcolor: '#1a1a2e',
        borderRadius: 0.5,
      }}
    >
      <IconButton size="small" {...attributes} {...listeners} sx={{ cursor: 'grab', p: 0 }}>
        <DragIndicatorIcon sx={{ fontSize: 16, color: '#555' }} />
      </IconButton>

      <Typography variant="caption" sx={{ fontWeight: 600, color: '#ffab40', minWidth: 14 }}>
        {badges[index] || `(${index + 1})`}
      </Typography>

      <Select
        size="small"
        value={sub.actionType}
        onChange={(e) => u({ actionType: e.target.value as ActionType })}
        sx={{ height: 26, minWidth: 60, fontSize: 11 }}
      >
        {actionTypes.map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}
      </Select>

      {numField('X', sub.x, 'x')}
      {numField('Y', sub.y, 'y')}
      {numField('半径', sub.radius, 'radius')}
      {numField('次数', sub.count, 'count', 45)}
      {numField('长按', sub.longPress, 'longPress')}
      {numField('循环', sub.loopCount, 'loopCount', 48)}
      {numField('等min', sub.waitMin, 'waitMin', 52)}
      {numField('max', sub.waitMax, 'waitMax', 45)}

      <TextField
        size="small"
        label="备注"
        value={sub.note}
        onChange={(e) => u({ note: e.target.value })}
        sx={{ width: 80, '& input': { py: 0.5, fontSize: 11 }, '& label': { fontSize: 10 } }}
      />

      <IconButton size="small" onClick={() => removeSubAction(ruleId, sub.id)} sx={{ p: 0 }}>
        <CloseIcon sx={{ fontSize: 14, color: '#888' }} />
      </IconButton>
    </Box>
  )
}
