import { useRef, useState, useEffect, useCallback } from 'react'
import {
  Box, Typography, Dialog, DialogTitle, DialogContent, DialogActions,
  Button, TextField, Select, MenuItem,
} from '@mui/material'
import { useDeviceStore } from '../../stores/deviceStore'
import { useRuleStore } from '../../stores/ruleStore'
import { useLogStore } from '../../stores/logStore'
import { templateIconsApi, devicesApi } from '../../api/devices'

const LONG_PRESS_MS = 400

interface Props {
  onCoordClick?: (px: number, py: number) => void
}

export default function PhonePreview({ onCoordClick }: Props) {
  const previewRef = useRef<HTMLDivElement>(null)
  const selectedDeviceId = useDeviceStore((s) => s.selectedDeviceId)
  const refreshTick = useDeviceStore((s) => s.refreshTick)
  const visionTargets = useDeviceStore((s) => s.visionTargets)
  const setCurrentFrameSrc = useDeviceStore((s) => s.setCurrentFrameSrc)
  const setCurrentFrameBlob = useDeviceStore((s) => s.setCurrentFrameBlob)
  const armLinkEnabled = useDeviceStore((s) => s.armLinkEnabled)
  const setCoordinate = useRuleStore((s) => s.setCoordinate)
  const selectedSubId = useRuleStore((s) => s.selectedSubId)
  const addLog = useLogStore((s) => s.addLog)
  const imgRef = useRef<HTMLImageElement>(null)
  const [imgSrc, setImgSrc] = useState('')
  const [previewSize, setPreviewSize] = useState({ width: 0, height: 0 })
  const objectUrlRef = useRef<string>('')
  const blobRef = useRef<Blob | null>(null)

  const [fetchLoading, setFetchLoading] = useState(false)

  // Long-press crop state
  const longPressTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mouseDownCoords = useRef<{ x: number; y: number; cx: number; cy: number } | null>(null)
  const [isCropping, setIsCropping] = useState(false)
  const [cropStart, setCropStart] = useState<{ x: number; y: number } | null>(null)
  const [cropEnd, setCropEnd] = useState<{ x: number; y: number } | null>(null)

  // Save dialog
  const [saveDialogOpen, setSaveDialogOpen] = useState(false)
  const [saveName, setSaveName] = useState('')
  const [saveApp, setSaveApp] = useState('_common')
  const [cropRegion, setCropRegion] = useState<{ x: number; y: number; w: number; h: number } | null>(null)
  const [appFolders, setAppFolders] = useState<string[]>([])

  useEffect(() => {
    const el = previewRef.current
    if (!el) return
    const update = () => setPreviewSize({ width: el.clientWidth, height: el.clientHeight })
    update()
    const ro = new ResizeObserver(update)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // Load app folders for save dialog
  useEffect(() => {
    if (saveDialogOpen) {
      templateIconsApi.list().then(data => {
        setAppFolders(Object.keys(data.apps || {}))
      }).catch(() => {})
    }
  }, [saveDialogOpen])

  // 仅在设备切换或点击"刷新图像"时取一帧，不自动轮询
  useEffect(() => {
    if (!selectedDeviceId) { setImgSrc(''); setCurrentFrameSrc(''); return }

    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 8000)

    setFetchLoading(true)
    const fetchOnce = async () => {
      const token = localStorage.getItem('token') || ''
      try {
        const res = await fetch(`/api/v1/devices/${selectedDeviceId}/snapshot?t=${Date.now()}`, {
          headers: { Authorization: `Bearer ${token}` },
          signal: controller.signal,
        })
        if (!res.ok) {
          addLog(`刷新图像失败: HTTP ${res.status}`, 'error')
          return
        }
        const blob = await res.blob()
        blobRef.current = blob
        const url = URL.createObjectURL(blob)
        if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current)
        objectUrlRef.current = url
        setImgSrc(url)
        setCurrentFrameSrc(url)
        setCurrentFrameBlob(blob)
        addLog('刷新图像: 已获取最新画面', 'success')
      } catch (err: unknown) {
        if (err instanceof Error && err.name === 'AbortError') {
          addLog('刷新图像超时 (>8s)，请检查设备连接', 'error')
        } else {
          addLog(`刷新图像失败: ${err}`, 'error')
        }
      } finally {
        clearTimeout(timer)
        setFetchLoading(false)
      }
    }

    fetchOnce()
    return () => {
      controller.abort()
      clearTimeout(timer)
      setFetchLoading(false)
    }
  }, [selectedDeviceId, refreshTick])

  // Calculate the rendered image dimensions & offset
  const getImageLayout = useCallback(() => {
    const cw = previewSize.width
    const ch = previewSize.height
    if (!cw || !ch) return null
    const imgAspect = 720 / 1280
    const containerAspect = cw / ch
    const drawWidth = containerAspect > imgAspect ? ch * imgAspect : cw
    const drawHeight = containerAspect > imgAspect ? ch : cw / imgAspect
    const offsetLeft = (cw - drawWidth) / 2
    const offsetTop = (ch - drawHeight) / 2
    return { drawWidth, drawHeight, offsetLeft, offsetTop }
  }, [previewSize])

  // Convert screen click to image pixel coordinates
  const screenToPixel = useCallback((clientX: number, clientY: number) => {
    const img = imgRef.current
    if (!img) return null
    const rect = img.getBoundingClientRect()
    const scaleX = 720 / rect.width
    const scaleY = 1280 / rect.height
    const px = Math.round((clientX - rect.left) * scaleX)
    const py = Math.round((clientY - rect.top) * scaleY)
    return { x: Math.max(0, Math.min(720, px)), y: Math.max(0, Math.min(1280, py)) }
  }, [])

  // --- Mouse interaction: short click = coordinate, long-press drag = crop ---
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button !== 0) return
    const coords = screenToPixel(e.clientX, e.clientY)
    if (!coords) return
    mouseDownCoords.current = { ...coords, cx: e.clientX, cy: e.clientY }
    longPressTimer.current = setTimeout(() => {
      setIsCropping(true)
      setCropStart(coords)
      setCropEnd(coords)
      addLog('长按截图模式：拖动选择区域', 'info')
    }, LONG_PRESS_MS)
    e.preventDefault()
  }, [screenToPixel, addLog])

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (longPressTimer.current && mouseDownCoords.current) {
      const dx = Math.abs(e.clientX - mouseDownCoords.current.cx)
      const dy = Math.abs(e.clientY - mouseDownCoords.current.cy)
      if (dx > 5 || dy > 5) {
        clearTimeout(longPressTimer.current)
        longPressTimer.current = null
      }
    }
    if (isCropping) {
      const coords = screenToPixel(e.clientX, e.clientY)
      if (coords) setCropEnd(coords)
    }
  }, [isCropping, screenToPixel])

  const handleMouseUp = useCallback((e: React.MouseEvent) => {
    if (longPressTimer.current) {
      clearTimeout(longPressTimer.current)
      longPressTimer.current = null
    }
    if (isCropping && cropStart && cropEnd) {
      setIsCropping(false)
      const x1 = Math.min(cropStart.x, cropEnd.x)
      const y1 = Math.min(cropStart.y, cropEnd.y)
      const x2 = Math.max(cropStart.x, cropEnd.x)
      const y2 = Math.max(cropStart.y, cropEnd.y)
      const w = x2 - x1
      const h = y2 - y1
      if (w > 10 && h > 10) {
        setCropRegion({ x: x1, y: y1, w, h })
        setSaveDialogOpen(true)
      } else {
        setCropStart(null)
        setCropEnd(null)
      }
    } else if (!isCropping && mouseDownCoords.current) {
      const coords = screenToPixel(e.clientX, e.clientY)
      if (coords) {
        if (onCoordClick) {
          onCoordClick(coords.x, coords.y)
        } else {
          setCoordinate(coords.x, coords.y)
          addLog(`坐标已获取: (${coords.x}, ${coords.y})${selectedSubId ? ' → 子动作' : ''}`, 'success')
        }
        // 联动模式：点击时机械臂跟随移动
        if (armLinkEnabled && selectedDeviceId) {
          devicesApi.moveToPixel(selectedDeviceId, coords.x, coords.y)
            .then(res => {
              const coordMsg = `pixel(${coords.x},${coords.y}) → mech(${res.mech.x.toFixed(2)},${res.mech.y.toFixed(2)})mm`
              if (res.moved) {
                addLog(`机械臂已移动: ${coordMsg}${res.calibrated ? '' : ' [未标定]'}`, 'success')
              } else {
                addLog(`坐标转换: ${coordMsg} | 移动失败: ${res.move_error}`, 'error')
              }
            })
            .catch(err => {
              addLog(`机械臂联动失败: ${err instanceof Error ? err.message : String(err)}`, 'error')
            })
        }
      }
    }
    mouseDownCoords.current = null
  }, [isCropping, cropStart, cropEnd, screenToPixel, onCoordClick, setCoordinate, selectedSubId, addLog, armLinkEnabled, selectedDeviceId])

  const handleSaveCrop = async () => {
    if (!cropRegion || !saveName.trim()) return
    const name = saveName.trim().replace(/\.[^.]+$/, '') + '.jpg'
    try {
      if (blobRef.current) {
        // 直接用已显示的图片裁剪（不再重新截图，更快更可靠）
        const buf = await blobRef.current.arrayBuffer()
        const bytes = new Uint8Array(buf)
        let binary = ''
        for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i])
        const b64 = btoa(binary)
        await templateIconsApi.cropFromBase64(b64, cropRegion, saveApp, name)
      } else if (selectedDeviceId) {
        await templateIconsApi.cropFromDevice(selectedDeviceId, cropRegion, saveApp, name)
      } else {
        addLog('无可用图像数据', 'error')
        return
      }
      addLog(`截图已保存: ${saveApp}/${name}`, 'success')
    } catch (e: unknown) {
      addLog(`截图保存失败: ${e instanceof Error ? e.message : String(e)}`, 'error')
    }
    setSaveDialogOpen(false)
    setSaveName('')
    setCropStart(null)
    setCropEnd(null)
    setCropRegion(null)
  }

  // Render crop selection rectangle
  const renderCropRect = () => {
    if (!cropStart || !cropEnd) return null
    const layout = getImageLayout()
    if (!layout) return null
    const { drawWidth, drawHeight, offsetLeft, offsetTop } = layout

    const x1 = Math.min(cropStart.x, cropEnd.x)
    const y1 = Math.min(cropStart.y, cropEnd.y)
    const x2 = Math.max(cropStart.x, cropEnd.x)
    const y2 = Math.max(cropStart.y, cropEnd.y)

    const left = offsetLeft + (x1 / 720) * drawWidth
    const top = offsetTop + (y1 / 1280) * drawHeight
    const width = ((x2 - x1) / 720) * drawWidth
    const height = ((y2 - y1) / 1280) * drawHeight

    return (
      <Box sx={{
        position: 'absolute', left, top, width, height,
        border: '2px dashed #ff9100',
        bgcolor: 'rgba(255,145,0,0.1)',
        pointerEvents: 'none',
        zIndex: 10,
      }} />
    )
  }

  return (
    <>
      <Box
        ref={previewRef}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={() => {
          if (longPressTimer.current) { clearTimeout(longPressTimer.current); longPressTimer.current = null }
          if (isCropping) { setIsCropping(false); setCropStart(null); setCropEnd(null) }
        }}
        sx={{
          bgcolor: '#111',
          borderRadius: 1,
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          flex: 1,
          minHeight: 0,
          cursor: isCropping ? 'crosshair' : 'crosshair',
          overflow: 'hidden',
          position: 'relative',
          userSelect: 'none',
        }}
      >
        {imgSrc ? (
          <>
            <img
              ref={imgRef}
              src={imgSrc}
              alt="手机画面"
              draggable={false}
              style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain', userSelect: 'none', pointerEvents: 'none' }}
              onError={() => setImgSrc('')}
            />
            {/* Green rectangle overlays for match results */}
            {(() => {
              const layout = getImageLayout()
              if (!layout) return null
              const { drawWidth, drawHeight, offsetLeft, offsetTop } = layout

              return visionTargets.map((t, idx) => {
                // (x, y) = center coords in 720×1280 space, (w, h) = box size
                const left = offsetLeft + ((t.x - t.w / 2) / 720) * drawWidth
                const top = offsetTop + ((t.y - t.h / 2) / 1280) * drawHeight
                const width = (t.w / 720) * drawWidth
                const height = (t.h / 1280) * drawHeight
                return (
                  <Box
                    key={`${t.label}-${idx}`}
                    sx={{
                      position: 'absolute',
                      left,
                      top,
                      width,
                      height,
                      border: '2px solid #00ff00',
                      pointerEvents: 'none',
                      zIndex: 5,
                    }}
                  >
                    <Box
                      sx={{
                        position: 'absolute',
                        left: 0,
                        top: -16,
                        px: 0.4,
                        py: 0.1,
                        fontSize: 9,
                        lineHeight: 1.2,
                        color: '#000',
                        bgcolor: '#00ff00',
                        whiteSpace: 'nowrap',
                        maxWidth: 120,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        fontWeight: 'bold',
                      }}
                    >
                      {t.label}
                    </Box>
                  </Box>
                )
              })
            })()}
            {/* Crop selection rectangle */}
            {renderCropRect()}
          </>
        ) : (
          <Typography color="text.secondary" sx={{ py: 8 }}>
            {!selectedDeviceId ? '请先选择设备' : fetchLoading ? '正在获取画面...' : '暂无画面'}
          </Typography>
        )}
      </Box>

      {/* Save crop dialog */}
      <Dialog open={saveDialogOpen} onClose={() => { setSaveDialogOpen(false); setCropStart(null); setCropEnd(null) }}>
        <DialogTitle>保存截图为模板</DialogTitle>
        <DialogContent>
          <Typography fontSize={12} color="text.secondary" sx={{ mb: 1 }}>
            区域: ({cropRegion?.x}, {cropRegion?.y}) {cropRegion?.w}×{cropRegion?.h}
          </Typography>
          <Select
            fullWidth size="small" value={saveApp}
            onChange={(e) => setSaveApp(e.target.value)}
            sx={{ mb: 1 }}
          >
            {appFolders.map(f => <MenuItem key={f} value={f}>{f}</MenuItem>)}
            <MenuItem value="_common">_common (公共)</MenuItem>
          </Select>
          <TextField
            autoFocus fullWidth size="small" label="模板名称"
            value={saveName}
            onChange={(e) => setSaveName(e.target.value)}
            placeholder="例如: 微信"
            onKeyDown={(e) => { if (e.key === 'Enter') handleSaveCrop() }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => { setSaveDialogOpen(false); setCropStart(null); setCropEnd(null) }}>取消</Button>
          <Button variant="contained" onClick={handleSaveCrop} disabled={!saveName.trim()}>保存</Button>
        </DialogActions>
      </Dialog>
    </>
  )
}
