import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Dialog, DialogTitle, DialogContent, Box, Typography, Button, Slider,
  IconButton, CircularProgress, Table, TableBody, TableCell, TableHead,
  TableRow, TextField, Tooltip,
} from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import CreateNewFolderIcon from '@mui/icons-material/CreateNewFolder'
import UploadFileIcon from '@mui/icons-material/UploadFile'
import DeleteIcon from '@mui/icons-material/Delete'
import { templateIconsApi } from '../../api/devices'
import type { TemplateIconInfo } from '../../api/devices'
import { colors } from '../../theme'

interface Props {
  open: boolean
  onClose: () => void
  onConfirm: (templateName: string, threshold: number) => void
}

export default function InsertImageDialog({ open, onClose, onConfirm }: Props) {
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [threshold, setThreshold] = useState(0.85)
  const [apps, setApps] = useState<Record<string, TemplateIconInfo[]>>({})
  const [selectedApp, setSelectedApp] = useState('')
  const [selectedFile, setSelectedFile] = useState('')
  const [loading, setLoading] = useState(false)
  const [newFolderMode, setNewFolderMode] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')

  const loadIcons = useCallback(async () => {
    setLoading(true)
    try {
      const data = await templateIconsApi.list()
      const appData = data.apps || {}
      setApps(appData)
      const names = Object.keys(appData)
      if (names.length > 0 && !selectedApp) {
        setSelectedApp(names[0])
      }
    } catch { /* ignore */ }
    finally { setLoading(false) }
  }, [selectedApp])

  useEffect(() => {
    if (open) loadIcons()
  }, [open, loadIcons])

  const currentIcons = apps[selectedApp] || []

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !selectedApp) return
    const name = file.name.replace(/\.[^.]+$/, '') + '.jpg'
    try {
      await templateIconsApi.upload(selectedApp, name, file)
      await loadIcons()
    } catch { /* ignore */ }
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handleDelete = async (app: string, name: string) => {
    try {
      await templateIconsApi.delete(app, name)
      await loadIcons()
    } catch { /* ignore */ }
  }

  const handleCreateFolder = async () => {
    if (!newFolderName.trim()) return
    try {
      await templateIconsApi.createFolder(newFolderName.trim())
      setNewFolderMode(false)
      setSelectedApp(newFolderName.trim())
      setNewFolderName('')
      await loadIcons()
    } catch { /* ignore */ }
  }

  const handleConfirm = () => {
    if (!selectedFile) return
    // templateName = app/iconName (without extension)
    const nameOnly = selectedFile.replace(/\.[^.]+$/, '')
    onConfirm(nameOnly, threshold)
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
          width: 400,
          maxHeight: '80vh',
          borderRadius: 2,
          border: '1px solid #334',
        },
      }}
    >
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', pb: 1 }}>
        <Typography fontWeight="bold" fontSize={15} color="#4fc3f7">
          插入图片 (识图)
        </Typography>
        <IconButton size="small" onClick={onClose} sx={{ color: '#aaa' }}>
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>
      <DialogContent sx={{ pt: 0 }}>
        {/* Threshold slider */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
          <Typography fontSize={13} sx={{ whiteSpace: 'nowrap' }}>匹配阈值:</Typography>
          <Slider
            value={threshold}
            onChange={(_, v) => setThreshold(v as number)}
            min={0.5}
            max={1.0}
            step={0.01}
            sx={{ color: '#4fc3f7', flex: 1 }}
          />
          <Typography fontSize={13} fontWeight="bold" sx={{ minWidth: 36 }}>
            {threshold.toFixed(2)}
          </Typography>
        </Box>

        {/* Template file browser */}
        <Box sx={{ border: '1px solid #334', borderRadius: 1, p: 1.5, mb: 2 }}>
          <Typography fontSize={13} fontWeight="bold" sx={{ mb: 1 }}>
            选择模板图片
          </Typography>

          {/* Folder tabs */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 1, flexWrap: 'wrap' }}>
            {newFolderMode ? (
              <Box sx={{ display: 'flex', gap: 0.5 }}>
                <TextField
                  size="small"
                  value={newFolderName}
                  onChange={(e) => setNewFolderName(e.target.value)}
                  placeholder="文件夹名"
                  onKeyDown={(e) => { if (e.key === 'Enter') handleCreateFolder() }}
                  sx={{ width: 100, '& input': { py: 0.3, fontSize: 12 } }}
                />
                <Button size="small" variant="contained" onClick={handleCreateFolder}
                  sx={{ fontSize: 11, minWidth: 'auto', px: 1 }}>确定</Button>
                <Button size="small" onClick={() => setNewFolderMode(false)}
                  sx={{ fontSize: 11, minWidth: 'auto', px: 1 }}>取消</Button>
              </Box>
            ) : (
              <Button
                size="small" variant="outlined"
                startIcon={<CreateNewFolderIcon sx={{ fontSize: 14 }} />}
                onClick={() => setNewFolderMode(true)}
                sx={{ fontSize: 11, py: 0.2 }}
              >
                + 新建
              </Button>
            )}
          </Box>

          <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', mb: 1 }}>
            {Object.keys(apps).map((app) => (
              <Button
                key={app}
                size="small"
                variant={selectedApp === app ? 'contained' : 'outlined'}
                onClick={() => { setSelectedApp(app); setSelectedFile('') }}
                sx={{ fontSize: 11, minWidth: 'auto', px: 1, py: 0.2 }}
              >
                {app}
              </Button>
            ))}
          </Box>

          {/* Upload */}
          {selectedApp && (
            <Box sx={{ mb: 1 }}>
              <Button
                size="small" variant="outlined" component="label"
                startIcon={<UploadFileIcon sx={{ fontSize: 14 }} />}
                sx={{ fontSize: 11, py: 0.2 }}
              >
                上传模板图
                <input ref={fileInputRef} type="file" hidden accept="image/*" onChange={handleUpload} />
              </Button>
            </Box>
          )}

          {/* Files table */}
          {loading ? (
            <Box sx={{ py: 2, textAlign: 'center' }}><CircularProgress size={20} /></Box>
          ) : currentIcons.length > 0 ? (
            <Box sx={{ maxHeight: 200, overflow: 'auto' }}>
              <Table size="small" sx={{ '& td, & th': { borderColor: '#334', py: 0.5, px: 1 } }}>
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ fontSize: 12, fontWeight: 'bold', color: '#4fc3f7', width: 50 }}>图</TableCell>
                    <TableCell sx={{ fontSize: 12, fontWeight: 'bold', color: '#4fc3f7' }}>名称</TableCell>
                    <TableCell sx={{ width: 30 }} />
                  </TableRow>
                </TableHead>
                <TableBody>
                  {currentIcons.map((icon) => (
                    <TableRow
                      key={icon.name}
                      hover
                      selected={selectedFile === icon.name}
                      onClick={() => setSelectedFile(icon.name)}
                      sx={{
                        cursor: 'pointer',
                        '&.Mui-selected': { bgcolor: 'rgba(79,195,247,0.15)' },
                        '&.Mui-selected:hover': { bgcolor: 'rgba(79,195,247,0.2)' },
                        '&:hover': { bgcolor: 'rgba(255,255,255,0.04)' },
                      }}
                    >
                      <TableCell>
                        <Box sx={{ width: 32, height: 32, borderRadius: 0.5, overflow: 'hidden', border: '1px solid #444' }}>
                          <img
                            src={templateIconsApi.get(selectedApp, icon.name)}
                            alt={icon.name}
                            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                            onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
                          />
                        </Box>
                      </TableCell>
                      <TableCell>
                        <Typography
                          fontSize={12}
                          fontWeight={selectedFile === icon.name ? 'bold' : 'normal'}
                          color={selectedFile === icon.name ? '#4fc3f7' : 'inherit'}
                        >
                          {icon.name}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Tooltip title="删除">
                          <IconButton size="small" onClick={(e) => { e.stopPropagation(); handleDelete(selectedApp, icon.name) }} sx={{ p: 0.3 }}>
                            <DeleteIcon sx={{ fontSize: 14, color: '#666' }} />
                          </IconButton>
                        </Tooltip>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Box>
          ) : (
            <Typography fontSize={12} color="text.secondary" sx={{ py: 1, textAlign: 'center' }}>
              {selectedApp ? '暂无模板图，请上传' : '请选择文件夹'}
            </Typography>
          )}
        </Box>

        {/* Confirm button */}
        <Button
          fullWidth
          variant="contained"
          onClick={handleConfirm}
          disabled={!selectedFile}
          sx={{
            bgcolor: '#4fc3f7',
            fontWeight: 'bold',
            py: 1,
            fontSize: 14,
            '&:hover': { bgcolor: '#29b6f6' },
          }}
        >
          确认插入
        </Button>
      </DialogContent>
    </Dialog>
  )
}
