import { Box, Typography, Button, Paper, Select, MenuItem, Grid, TextField, Alert, Snackbar, Chip, Slider, IconButton, Checkbox, FormControlLabel } from '@mui/material'
import { Add as AddIcon, Remove as RemoveIcon } from '@mui/icons-material'
import { useDeviceStore } from '../stores/deviceStore'
import { devicesApi } from '../api/devices'
import apiClient from '../api/client'
import PhonePreview from '../components/DevTools/PhonePreview'
import { colors } from '../theme'
import { useState, useEffect } from 'react'

// 手眼标定：4个标定点，用户在图像上点击记录像素坐标，
// 物理操控机械臂到对应位置后点击"读取当前臂位置"记录机械坐标
const POINTS = [1, 2, 3, 4] as const
type PtIdx = typeof POINTS[number]

type Pt = { px: string; py: string; mx: string; my: string }
type Forms = Record<PtIdx, Pt>
const initForms = (): Forms =>
  Object.fromEntries(POINTS.map(i => [i, { px: '', py: '', mx: '', my: '' }])) as Forms

const POINT_HINTS = [
  '建议: 手机屏幕左上角附近',
  '建议: 手机屏幕右上角附近',
  '建议: 手机屏幕左下角附近',
  '建议: 手机屏幕右下角附近',
]

