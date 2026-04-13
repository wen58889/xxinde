import { Box, Button } from '@mui/material'
import AddIcon from '@mui/icons-material/Add'
import { Rule } from '../../types/rule'
import { useRuleStore } from '../../stores/ruleStore'
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
} from '@dnd-kit/core'
import {
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import SubActionRow from './SubActionRow'

interface Props {
  rule: Rule
}

export default function SubActionQueue({ rule }: Props) {
  const addSubAction = useRuleStore((s) => s.addSubAction)
  const reorderSubActions = useRuleStore((s) => s.reorderSubActions)

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  )

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    if (!over || active.id === over.id) return
    const from = rule.subActions.findIndex((s) => s.id === active.id)
    const to = rule.subActions.findIndex((s) => s.id === over.id)
    if (from >= 0 && to >= 0) reorderSubActions(rule.id, from, to)
  }

  return (
    <Box sx={{ pl: 2, py: 0.5 }}>
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={rule.subActions.map((s) => s.id)} strategy={verticalListSortingStrategy}>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.3 }}>
            {rule.subActions.map((sub, idx) => (
              <SubActionRow key={sub.id} ruleId={rule.id} sub={sub} index={idx} />
            ))}
          </Box>
        </SortableContext>
      </DndContext>
      <Button
        size="small"
        startIcon={<AddIcon />}
        onClick={(e) => { e.stopPropagation(); addSubAction(rule.id) }}
        sx={{ mt: 0.5, fontSize: 11, textTransform: 'none' }}
      >
        添加动作
      </Button>
    </Box>
  )
}
