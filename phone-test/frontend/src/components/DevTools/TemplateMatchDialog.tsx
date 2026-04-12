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
import { templateIconsApi, visionTestApi } from '../../api/devices'
import type { TemplateIconInfo } from '../../api/devices'
import { useDeviceStore } from '../../stores/deviceStore'
import { useLogStore } from '../../stores/logStore'
import { colors } from '../../theme'

interface MatchResult {
  label: string
  x: number
  y: number
  w: number
  h: number
  confidence: number
}

interface Props {
  open: boolean
  onClose: () => void
  onMatchResults: (results: MatchResult[]) => void
}

export default function TemplateMatchDialog({ open, onClose, onMatchResults }: Props) {
  const selectedDeviceId = useDeviceStore((s) => s.selectedDeviceId)
  const addLog = useLogStore((s) => s.addLog)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [threshold, setThreshold] = useState(0.85)
  const [apps, setApps] = useState<Record<string, TemplateIconInfo[]>>({})
  const [selectedApp, setSelectedApp] = useState('')
  const [selectedFile, setSelectedFile] = useState('')
  const [loading, setLoading] = useState(false)
  const [matchLoading, setMatchLoading] = useState(false)
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
  const allIcons = Object.values(apps).flat()

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    return `${(bytes / 1024).toFixed(1)} KB`
  }

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !selectedApp) return
    const name = file.name.replace(/\.[^.]+$/, '') + '.jpg'
    try {
      await templateIconsApi.upload(selectedApp, name, file)
      addLog(`模板上传成功: ${selectedApp}/${name}`, 'success')
      await loadIcons()
    } catch {
      addLog('模板上传失败', 'error')
    }
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handleDelete = async (app: string, name: string) => {
    try {
      await templateIconsApi.delete(app, name)
      addLog(`已删除模板: ${app}/${name}`, 'info')
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

  const handleMatchTest = async () => {
    const frameBlob = useDeviceStore.getState().currentFrameBlob
    if (!selectedDeviceId && !frameBlob) {
      addLog('请先选择设备并获取画面', 'warn')
      return
    }
    setMatchLoading(true)
    addLog('开始模板匹配测试...', 'info')
    try {
      const req: Record<string, unknown> = { threshold }

      // 优先用已显示的图片（不再重新截图，更快更可靠）
      if (frameBlob) {
        const buf = await frameBlob.arrayBuffer()
        const bytes = new Uint8Array(buf)
        let binary = ''
        for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i])
        req.image_base64 = btoa(binary)
      } else {
        req.device_id = selectedDeviceId
      }

      // If a specific file is selected, match only that template
      if (selectedFile) {
        req.template_name = selectedFile.replace(/\.[^.]+$/, '')
        req.app_name = selectedApp || '_common'
      }

      const data = await visionTestApi.matchTest(req as any) as any
      const matches: MatchResult[] = (data.result || []).map((r: any) => ({
        label: r.label || r.template_name || '',
        x: r.x,
        y: r.y,
        w: r.w,
        h: r.h,
        confidence: r.confidence,
      }))

      if (matches.length > 0) {
        addLog(`匹配成功: 找到 ${matches.length} 个目标 (${data.latency_ms}ms)`, 'success')
        matches.forEach((m, i) =>
          addLog(`  #${i + 1} ${m.label} (${Math.round(m.x)},${Math.round(m.y)}) ${(m.confidence * 100).toFixed(1)}%`, 'info')
        )
        onMatchResults(matches)
      } else {
        addLog(`未匹配到目标 (阈值=${threshold}, ${data.latency_ms}ms)`, 'warn')
        onMatchResults([])
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      addLog(`匹配测试失败: ${msg}`, 'error')
      onMatchResults([])
    } finally {
      setMatchLoading(false)
    }
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
          width: 420,
          maxHeight: '80vh',
          borderRadius: 2,
          border: '1px solid #334',
        },
      }}
    >
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', pb: 1 }}>
        <Typography fontWeight="bold" fontSize={16} color={colors.highlight}>
          图色测试 (模板匹配)
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
            sx={{ color: colors.highlight, flex: 1 }}
          />
          <Typography fontSize={13} fontWeight="bold" sx={{ minWidth: 36 }}>
            {threshold.toFixed(2)}
          </Typography>
        </Box>

        {/* Template file browser section */}
        <Box sx={{
          border: '1px solid #334',
          borderRadius: 1,
          p: 1.5,
          mb: 2,
        }}>
          <Typography fontSize={13} fontWeight="bold" sx={{ mb: 1 }}>
            本地素材 (右键点击素材进行操作)
          </Typography>

          {/* App folder tabs + actions */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 1, flexWrap: 'wrap' }}>
            <Typography fontSize={12} color="text.secondary">点击文件夹展开</Typography>
            <Box sx={{ flex: 1 }} />
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
                + 新建文件夹
              </Button>
            )}
          </Box>

          {/* Folder buttons */}
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

          {/* Upload button */}
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
            <Box sx={{ maxHeight: 240, overflow: 'auto' }}>
              <Table size="small" sx={{ '& td, & th': { borderColor: '#334', py: 0.5, px: 1 } }}>
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ fontSize: 12, fontWeight: 'bold', color: colors.highlight, width: 50 }}>类型</TableCell>
                    <TableCell sx={{ fontSize: 12, fontWeight: 'bold', color: colors.highlight }}>名称</TableCell>
                    <TableCell sx={{ fontSize: 12, fontWeight: 'bold', color: colors.highlight, width: 60 }}>大小</TableCell>
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
                        '&.Mui-selected': { bgcolor: 'rgba(255,100,0,0.15)' },
                        '&.Mui-selected:hover': { bgcolor: 'rgba(255,100,0,0.2)' },
                        '&:hover': { bgcolor: 'rgba(255,255,255,0.04)' },
                      }}
                    >
                      <TableCell>
                        <Box sx={{
                          width: 32, height: 32, borderRadius: 0.5,
                          overflow: 'hidden', border: '1px solid #444',
                        }}>
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
                          color={selectedFile === icon.name ? '#ff9100' : 'inherit'}
                        >
                          {icon.name}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Typography fontSize={11} color="text.secondary">
                          {formatSize(icon.size)}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Tooltip title="删除">
                          <IconButton
                            size="small"
                            onClick={(e) => { e.stopPropagation(); handleDelete(selectedApp, icon.name) }}
                            sx={{ p: 0.3 }}
                          >
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
              {selectedApp ? '暂无模板图，请上传或从截图裁剪' : '请选择文件夹'}
            </Typography>
          )}
        </Box>

        {/* Match test button */}
        <Button
          fullWidth
          variant="contained"
          onClick={handleMatchTest}
          disabled={matchLoading || !selectedDeviceId}
          sx={{
            bgcolor: colors.highlight,
            fontWeight: 'bold',
            py: 1,
            fontSize: 14,
            '&:hover': { bgcolor: '#007acc' },
          }}
        >
          {matchLoading ? <CircularProgress size={18} color="inherit" /> : '开始匹配测试'}
        </Button>
      </DialogContent>
    </Dialog>
  )
}
