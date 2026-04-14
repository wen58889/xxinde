import { Box, IconButton, Typography, Collapse, TextField, Tooltip } from '@mui/material'
import ExpandLessIcon from '@mui/icons-material/ExpandLess'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import DeleteIcon from '@mui/icons-material/Delete'
import EditIcon from '@mui/icons-material/Edit'
import ImageIcon from '@mui/icons-material/Image'
import TextFieldsIcon from '@mui/icons-material/TextFields'
import DragIndicatorIcon from '@mui/icons-material/DragIndicator'
import { useState, useRef } from 'react'
import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { Rule } from '../../types/rule'
import { useRuleStore } from '../../stores/ruleStore'
import RuleParams from './RuleParams'
import DetectArea from './DetectArea'
import SubActionQueue from './SubActionQueue'
import InsertImageDialog from './InsertImageDialog'
import InsertTextDialog from './InsertTextDialog'
import { colors } from '../../theme'

interface Props {
  rule: Rule
  index: number
}

export default function RuleCard({ rule, index }: Props) {
  const toggleExpand = useRuleStore((s) => s.toggleExpand)
  const removeRule = useRuleStore((s) => s.removeRule)
  const duplicateRule = useRuleStore((s) => s.duplicateRule)
  const updateRule = useRuleStore((s) => s.updateRule)
  const selectRule = useRuleStore((s) => s.selectRule)
  const selectedRuleId = useRuleStore((s) => s.selectedRuleId)
  const addSubAction = useRuleStore((s) => s.addSubAction)
  const updateSubAction = useRuleStore((s) => s.updateSubAction)

  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: rule.id })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    zIndex: isDragging ? 10 : undefined,
  }

  const [editing, setEditing] = useState(false)
  const [nameVal, setNameVal] = useState(rule.name)
  const inputRef = useRef<HTMLInputElement>(null)
  const [imageDialogOpen, setImageDialogOpen] = useState(false)
  const [textDialogOpen, setTextDialogOpen] = useState(false)

  const isSelected = selectedRuleId === rule.id

  const startEdit = (e: React.MouseEvent) => {
    e.stopPropagation()
    setNameVal(rule.name)
    setEditing(true)
    setTimeout(() => inputRef.current?.select(), 10)
  }

  const commitEdit = () => {
    const trimmed = nameVal.trim()
    if (trimmed) updateRule(rule.id, { name: trimmed })
    setEditing(false)
  }

  const handleInsertImage = (templateName: string, threshold: number) => {
    addSubAction(rule.id)
    setTimeout(() => {
      const updatedRule = useRuleStore.getState().rules.find((r) => r.id === rule.id)
      if (updatedRule) {
        const lastSub = updatedRule.subActions[updatedRule.subActions.length - 1]
        if (lastSub) updateSubAction(rule.id, lastSub.id, { actionType: '识图', templateName, threshold })
      }
    }, 0)
  }

  const handleInsertText = (keyword: string) => {
    addSubAction(rule.id)
    setTimeout(() => {
      const updatedRule = useRuleStore.getState().rules.find((r) => r.id === rule.id)
      if (updatedRule) {
        const lastSub = updatedRule.subActions[updatedRule.subActions.length - 1]
        if (lastSub) updateSubAction(rule.id, lastSub.id, { actionType: '识字', keyword })
      }
    }, 0)
  }

  return (
    <Box
      ref={setNodeRef}
      style={style}
      sx={{
        bgcolor: colors.card,
        borderRadius: 1,
        border: isSelected ? `1px solid ${colors.highlight}` : '1px solid #333',
        mb: 0.5,
      }}
      onClick={() => selectRule(rule.id)}
    >
      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', px: 1, py: 0.3 }}>
        {/* Drag handle */}
        <IconButton
          size="small"
          {...attributes}
          {...listeners}
          sx={{ cursor: 'grab', color: '#666', '&:hover': { color: '#aaa' }, mr: -0.5 }}
        >
          <DragIndicatorIcon sx={{ fontSize: 16 }} />
        </IconButton>
        <IconButton size="small" onClick={(e) => { e.stopPropagation(); toggleExpand(rule.id) }}>
          {rule.expanded ? <ExpandLessIcon sx={{ fontSize: 16 }} /> : <ExpandMoreIcon sx={{ fontSize: 16 }} />}
        </IconButton>
        <Typography variant="caption" sx={{ fontWeight: 600, minWidth: 20 }}>{index + 1}.</Typography>

        {editing ? (
          <TextField
            inputRef={inputRef}
            size="small"
            value={nameVal}
            onChange={(e) => setNameVal(e.target.value)}
            onBlur={commitEdit}
            onKeyDown={(e) => { if (e.key === 'Enter') commitEdit(); if (e.key === 'Escape') setEditing(false) }}
            onClick={(e) => e.stopPropagation()}
            sx={{ flex: 1, '& input': { py: 0.3, fontSize: 13 } }}
            autoFocus
          />
        ) : (
          <Typography
            variant="body2"
            sx={{ flex: 1, fontSize: 13, cursor: 'text' }}
            onDoubleClick={startEdit}
            title="双击修改名称"
          >
            {rule.name}
          </Typography>
        )}

        <IconButton size="small" onClick={startEdit} sx={{ opacity: 0.4, '&:hover': { opacity: 1 } }}>
          <EditIcon sx={{ fontSize: 12 }} />
        </IconButton>
        <Tooltip title="插入图片" arrow>
          <IconButton size="small" onClick={(e) => { e.stopPropagation(); setImageDialogOpen(true) }} sx={{ opacity: 0.6, '&:hover': { opacity: 1, color: '#4fc3f7' } }}>
            <ImageIcon sx={{ fontSize: 14 }} />
          </IconButton>
        </Tooltip>
        <Tooltip title="插入文字" arrow>
          <IconButton size="small" onClick={(e) => { e.stopPropagation(); setTextDialogOpen(true) }} sx={{ opacity: 0.6, '&:hover': { opacity: 1, color: '#81c784' } }}>
            <TextFieldsIcon sx={{ fontSize: 14 }} />
          </IconButton>
        </Tooltip>
        <IconButton size="small" onClick={(e) => { e.stopPropagation(); duplicateRule(rule.id) }}>
          <ContentCopyIcon sx={{ fontSize: 14 }} />
        </IconButton>
        <IconButton size="small" onClick={(e) => { e.stopPropagation(); removeRule(rule.id) }}>
          <DeleteIcon sx={{ fontSize: 14, color: colors.danger }} />
        </IconButton>
      </Box>

      {/* Body */}
      <Collapse in={rule.expanded}>
        <Box sx={{ px: 1, pb: 1 }}>
          <RuleParams rule={rule} />
          <DetectArea rule={rule} />
          <SubActionQueue rule={rule} />
        </Box>
      </Collapse>

      {/* Dialogs */}
      <InsertImageDialog
        open={imageDialogOpen}
        onClose={() => setImageDialogOpen(false)}
        onConfirm={handleInsertImage}
      />
      <InsertTextDialog
        open={textDialogOpen}
        onClose={() => setTextDialogOpen(false)}
        onConfirm={handleInsertText}
      />
    </Box>
  )
}
