import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Box, Typography, Paper, Button, TextField, Slider,
  CircularProgress, Divider, Grid, Alert, IconButton,
  List, ListItem, ListItemText, ListItemSecondaryAction, Tooltip,
  Dialog, DialogTitle, DialogContent, DialogActions,
} from '@mui/material'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import ErrorIcon from '@mui/icons-material/Error'
import { useNavigate } from 'react-router-dom'
import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import RefreshIcon from '@mui/icons-material/Refresh'
import DeleteIcon from '@mui/icons-material/Delete'
import UploadFileIcon from '@mui/icons-material/UploadFile'
import CreateNewFolderIcon from '@mui/icons-material/CreateNewFolder'
import ImageSearchIcon from '@mui/icons-material/ImageSearch'
import TextFieldsIcon from '@mui/icons-material/TextFields'
import { visionTestApi, templateIconsApi } from '../api/devices'
import type { TemplateIconInfo } from '../api/devices'
import { ensureToken } from '../api/client'
import { useDeviceStore } from '../stores/deviceStore'
import { colors } from '../theme'

interface MatchResult {
  x: number
  y: number
  w: number
  h: number
  confidence: number
  template_name: string
}

export default function VisionTest() {
  const nav = useNavigate()
  const devices = useDeviceStore((s) => s.devices)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Health
  const [health, setHealth] = useState<Record<string, unknown>>({})
  const [healthLoading, setHealthLoading] = useState(false)

  // Template icons
  const [apps, setApps] = useState<Record<string, TemplateIconInfo[]>>({})
  const [selectedApp, setSelectedApp] = useState<string>('')
  const [iconsLoading, setIconsLoading] = useState(false)

  // Match test
  const [threshold, setThreshold] = useState(0.85)
  const [selectedTemplate, setSelectedTemplate] = useState('')
  const [deviceId, setDeviceId] = useState<number | ''>('')
  const [matchLoading, setMatchLoading] = useState(false)
  const [matchResults, setMatchResults] = useState<MatchResult[]>([])
  const [matchError, setMatchError] = useState('')
  const [matchLatency, setMatchLatency] = useState<number | null>(null)

  // OCR test
  const [ocrKeyword, setOcrKeyword] = useState('')
  const [ocrLoading, setOcrLoading] = useState(false)
  const [ocrResults, setOcrResults] = useState<Array<{ text: string; x: number; y: number; w: number; h: number; confidence: number }>>([])
  const [ocrError, setOcrError] = useState('')

  // Screenshot preview with match overlay
  const [previewSrc, setPreviewSrc] = useState('')

  // New folder dialog
  const [folderDialogOpen, setFolderDialogOpen] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')

  // Delete confirm
  const [deleteTarget, setDeleteTarget] = useState<{ app: string; name: string } | null>(null)

  const loadHealth = useCallback(async () => {
    await ensureToken()
    setHealthLoading(true)
    try {
      const data = await visionTestApi.health()
      setHealth(data)
    } catch {
      setHealth({ error: '请求失败' })
    } finally {
      setHealthLoading(false)
    }
  }, [])

  const loadIcons = useCallback(async () => {
    await ensureToken()
    setIconsLoading(true)
    try {
      const data = await templateIconsApi.list()
      setApps(data.apps || {})
      const appNames = Object.keys(data.apps || {})
      if (appNames.length > 0 && !selectedApp) {
        setSelectedApp(appNames[0])
      }
    } catch {
      /* ignore */
    } finally {
      setIconsLoading(false)
    }
  }, [selectedApp])

  useEffect(() => { loadHealth(); loadIcons() }, [loadHealth, loadIcons])

  const currentIcons = apps[selectedApp] || []
  const appNames = Object.keys(apps)

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !selectedApp) return
    const name = file.name.replace(/\.[^.]+$/, '') + '.jpg'
    try {
      await templateIconsApi.upload(selectedApp, name, file)
      await loadIcons()
    } catch {
      /* ignore */
    }
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      await templateIconsApi.delete(deleteTarget.app, deleteTarget.name)
      await loadIcons()
    } catch {
      /* ignore */
    }
    setDeleteTarget(null)
  }

  const handleCreateFolder = async () => {
    if (!newFolderName.trim()) return
    try {
      await templateIconsApi.createFolder(newFolderName.trim())
      setNewFolderName('')
      setFolderDialogOpen(false)
      await loadIcons()
      setSelectedApp(newFolderName.trim())
    } catch {
      /* ignore */
    }
  }

  const handleMatchTest = async () => {
    if (!selectedTemplate) return
    setMatchLoading(true)
    setMatchResults([])
    setMatchError('')
    setMatchLatency(null)
    const t0 = performance.now()
    try {
      const req: Record<string, unknown> = {
        template_name: selectedTemplate,
        app_name: selectedApp || '_common',
        threshold,
      }
      if (deviceId !== '') req.device_id = deviceId
      const data = await visionTestApi.matchTest(req as any) as any
      setMatchLatency(Math.round(performance.now() - t0))
      if (data.matches) {
        setMatchResults(data.matches)
      } else if (data.match) {
        setMatchResults([data.match])
      } else {
        setMatchResults([])
      }
      if (data.screenshot_base64) {
        setPreviewSrc(`data:image/jpeg;base64,${data.screenshot_base64}`)
      }
    } catch (e: unknown) {
      setMatchError(e instanceof Error ? e.message : String(e))
      setMatchLatency(Math.round(performance.now() - t0))
    } finally {
      setMatchLoading(false)
    }
  }

  const handleOcrTest = async () => {
    setOcrLoading(true)
    setOcrResults([])
    setOcrError('')
    try {
      const req: Record<string, unknown> = {}
      if (deviceId !== '') req.device_id = deviceId
      if (ocrKeyword.trim()) req.keyword = ocrKeyword.trim()
      const data = await visionTestApi.ocrTest(req as any) as any
      setOcrResults(data.texts || data.result || [])
    } catch (e: unknown) {
      setOcrError(e instanceof Error ? e.message : String(e))
    } finally {
      setOcrLoading(false)
    }
  }

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  return (
    <Box sx={{ p: 3, bgcolor: colors.bg, minHeight: '100vh', maxWidth: 1100, mx: 'auto' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 3 }}>
        <Button startIcon={<ArrowBackIcon />} onClick={() => nav('/')} size="small">返回</Button>
        <Typography variant="h5">模板匹配管理</Typography>
        <Box sx={{ flex: 1 }} />
        <Button size="small" variant="outlined" onClick={loadHealth} disabled={healthLoading}
          startIcon={healthLoading ? <CircularProgress size={14} /> : <RefreshIcon fontSize="small" />}>
          状态检查
        </Button>
      </Box>

      {/* Health bar */}
      {Object.keys(health).length > 0 && (
        <Paper sx={{ p: 2, bgcolor: colors.card, mb: 3, display: 'flex', gap: 3, flexWrap: 'wrap', alignItems: 'center' }}>
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
            <Typography fontSize={13} fontWeight="bold">OpenCV:</Typography>
            <Typography fontSize={13} color={colors.success}>{(health as any).opencv_version || '-'}</Typography>
          </Box>
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
            <Typography fontSize={13} fontWeight="bold">PaddleOCR:</Typography>
            <Typography fontSize={13} color={(health as any).ocr_loaded ? colors.success : '#aaa'}>
              {(health as any).ocr_loaded ? '已加载' : '未加载'}
            </Typography>
          </Box>
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
            <Typography fontSize={13} fontWeight="bold">模板目录:</Typography>
            <Typography fontSize={13}>{(health as any).template_dir || '-'}</Typography>
          </Box>
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
            <Typography fontSize={13} fontWeight="bold">模板数:</Typography>
            <Typography fontSize={13}>{(health as any).total_templates ?? '-'}</Typography>
          </Box>
        </Paper>
      )}

      <Grid container spacing={3}>
        {/* ═══ Left: Template file browser ═══ */}
        <Grid item xs={12} md={5}>
          <Paper sx={{ p: 2, bgcolor: colors.card, height: '100%' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
              <Typography variant="subtitle1" fontWeight="bold">模板图库</Typography>
              <Box sx={{ display: 'flex', gap: 0.5 }}>
                <Tooltip title="新建文件夹">
                  <IconButton size="small" onClick={() => setFolderDialogOpen(true)}>
                    <CreateNewFolderIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
                <Tooltip title="上传模板图">
                  <IconButton size="small" component="label">
                    <UploadFileIcon fontSize="small" />
                    <input ref={fileInputRef} type="file" hidden accept="image/*" onChange={handleUpload} />
                  </IconButton>
                </Tooltip>
                <Tooltip title="刷新">
                  <IconButton size="small" onClick={loadIcons} disabled={iconsLoading}>
                    {iconsLoading ? <CircularProgress size={14} /> : <RefreshIcon fontSize="small" />}
                  </IconButton>
                </Tooltip>
              </Box>
            </Box>

            {/* App tabs */}
            <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', mb: 2 }}>
              {appNames.map((app) => (
                <Button key={app} size="small" variant={selectedApp === app ? 'contained' : 'outlined'}
                  onClick={() => setSelectedApp(app)}
                  sx={{ fontSize: 12, minWidth: 'auto', px: 1.5 }}>
                  {app} ({(apps[app] || []).length})
                </Button>
              ))}
            </Box>

            {currentIcons.length === 0 ? (
              <Alert severity="info" sx={{ fontSize: 12 }}>
                {selectedApp ? `"${selectedApp}" 下暂无模板图，请点击上传` : '请先选择或新建一个应用文件夹'}
              </Alert>
            ) : (
              <List dense disablePadding sx={{ maxHeight: 480, overflow: 'auto' }}>
                {currentIcons.map((icon) => (
                  <ListItem
                    key={icon.name}
                    disablePadding
                    onClick={() => setSelectedTemplate(icon.name.replace(/\.[^.]+$/, ''))}
                    sx={{
                      px: 1.5, py: 0.5, mb: 0.5, borderRadius: 1, cursor: 'pointer',
                      border: `1px solid ${selectedTemplate === icon.name.replace(/\.[^.]+$/, '') ? colors.highlight : '#333'}`,
                      bgcolor: selectedTemplate === icon.name.replace(/\.[^.]+$/, '') ? 'rgba(0,150,255,0.08)' : 'transparent',
                      '&:hover': { bgcolor: 'rgba(0,150,255,0.04)' },
                    }}
                  >
                    <Box sx={{ width: 40, height: 40, mr: 1.5, borderRadius: 1, overflow: 'hidden', border: '1px solid #444', flexShrink: 0 }}>
                      <img
                        src={templateIconsApi.get(selectedApp, icon.name)}
                        alt={icon.name}
                        style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                        onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
                      />
                    </Box>
                    <ListItemText
                      primary={<Typography fontSize={13}>{icon.name}</Typography>}
                      secondary={<Typography fontSize={11} color="text.secondary">{formatSize(icon.size)}</Typography>}
                    />
                    <ListItemSecondaryAction>
                      <Tooltip title="删除">
                        <IconButton size="small" edge="end"
                          onClick={(e) => { e.stopPropagation(); setDeleteTarget({ app: selectedApp, name: icon.name }) }}>
                          <DeleteIcon fontSize="small" sx={{ color: '#666' }} />
                        </IconButton>
                      </Tooltip>
                    </ListItemSecondaryAction>
                  </ListItem>
                ))}
              </List>
            )}
          </Paper>
        </Grid>

        {/* ═══ Right: Match test ═══ */}
        <Grid item xs={12} md={7}>
          <Paper sx={{ p: 2, bgcolor: colors.card, mb: 3 }}>
            <Typography variant="subtitle1" fontWeight="bold" sx={{ mb: 2 }}>
              <ImageSearchIcon fontSize="small" sx={{ verticalAlign: 'middle', mr: 0.5 }} />
              模板匹配测试
            </Typography>

            <Box sx={{ mb: 2 }}>
              <Typography fontSize={13} sx={{ mb: 1 }}>匹配阈值: <strong>{threshold.toFixed(2)}</strong></Typography>
              <Slider
                value={threshold}
                onChange={(_, v) => setThreshold(v as number)}
                min={0.5} max={1.0} step={0.01}
                valueLabelDisplay="auto"
                sx={{ color: colors.highlight }}
              />
            </Box>

            <Grid container spacing={1} sx={{ mb: 2 }}>
              <Grid item xs={6}>
                <TextField
                  fullWidth size="small" label="模板名称"
                  value={selectedTemplate}
                  onChange={(e) => setSelectedTemplate(e.target.value)}
                  placeholder="从左侧选择或手动输入"
                />
              </Grid>
              <Grid item xs={6}>
                <TextField
                  fullWidth size="small" label="设备ID"
                  type="number"
                  value={deviceId}
                  onChange={(e) => setDeviceId(e.target.value ? Number(e.target.value) : '')}
                  placeholder="截图设备"
                />
              </Grid>
            </Grid>

            <Button
              fullWidth variant="contained" onClick={handleMatchTest}
              disabled={matchLoading || !selectedTemplate}
              startIcon={matchLoading ? <CircularProgress size={14} /> : <ImageSearchIcon />}
              sx={{ bgcolor: colors.highlight, mb: 2 }}
            >
              开始匹配测试
            </Button>

            {matchError && <Alert severity="error" sx={{ mb: 2, fontSize: 12 }}>{matchError}</Alert>}

            {matchResults.length > 0 && (
              <Box sx={{
                p: 2, borderRadius: 1, bgcolor: 'rgba(0,200,83,0.08)',
                border: `1px solid ${colors.success}44`, mb: 2,
              }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                  <CheckCircleIcon fontSize="small" sx={{ color: colors.success }} />
                  <Typography fontSize={13} fontWeight="bold">
                    匹配成功 · 找到 {matchResults.length} 个目标
                    {matchLatency !== null && ` · ${matchLatency}ms`}
                  </Typography>
                </Box>
                {matchResults.map((m, i) => (
                  <Typography key={i} fontSize={12} sx={{ ml: 3 }}>
                    #{i + 1} ({m.x}, {m.y}) {m.w}×{m.h} 置信度: {(m.confidence * 100).toFixed(1)}%
                  </Typography>
                ))}
              </Box>
            )}

            {!matchLoading && matchResults.length === 0 && matchLatency !== null && !matchError && (
              <Box sx={{
                p: 2, borderRadius: 1, bgcolor: 'rgba(255,23,68,0.08)',
                border: `1px solid ${colors.danger}44`, mb: 2,
              }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <ErrorIcon fontSize="small" sx={{ color: colors.danger }} />
                  <Typography fontSize={13} fontWeight="bold">
                    未匹配到目标 · {matchLatency}ms
                  </Typography>
                </Box>
                <Typography fontSize={12} color="text.secondary" sx={{ mt: 0.5 }}>
                  尝试降低阈值，或确认模板图片是否正确
                </Typography>
              </Box>
            )}

            {/* Preview with overlay */}
            {previewSrc && (
              <Box sx={{ position: 'relative', borderRadius: 1, overflow: 'hidden', border: '1px solid #333' }}>
                <img src={previewSrc} alt="preview" style={{ width: '100%', display: 'block' }} />
                <svg style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%' }}>
                  {matchResults.map((m, i) => (
                    <rect
                      key={i}
                      x={`${(m.x / 1280) * 100}%`}
                      y={`${(m.y / 720) * 100}%`}
                      width={`${(m.w / 1280) * 100}%`}
                      height={`${(m.h / 720) * 100}%`}
                      fill="none" stroke="#00ff00" strokeWidth="2"
                    />
                  ))}
                </svg>
              </Box>
            )}
          </Paper>

          {/* OCR test */}
          <Paper sx={{ p: 2, bgcolor: colors.card }}>
            <Typography variant="subtitle1" fontWeight="bold" sx={{ mb: 2 }}>
              <TextFieldsIcon fontSize="small" sx={{ verticalAlign: 'middle', mr: 0.5 }} />
              OCR 识字测试
            </Typography>
            <Grid container spacing={1} sx={{ mb: 2 }}>
              <Grid item xs={8}>
                <TextField
                  fullWidth size="small" label="关键词（可选）"
                  value={ocrKeyword}
                  onChange={(e) => setOcrKeyword(e.target.value)}
                  placeholder="留空返回全部文字"
                />
              </Grid>
              <Grid item xs={4}>
                <Button
                  fullWidth variant="contained" onClick={handleOcrTest}
                  disabled={ocrLoading}
                  startIcon={ocrLoading ? <CircularProgress size={14} /> : <TextFieldsIcon />}
                  sx={{ height: '100%' }}
                >
                  识字
                </Button>
              </Grid>
            </Grid>
            {ocrError && <Alert severity="error" sx={{ fontSize: 12 }}>{ocrError}</Alert>}
            {ocrResults.length > 0 && (
              <Box sx={{ maxHeight: 200, overflow: 'auto' }}>
                {ocrResults.map((t, i) => (
                  <Typography key={i} fontSize={12} sx={{ py: 0.3 }}>
                    「{t.text}」({Math.round(t.x)}, {Math.round(t.y)}) {t.confidence ? `${(t.confidence * 100).toFixed(0)}%` : ''}
                  </Typography>
                ))}
              </Box>
            )}
          </Paper>
        </Grid>
      </Grid>

      {/* New folder dialog */}
      <Dialog open={folderDialogOpen} onClose={() => setFolderDialogOpen(false)}>
        <DialogTitle>新建应用文件夹</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus fullWidth label="文件夹名称（应用名）" sx={{ mt: 1 }}
            value={newFolderName}
            onChange={(e) => setNewFolderName(e.target.value)}
            placeholder="例如: 抖音"
            onKeyDown={(e) => { if (e.key === 'Enter') handleCreateFolder() }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setFolderDialogOpen(false)}>取消</Button>
          <Button variant="contained" onClick={handleCreateFolder} disabled={!newFolderName.trim()}>创建</Button>
        </DialogActions>
      </Dialog>

      {/* Delete confirm dialog */}
      <Dialog open={!!deleteTarget} onClose={() => setDeleteTarget(null)}>
        <DialogTitle>确认删除</DialogTitle>
        <DialogContent>
          <Typography>确定删除模板图 "{deleteTarget?.name}" ？此操作不可恢复。</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteTarget(null)}>取消</Button>
          <Button variant="contained" color="error" onClick={handleDelete}>删除</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
