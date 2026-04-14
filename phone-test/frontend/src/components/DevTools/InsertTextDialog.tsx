import { useState } from 'react'
import {
  Dialog, DialogTitle, DialogContent, Box, Typography, Button,
  IconButton, TextField,
} from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import { colors } from '../../theme'

interface Props {
  open: boolean
  onClose: () => void
  onConfirm: (keyword: string) => void
}

export default function InsertTextDialog({ open, onClose, onConfirm }: Props) {
  const [keyword, setKeyword] = useState('')

  const handleConfirm = () => {
    if (!keyword.trim()) return
    onConfirm(keyword.trim())
    setKeyword('')
    onClose()
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth={false}
      PaperProps={{
        sx: {
          bgcolor: '#1e2a3a',
          color: colors.text,
          width: 340,
          borderRadius: 2,
          border: '1px solid #334',
        },
      }}
    >
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', pb: 1 }}>
        <Typography fontWeight="bold" fontSize={15} color="#81c784">
          插入文字 (识字)
        </Typography>
        <IconButton size="small" onClick={onClose} sx={{ color: '#aaa' }}>
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>
      <DialogContent sx={{ pt: 0 }}>
        <Typography fontSize={13} sx={{ mb: 1.5, color: '#aaa' }}>
          输入要查找的文字，脚本运行时通过OCR识别并点击
        </Typography>
        <TextField
          fullWidth
          size="small"
          label="查找文字"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') handleConfirm() }}
          autoFocus
          sx={{
            mb: 2,
            '& input': { py: 0.8, fontSize: 14 },
            '& label': { fontSize: 12 },
          }}
        />
        <Button
          fullWidth
          variant="contained"
          onClick={handleConfirm}
          disabled={!keyword.trim()}
          sx={{
            bgcolor: '#81c784',
            fontWeight: 'bold',
            py: 1,
            fontSize: 14,
            '&:hover': { bgcolor: '#66bb6a' },
          }}
        >
          确认插入
        </Button>
      </DialogContent>
    </Dialog>
  )
}