export default function Calibration() {
  const devices = useDeviceStore((s) => s.devices)
  const { selectedDeviceId, selectDevice, fetchDevices, triggerRefresh, armLinkEnabled, setArmLinkEnabled } = useDeviceStore()
  const [forms, setForms] = useState<Forms>(initForms())
  const [activeIdx, setActiveIdx] = useState<PtIdx | null>(1)
  const [readingPos, setReadingPos] = useState<PtIdx | null>(null)
  const [offsetX, setOffsetX] = useState(0)
  const [offsetY, setOffsetY] = useState(0)
  const [toast, setToast] = useState<{ msg: string; severity: 'success' | 'error' | 'warning' | 'info' } | null>(null)

  useEffect(() => { fetchDevices() }, [])
  useEffect(() => { if (selectedDeviceId) triggerRefresh() }, [selectedDeviceId])

  // 加载已有标定数据
  useEffect(() => {
    if (!selectedDeviceId) return
    devicesApi.getCalibration(selectedDeviceId).then((cal) => {
      if (cal && cal.pixel_points && cal.mech_points) {
        const loaded = initForms()
        POINTS.forEach((i) => {
          const px = cal.pixel_points[i - 1]
          const mx = cal.mech_points[i - 1]
          if (px && mx) loaded[i] = {
            px: String(px[0]), py: String(px[1]),
            mx: String(mx[0]), my: String(mx[1]),
          }
        })
        setForms(loaded)
        setOffsetX(cal.offset_x ?? 0)
        setOffsetY(cal.offset_y ?? 0)
      }
    }).catch(() => {})
  }, [selectedDeviceId])

  const setField = (idx: PtIdx, field: keyof Pt, val: string) =>
    setForms(prev => ({ ...prev, [idx]: { ...prev[idx], [field]: val } }))

  // 点击图像 → 记录像素坐标
  const handleCoordClick = (px: number, py: number) => {
    if (!activeIdx) {
      setToast({ msg: '请先点击左侧数字标号选中标定点', severity: 'warning' })
      return
    }
    setForms(prev => ({ ...prev, [activeIdx]: { ...prev[activeIdx], px: String(px), py: String(py) } }))
    // 自动跳到下一个未填像素坐标的点
    const next = POINTS.find(i => i !== activeIdx && (!forms[i].px || !forms[i].py))
    if (next) setActiveIdx(next)
  }

  // 读取机械臂当前位置
  const handleReadPosition = async (idx: PtIdx) => {
    if (!selectedDeviceId) {
      setToast({ msg: '请先选择设备', severity: 'warning' }); return
    }
    setReadingPos(idx)
    try {
      const pos = await devicesApi.getPosition(selectedDeviceId)
      setForms(prev => ({
        ...prev,
        [idx]: { ...prev[idx], mx: String(pos.x), my: String(pos.y) }
      }))
      setToast({ msg: `已读取机械坐标: X=${pos.x}, Y=${pos.y}, Z=${pos.z}`, severity: 'success' })
    } catch (e) {
      setToast({ msg: `读取位置失败: ${e}`, severity: 'error' })
    } finally {
      setReadingPos(null)
    }
  }

  const pixelFilled = (f: Pt) => f.px && f.py
  const mechFilled = (f: Pt) => f.mx && f.my
  const allFilled = POINTS.every(i => pixelFilled(forms[i]) && mechFilled(forms[i]))

  const cropFromForms = (() => {
    const xs = POINTS.map(i => parseFloat(forms[i].px)).filter(v => !isNaN(v) && v > 0)
    const ys = POINTS.map(i => parseFloat(forms[i].py)).filter(v => !isNaN(v) && v > 0)
    if (xs.length < 2 || ys.length < 2) return null
    return { x1: Math.min(...xs), y1: Math.min(...ys), x2: Math.max(...xs), y2: Math.max(...ys) }
  })()

  const handleSaveAll = async () => {
    const incomplete = POINTS.filter(i => !pixelFilled(forms[i]) || !mechFilled(forms[i]))
    if (incomplete.length > 0) {
      setToast({ msg: `点 ${incomplete.join('、')} 还未填完整`, severity: 'warning' }); return
    }
    if (!selectedDeviceId) {
      setToast({ msg: '请先选择设备', severity: 'warning' }); return
    }
    try {
      if (cropFromForms) {
        await apiClient.post('/settings/screen_crop', cropFromForms)
      }
      await devicesApi.calibrate(selectedDeviceId, {
        pixel_points: POINTS.map(i => [parseFloat(forms[i].px), parseFloat(forms[i].py)]),
        mech_points: POINTS.map(i => [parseFloat(forms[i].mx), parseFloat(forms[i].my)]),
        offset_x: offsetX,
        offset_y: offsetY,
      })
      setToast({ msg: '手眼标定保存成功！', severity: 'success' })
    } catch (e) {
      setToast({ msg: `保存失败: ${e}`, severity: 'error' })
    }
  }

  return (
    <Box sx={{ p: 3, bgcolor: colors.bg, minHeight: '100vh' }}>
      <Snackbar open={!!toast} autoHideDuration={5000} onClose={() => setToast(null)}
        anchorOrigin={{ vertical: 'top', horizontal: 'center' }}>
        <Alert onClose={() => setToast(null)} severity={toast?.severity ?? 'info'} sx={{ width: '100%' }}>
          {toast?.msg}
        </Alert>
      </Snackbar>

      <Typography variant="h5" sx={{ mb: 0.5 }}>手眼标定</Typography>
      <Typography variant="caption" sx={{ color: '#888', mb: 2, display: 'block' }}>
        像素坐标（摄像头）→ 机械坐标（机械臂 mm），建立仿射变换映射
      </Typography>

      <Box sx={{ display: 'flex', gap: 1, mb: 2, alignItems: 'center', flexWrap: 'wrap' }}>
        <Select size="small" value={selectedDeviceId || ''} onChange={(e) => selectDevice(Number(e.target.value))}
          sx={{ minWidth: 140 }} displayEmpty>
          <MenuItem value="" disabled>选择设备</MenuItem>
          {devices.map((d) => <MenuItem key={d.id} value={d.id}>#{d.id} - {d.ip}</MenuItem>)}
        </Select>
        <Button variant="outlined" onClick={() => triggerRefresh()}>刷新图像</Button>
        <Button variant="outlined" onClick={async () => {
          if (!selectedDeviceId) return
          try { await devicesApi.home(selectedDeviceId) } catch {}
        }} disabled={!selectedDeviceId}>归位</Button>
        <FormControlLabel
          control={<Checkbox size="small" checked={armLinkEnabled} onChange={(e) => setArmLinkEnabled(e.target.checked)} sx={{ color: armLinkEnabled ? colors.success : undefined, '&.Mui-checked': { color: colors.success } }} />}
          label="联动"
          sx={{ '& .MuiTypography-root': { fontSize: 13, color: armLinkEnabled ? colors.success : undefined } }}
        />
        <Button variant="contained" onClick={handleSaveAll} disabled={!allFilled}
          sx={{ bgcolor: colors.success }}>
          保存标定
        </Button>
      </Box>

      {cropFromForms && (
        <Alert severity="info" sx={{ mb: 2 }}>
          屏幕裁剪区域（像素外框）：x1={cropFromForms.x1}, y1={cropFromForms.y1},
          x2={cropFromForms.x2}, y2={cropFromForms.y2}
          　宽={cropFromForms.x2 - cropFromForms.x1}px 高={cropFromForms.y2 - cropFromForms.y1}px
        </Alert>
      )}

      <Grid container spacing={2}>
        <Grid item xs={5}>
          <PhonePreview onCoordClick={handleCoordClick} />
          <Typography variant="caption" sx={{ color: '#888', mt: 0.5, display: 'block' }}>
            {activeIdx
              ? `点击图像 → 填入第 ${activeIdx} 个标定点的像素坐标`
              : '点击右侧数字标号选中标定点，再点击图像'}
          </Typography>
        </Grid>

        <Grid item xs={7}>
          <Paper sx={{ p: 2, bgcolor: colors.card }}>
            <Alert severity="info" sx={{ mb: 2, py: 0.5 }}>
              <strong>操作流程：</strong>
              ① 点击图像取像素坐标 → ② 物理操控机械臂移至手机屏幕对应点 → ③ 点「读取臂位置」记录机械坐标 → 重复4次 → 保存
            </Alert>
            {POINTS.map((idx) => {
              const form = forms[idx]
              const isActive = activeIdx === idx
              const pxDone = pixelFilled(form)
              const mxDone = mechFilled(form)
              const allDone = pxDone && mxDone
              return (
                <Box key={idx} sx={{
                  mb: 1.5, p: 1.5, borderRadius: 1,
                  border: isActive ? '1px solid #1976d2' : allDone ? '1px solid #2e7d32' : '1px solid #333',
                  bgcolor: isActive ? 'rgba(25,118,210,0.06)' : 'transparent',
                }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                    <Box onClick={() => setActiveIdx(isActive ? null : idx)} sx={{
                      width: 28, height: 28, borderRadius: '50%', display: 'flex',
                      alignItems: 'center', justifyContent: 'center', cursor: 'pointer',
                      bgcolor: isActive ? '#1976d2' : allDone ? '#2e7d32' : '#444',
                      color: '#fff', fontWeight: 700, fontSize: 14, flexShrink: 0,
                    }}>{idx}</Box>
                    <Typography variant="caption" sx={{ color: '#aaa', flex: 1 }}>
                      {POINT_HINTS[idx - 1]}
                    </Typography>
                    {allDone && <Chip label="✓ 完成" size="small" sx={{ bgcolor: '#1b5e20', color: '#69f0ae', height: 20 }} />}
                  </Box>

                  <Box sx={{ display: 'flex', gap: 1, mb: 1 }}>
                    <TextField size="small" label="像素 X"
                      value={form.px}
                      onChange={(e) => setField(idx, 'px', e.target.value)}
                      sx={{ flex: 1, '& input': { py: 0.5, fontSize: 13 } }}
                      InputProps={{ sx: { bgcolor: pxDone ? 'rgba(46,125,50,0.1)' : undefined } }}
                    />
                    <TextField size="small" label="像素 Y"
                      value={form.py}
                      onChange={(e) => setField(idx, 'py', e.target.value)}
                      sx={{ flex: 1, '& input': { py: 0.5, fontSize: 13 } }}
                      InputProps={{ sx: { bgcolor: pxDone ? 'rgba(46,125,50,0.1)' : undefined } }}
                    />
                  </Box>

                  <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
                    <TextField size="small" label="机械 X (mm)"
                      value={form.mx}
                      onChange={(e) => setField(idx, 'mx', e.target.value)}
                      sx={{ flex: 1, '& input': { py: 0.5, fontSize: 13 } }}
                      InputProps={{ sx: { bgcolor: mxDone ? 'rgba(46,125,50,0.1)' : undefined } }}
                    />
                    <TextField size="small" label="机械 Y (mm)"
                      value={form.my}
                      onChange={(e) => setField(idx, 'my', e.target.value)}
                      sx={{ flex: 1, '& input': { py: 0.5, fontSize: 13 } }}
                      InputProps={{ sx: { bgcolor: mxDone ? 'rgba(46,125,50,0.1)' : undefined } }}
                    />
                    <Button size="small" variant="outlined"
                      onClick={() => handleReadPosition(idx)}
                      disabled={readingPos === idx || !selectedDeviceId}
                      sx={{ flexShrink: 0, minWidth: 90, fontSize: 12 }}>
                      {readingPos === idx ? '读取中...' : '读取臂位置'}
                    </Button>
                  </Box>
                </Box>
              )
            })}

            {/* Offset 微调 */}
            <Box sx={{ mt: 3, pt: 2, borderTop: '1px solid #333' }}>
              <Typography variant="subtitle2" sx={{ mb: 1, color: '#ccc' }}>
                偏移微调 (offset)
              </Typography>
              <Typography variant="caption" sx={{ color: '#888', mb: 1.5, display: 'block' }}>
                标定后如果联动位置有整体偏移，在此微调。正值向右/下偏移，负值向左/上偏移，单位 mm。
              </Typography>
              <Box sx={{ display: 'flex', gap: 3, alignItems: 'center' }}>
                <Box sx={{ flex: 1 }}>
                  <Typography variant="caption" sx={{ color: '#aaa' }}>X 偏移: {offsetX.toFixed(1)} mm</Typography>
                  <Slider
                    value={offsetX}
                    onChange={(_, v) => setOffsetX(v as number)}
                    min={-10} max={10} step={0.1}
                    size="small"
                    sx={{ mt: 0.5, '& .MuiSlider-thumb': { width: 14, height: 14 } }}
                  />
                </Box>
                <Box sx={{ flex: 1 }}>
                  <Typography variant="caption" sx={{ color: '#aaa' }}>Y 偏移: {offsetY.toFixed(1)} mm</Typography>
                  <Slider
                    value={offsetY}
                    onChange={(_, v) => setOffsetY(v as number)}
                    min={-10} max={10} step={0.1}
                    size="small"
                    sx={{ mt: 0.5, '& .MuiSlider-thumb': { width: 14, height: 14 } }}
                  />
                </Box>
                <Button
                  size="small" variant="outlined"
                  onClick={async () => {
                    if (!selectedDeviceId) return
                    try {
                      await devicesApi.updateOffset(selectedDeviceId, offsetX, offsetY)
                      setToast({ msg: `偏移已更新: X=${offsetX.toFixed(1)}, Y=${offsetY.toFixed(1)} mm`, severity: 'success' })
                    } catch (e) {
                      setToast({ msg: `更新偏移失败: ${e}`, severity: 'error' })
                    }
                  }}
                  disabled={!selectedDeviceId}
                  sx={{ flexShrink: 0, minWidth: 80, fontSize: 12 }}
                >
                  应用偏移
                </Button>
              </Box>
            </Box>
          </Paper>
        </Grid>
      </Grid>
    </Box>
  )
}
